import time

from aiohttp import web

from ..services.params import HAS_PARAMS, Params
from .system import is_drive_engaged


CONFIG_FIELDS = {
  "max_distance": lambda value: isinstance(value, int) and 200 <= value <= 250 and value % 2 == 0,
  "send_extended": lambda value: value in (0, 1),
  "output_type": lambda value: value in (0, 1),
}
FILTER_BOUNDS = {
  0: (0.0, 100.0), 1: (0.0, 409.5), 2: (-50.0, 52.375),
  3: (0.0, 128.9925), 4: (0.0, 128.9925), 5: (-50.0, 52.375),
  6: (0.0, 409.5), 7: (0.0, 102.375), 8: (0.0, 7.0),
  9: (-409.5, 409.5), 10: (-500.0, 1138.2), 11: (0.0, 128.9925),
  12: (0.0, 128.9925), 13: (0.0, 128.9925), 14: (0.0, 128.9925),
}
STATUS_KEYS = (
  "TeslaRadarStateMaxDistance", "TeslaRadarStateOutputType", "TeslaRadarStateExtended",
  "TeslaRadarStateQuality", "TeslaRadarStateSensorID", "TeslaRadarStateMotionRx",
  "TeslaRadarStateNVMRead", "TeslaRadarStateNVMWrite", "TeslaRadarStateCtrlRelay",
  "TeslaRadarStateRCSThreshold", "TeslaRadarStatePower", "TeslaRadarStateSort",
  "TeslaRadarStateSeq", "TeslaRadarStateUpdatedAt", "TeslaRadarFilterState",
  "TeslaRadarFilterStateSeq", "TeslaRadarConfigResult", "TeslaRadarFilterResult",
)


def _params(request: web.Request):
  params = request.app.get("params")
  if params is None and HAS_PARAMS and Params is not None:
    params = Params()
  if params is None:
    raise web.HTTPServiceUnavailable(text="Params unavailable")
  return params


def _value(params, key, default=None):
  value = params.get(key)
  if isinstance(value, bytes):
    value = value.decode("utf8", errors="replace")
  return default if value is None else value


def _text(params, key, default=""):
  value = _value(params, key, default)
  return default if value in (None, "") else str(value)


def _int(params, key, default=0):
  value = _value(params, key, default)
  if isinstance(value, bool):
    return int(value)
  try:
    return int(value)
  except (TypeError, ValueError):
    return default


def _bool(params, key, default=False):
  value = _value(params, key, default)
  if isinstance(value, bool):
    return value
  if isinstance(value, (int, float)):
    return value != 0
  if isinstance(value, str):
    return value.strip().lower() in ("1", "true", "yes", "on")
  return default


def _put_request(params, key, request):
  if _text(params, "TeslaRadarConfigRequest") or _text(params, "TeslaRadarFilterRequest"):
    raise ValueError("another ARS408 request is still in progress")
  params.put(key, request)
  return 1


def _status_payload(params):
  values = {key: _text(params, key) for key in STATUS_KEYS}
  updated_at = _int(params, "TeslaRadarStateUpdatedAt")
  age_ms = max(0, int((time.monotonic() - updated_at) * 1000)) if updated_at else None
  return {
    "supported": _bool(params, "TeslaRadarVehicleDetected"),
    "mode": _int(params, "TeslaRadarMode"),
    "desiredMode": _int(params, "TeslaRadarMode"),
    "activeMode": _int(params, "TeslaRadarActiveMode"),
    "controllerReady": _bool(params, "TeslaRadarControllerActive"),
    "applyReady": age_ms is not None and age_ms <= 3000 and \
      int((time.monotonic() - _int(params, "TeslaRadarApplyHeartbeat")) * 1000) <= 2500,
    "vehicleStandstill": _bool(params, "TeslaRadarVehicleStandstill"),
    "controlsEnabled": _bool(params, "TeslaRadarControlsEnabled"),
    "motionInput": _bool(params, "TeslaRadarMotionInput", True),
    "online": age_ms is not None and age_ms <= 3000,
    "stateAgeMs": age_ms,
    "state": {
      "maxDistance": values["TeslaRadarStateMaxDistance"],
      "outputType": values["TeslaRadarStateOutputType"],
      "extended": values["TeslaRadarStateExtended"],
      "quality": values["TeslaRadarStateQuality"],
      "sensorId": values["TeslaRadarStateSensorID"],
      "motionRx": values["TeslaRadarStateMotionRx"],
      "nvmRead": values["TeslaRadarStateNVMRead"],
      "nvmWrite": values["TeslaRadarStateNVMWrite"],
      "ctrlRelay": values["TeslaRadarStateCtrlRelay"],
      "rcsThreshold": values["TeslaRadarStateRCSThreshold"],
      "power": values["TeslaRadarStatePower"],
      "sort": values["TeslaRadarStateSort"],
      "sequence": values["TeslaRadarStateSeq"],
    },
    "prerequisites": {
      "bus": 1,
      "sensorIdOk": values["TeslaRadarStateSensorID"] == "0",
      "qualityOk": values["TeslaRadarStateQuality"] == "1",
    },
    "filterState": values["TeslaRadarFilterState"],
    "filterSequence": values["TeslaRadarFilterStateSeq"],
    "configResult": values["TeslaRadarConfigResult"],
    "filterResult": values["TeslaRadarFilterResult"],
  }


