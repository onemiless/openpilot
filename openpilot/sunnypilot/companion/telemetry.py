from __future__ import annotations

import copy
import queue
import threading
from datetime import UTC, datetime
from typing import Any

from openpilot.cereal import messaging
from openpilot.cereal.services import SERVICE_LIST


REQUESTABLE_SERVICES = frozenset((
  "carState", "modelV2", "controlsState", "selfdriveState", "deviceState", "carrotMan", "gpsLocationExternal",
))
SUBSCRIBED_SERVICES = tuple(name for name in REQUESTABLE_SERVICES if name in SERVICE_LIST)


def multiplex_frame(service: str, payload: bytes) -> bytes:
  encoded = service.encode()
  if not encoded or len(encoded) > 255:
    raise ValueError("invalid multiplex service name")
  return bytes((len(encoded),)) + encoded + payload


def _number(value: object, default: float = 0.0) -> float:
  try:
    return float(value)
  except (TypeError, ValueError, OverflowError):
    return default


def _field(value: object, name: str, default: object = None) -> object:
  try:
    return getattr(value, name)
  except (AttributeError, TypeError):
    return default


def _list(value: object, name: str) -> list[Any]:
  item = _field(value, name, ())
  try:
    return list(item)
  except TypeError:
    return []


def legacy_snapshot(messages: dict[str, object], alive: dict[str, bool]) -> dict[str, object]:
  data: dict[str, object] = {}
  car_state = messages.get("carState")
  if car_state is not None and alive.get("carState", False):
    cruise = _field(car_state, "cruiseState")
    data["carState"] = {
      "vEgo": _number(_field(car_state, "vEgo")),
      "vEgoCluster": _number(_field(car_state, "vEgoCluster")),
      "steeringAngleDeg": _number(_field(car_state, "steeringAngleDeg")),
      "leftBlinker": bool(_field(car_state, "leftBlinker", False)),
      "rightBlinker": bool(_field(car_state, "rightBlinker", False)),
      "leftBlindspot": bool(_field(car_state, "leftBlindspot", False)),
      "rightBlindspot": bool(_field(car_state, "rightBlindspot", False)),
      "gasPressed": bool(_field(car_state, "gasPressed", False)),
      "brakePressed": bool(_field(car_state, "brakePressed", False)),
      "cruiseEnabled": bool(_field(cruise, "enabled", False)),
      "cruiseSpeed": _number(_field(cruise, "speed")),
    }

  model = messages.get("modelV2")
  if model is not None and alive.get("modelV2", False):
    leads = _list(model, "leadsV3")
    lead = leads[0] if leads else None
    data["modelV2"] = {
      "leadX": _number((_list(lead, "x") or [0.0])[0]) if lead is not None else 0.0,
      "leadV": _number((_list(lead, "v") or [0.0])[0]) if lead is not None else 0.0,
      "leadProb": _number(_field(lead, "prob")) if lead is not None else 0.0,
      "laneLineProbs": [_number(item) for item in _list(model, "laneLineProbs")],
    }

  controls = messages.get("controlsState")
  selfdrive = messages.get("selfdriveState")
  if ((controls is not None and alive.get("controlsState", False))
      or (selfdrive is not None and alive.get("selfdriveState", False))):
    data["systemState"] = {
      "enabled": bool(_field(selfdrive, "enabled", _field(controls, "enabled", False))),
      "active": bool(_field(selfdrive, "active", _field(controls, "active", False))),
      "engageAllowed": bool(_field(selfdrive, "engageable", False)),
      "vCruise": _number(_field(controls, "vCruise")),
    }

  gps = messages.get("gpsLocationExternal")
  if gps is not None and alive.get("gpsLocationExternal", False):
    data["gpsLocationExternal"] = {
      "latitude": _number(_field(gps, "latitude")),
      "longitude": _number(_field(gps, "longitude")),
      "speed": _number(_field(gps, "speed")),
      "bearingDeg": _number(_field(gps, "bearingDeg")),
      "accuracy": _number(_field(gps, "accuracy")),
    }
  return data


class TelemetryBroker:
  def __init__(self) -> None:
    self._lock = threading.RLock()
    self._clients: dict[int, tuple[frozenset[str], queue.Queue[bytes]]] = {}
    self._next_client_id = 1
    self._latest: dict[str, bytes] = {}
    self._legacy_data: dict[str, object] = {}
    self._sequence = 0
    self._thread: threading.Thread | None = None

  def start(self) -> None:
    if self._thread is not None:
      return
    self._thread = threading.Thread(target=self._run, name="companion-telemetry", daemon=True)
    self._thread.start()

  def register(self, services: list[str]) -> tuple[int, queue.Queue[bytes]]:
    requested = frozenset(services)
    if not requested or not requested <= REQUESTABLE_SERVICES:
      raise ValueError("unknown or missing telemetry services")
    output: queue.Queue[bytes] = queue.Queue(maxsize=64)
    with self._lock:
      client_id = self._next_client_id
      self._next_client_id += 1
      self._clients[client_id] = (requested, output)
      for service in requested:
        if service in self._latest:
          output.put_nowait(multiplex_frame(service, self._latest[service]))
    return client_id, output

  def unregister(self, client_id: int) -> None:
    with self._lock:
      self._clients.pop(client_id, None)

  def publish(self, service: str, payload: bytes) -> None:
    frame = multiplex_frame(service, payload)
    with self._lock:
      self._latest[service] = payload
      clients = list(self._clients.values())
    for services, output in clients:
      if service not in services:
        continue
      try:
        output.put_nowait(frame)
      except queue.Full:
        try:
          output.get_nowait()
          output.put_nowait(frame)
        except (queue.Empty, queue.Full):
          pass

  def legacy_packet(self) -> dict[str, object]:
    with self._lock:
      self._sequence += 1
      return {
        "version": 1,
        "sequence": self._sequence,
        "timestamp": int(datetime.now(UTC).timestamp() * 1000),
        "data": copy.deepcopy(self._legacy_data),
      }

  def _run(self) -> None:
    sm = messaging.SubMaster(list(SUBSCRIBED_SERVICES), ignore_alive=list(SUBSCRIBED_SERVICES))
    while True:
      sm.update(100)
      changed = False
      for service in SUBSCRIBED_SERVICES:
        if sm.updated[service]:
          self.publish(service, bytes(sm[service].to_bytes()))
          changed = True
      if changed:
        messages = {service: sm[service] for service in SUBSCRIBED_SERVICES if sm.seen[service]}
        with self._lock:
          self._legacy_data = legacy_snapshot(messages, sm.alive)
