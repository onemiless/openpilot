import asyncio
import json
import time
from types import SimpleNamespace

from openpilot.common.params import Params as NativeParams
from openpilot.selfdrive.carrot.server.features import ars408


class FakeParams:
  def __init__(self, values=None):
    self.values = dict(values or {})

  def get(self, key, encoding=None):
    value = self.values.get(key)
    if value is None or encoding:
      return value
    return value.encode()

  def put(self, key, value):
    self.values[key] = str(value)


class FakeRequest:
  def __init__(self, params, body=None):
    self.app = {"params": params}
    self.body = body or {}

  async def json(self):
    return self.body


def response_json(response):
  return json.loads(response.text)


def ready_params(values=None):
  return FakeParams({
    "TeslaRadarMode": "2",
    "TeslaRadarActiveMode": "2",
    "TeslaRadarControllerActive": "1",
    "TeslaRadarVehicleDetected": "1",
    "TeslaRadarStateUpdatedAt": str(int(time.monotonic())),
    "IsOnroad": "1",
    "TeslaRadarApplyHeartbeat": str(int(time.monotonic())),
    "TeslaRadarVehicleStandstill": "1",
    "TeslaRadarControlsEnabled": "0",
    "TeslaRadarStateOutputType": "1",
    "TeslaRadarStateQuality": "1",
    **(values or {}),
  })


def test_real_typed_bool_params_are_preserved_in_status_and_gates():
  params = NativeParams()
  params.put_bool("TeslaRadarVehicleDetected", True)
  params.put_bool("TeslaRadarControllerActive", True)
  params.put_bool("TeslaRadarMotionInput", False)
  payload = ars408._status_payload(params)
  assert payload["supported"] is True
  assert payload["controllerReady"] is True
  assert payload["motionInput"] is False


def test_ars408_status_reports_fresh_radar():
  now = int(time.monotonic())
  params = FakeParams({
    "TeslaRadarMode": "2",
    "TeslaRadarActiveMode": "2",
    "TeslaRadarControllerActive": "1",
    "TeslaRadarVehicleDetected": "1",
    "TeslaRadarMotionInput": "1",
    "TeslaRadarStateUpdatedAt": str(now),
    "TeslaRadarStateMaxDistance": "250",
    "TeslaRadarStateOutputType": "1",
  })
  response = asyncio.run(ars408.api_status(FakeRequest(params)))
  payload = response_json(response)
  assert payload["ok"] and payload["online"]
  assert payload["desiredMode"] == payload["activeMode"] == 2
  assert payload["controllerReady"] is True
  assert payload["supported"] is True
  assert payload["state"]["maxDistance"] == "250"
  assert payload["state"]["outputType"] == "1"


def test_ars408_config_request_is_validated_and_queued():
  params = ready_params()
  response = asyncio.run(ars408.api_config(FakeRequest(params, {
    "field": "max_distance", "value": 248, "store": True, "confirm": True,
  })))
  payload = response_json(response)
  assert response.status == 200 and payload["ok"]
  assert params.values["TeslaRadarConfigRequest"].endswith(",max_distance,248,1")

  rejected = asyncio.run(ars408.api_config(FakeRequest(params, {
    "field": "max_distance", "value": 249, "store": False, "confirm": True,
  })))
  assert rejected.status == 400


def test_ars408_filter_query_and_write_validation():
  params = ready_params()
  query = asyncio.run(ars408.api_filter(FakeRequest(params, {"action": "query", "index": 0})))
  assert query.status == 200
  assert ",query,0" in params.values["TeslaRadarFilterRequest"]

  busy = asyncio.run(ars408.api_filter(FakeRequest(params, {
    "index": 0, "active": 1, "minimum": 0, "maximum": 48, "confirm": True,
  })))
  assert busy.status == 400
  params.values.pop("TeslaRadarFilterRequest")

  write = asyncio.run(ars408.api_filter(FakeRequest(params, {
    "index": 0, "active": 1, "minimum": 0, "maximum": 48, "confirm": True,
  })))
  assert write.status == 200
  assert params.values["TeslaRadarFilterRequest"].splitlines()[-1].endswith(",0,1,0,48")

  rejected = asyncio.run(ars408.api_filter(FakeRequest(params, {
    "index": 8, "active": 1, "minimum": 0, "maximum": 8, "confirm": True,
  })))
  assert rejected.status == 400


def test_ars408_writes_require_active_online_standstill_controller():
  inactive = ready_params({"TeslaRadarActiveMode": "0", "TeslaRadarControllerActive": "0"})
  response = asyncio.run(ars408.api_config(FakeRequest(inactive, {
    "field": "output_type", "value": 1, "store": False, "confirm": True,
  })))
  assert response.status == 409

  restart_pending = ready_params({"TeslaRadarMode": "0"})
  response = asyncio.run(ars408.api_config(FakeRequest(restart_pending, {
    "field": "output_type", "value": 1, "store": False, "confirm": True,
  })))
  assert response.status == 409

  offroad = ready_params({"IsOnroad": "0"})
  response = asyncio.run(ars408.api_filter(FakeRequest(offroad, {
    "index": 0, "active": 1, "minimum": 0, "maximum": 48, "confirm": True,
  })))
  assert response.status == 409

  moving = ready_params({"TeslaRadarVehicleStandstill": "0"})
  response = asyncio.run(ars408.api_config(FakeRequest(moving, {
    "field": "max_distance", "value": 250, "store": False, "confirm": True,
  })))
  assert response.status == 409

  engaged_request = FakeRequest(ready_params(), {
    "field": "max_distance", "value": 250, "store": False, "confirm": True,
  })
  engaged_request.app["realtime_broker"] = SimpleNamespace(last_snapshot={
    "services": {"selfdriveState": {"enabled": True}},
  })
  assert asyncio.run(ars408.api_config(engaged_request)).status == 409

  stale = ready_params({"TeslaRadarStateUpdatedAt": str(int(time.monotonic()) - 5)})
  response = asyncio.run(ars408.api_config(FakeRequest(stale, {
    "field": "max_distance", "value": 250, "store": False, "confirm": True,
  })))
  assert response.status == 409


def test_ars408_filter_query_may_run_onroad_but_still_requires_online_controller():
  params = ready_params({"TeslaRadarControlsEnabled": "1"})
  response = asyncio.run(ars408.api_filter(FakeRequest(params, {"action": "query", "index": 0})))
  assert response.status == 200


def test_objects_output_requires_quality_prerequisite():
  params = ready_params({"TeslaRadarStateQuality": "0", "TeslaRadarStateOutputType": "0"})
  response = asyncio.run(ars408.api_config(FakeRequest(params, {
    "field": "output_type", "value": 1, "store": False, "confirm": True,
  })))
  assert response.status == 409