def _write_block_reason(request, params, read_only=False):
  if not _bool(params, "IsOnroad"):
    return "ARS408 controller requires ignition on"
  desired_mode = _int(params, "TeslaRadarMode")
  active_mode = _int(params, "TeslaRadarActiveMode")
  if desired_mode != active_mode:
    return "ARS408 mode change is pending; restart before configuring the radar"
  if not _bool(params, "TeslaRadarControllerActive") or active_mode not in (1, 2, 3):
    return "ARS408 controller is not active; restart after enabling the mode"
  heartbeat = _int(params, "TeslaRadarApplyHeartbeat")
  if heartbeat <= 0 or time.monotonic() - heartbeat > 2.5:
    return "ARS408 apply loop is not active"
  updated_at = _int(params, "TeslaRadarStateUpdatedAt")
  if updated_at <= 0 or time.monotonic() - updated_at > 3.0:
    return "ARS408 RadarState is not online"
  sensor_id = _text(params, "TeslaRadarStateSensorID")
  if sensor_id and sensor_id != "0":
    return "ARS408 Sensor ID must be 0"
  if not read_only:
    if not _bool(params, "TeslaRadarVehicleStandstill"):
      return "vehicle must be stationary"
    if _bool(params, "TeslaRadarControlsEnabled") or is_drive_engaged(request):
      return "openpilot must be disengaged"
  return None


async def api_status(request: web.Request) -> web.Response:
  return web.json_response({"ok": True, **_status_payload(_params(request))})


async def api_config(request: web.Request) -> web.Response:
  try:
    body = await request.json()
    params = _params(request)
    if reason := _write_block_reason(request, params):
      return web.json_response({"ok": False, "error": reason}, status=409)
    field = str(body.get("field") or "")
    value = int(body.get("value"))
    raw_store = body.get("store", False)
    if raw_store not in (True, False, 0, 1):
      raise ValueError("store must be boolean")
    store = int(bool(raw_store))
    if body.get("confirm") is not True:
      raise ValueError("explicit confirmation is required")
    validator = CONFIG_FIELDS.get(field)
    if validator is None or not validator(value):
      raise ValueError(f"invalid ARS408 {field or 'configuration'} value")
    if field == "output_type" and value == 1 and _int(params, "TeslaRadarStateQuality") != 1:
      return web.json_response({"ok": False, "error": "Quality must be enabled before Objects output"}, status=409)
    request_id = str(int(time.monotonic() * 1000))
    depth = _put_request(params, "TeslaRadarConfigRequest", f"{request_id},{field},{value},{store}")
    return web.json_response({"ok": True, "requestId": request_id, "queueDepth": depth})
  except (TypeError, ValueError) as exc:
    return web.json_response({"ok": False, "error": str(exc)}, status=400)


async def api_filter(request: web.Request) -> web.Response:
  try:
    body = await request.json()
    params = _params(request)
    index = int(body.get("index"))
    if index not in FILTER_BOUNDS:
      raise ValueError("filter index must be 0..14")
    action = str(body.get("action") or "write")
    if action not in ("query", "write"):
      raise ValueError("filter action must be query or write")
    if reason := _write_block_reason(request, params, read_only=action == "query"):
      return web.json_response({"ok": False, "error": reason}, status=409)
    request_id = str(int(time.monotonic() * 1000))
    if action == "query":
      record = f"{request_id},query,{index}"
    else:
      if body.get("confirm") is not True:
        raise ValueError("explicit confirmation is required")
      active = int(body.get("active"))
      minimum = float(body.get("minimum"))
      maximum = float(body.get("maximum"))
      lower, upper = FILTER_BOUNDS[index]
      if active not in (0, 1) or not (lower <= minimum <= maximum <= upper):
        raise ValueError(f"invalid filter {index} range {minimum}..{maximum}")
      if index == 0:
        minimum = 0.0
      record = f"{request_id},{index},{active},{minimum:.10g},{maximum:.10g}"
    depth = _put_request(params, "TeslaRadarFilterRequest", record)
    return web.json_response({"ok": True, "requestId": request_id, "queueDepth": depth})
  except (TypeError, ValueError) as exc:
    return web.json_response({"ok": False, "error": str(exc)}, status=400)


def register(app: web.Application) -> None:
  app.router.add_get("/api/ars408", api_status)
  app.router.add_post("/api/ars408/config", api_config)
  app.router.add_post("/api/ars408/filter", api_filter)
