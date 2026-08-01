import json
import os
import queue
import threading
import time


TESLA_CAN_PROBE_PATH = "/data/tesla_can_probe.log"
TESLA_CAN_PROBE_PREFIX = "[TESLA-CAN-PROBE-v2]"
# The probe stays available for manual diagnostics, but production/dev builds
# must not continuously record raw CAN traffic.
TESLA_CAN_PROBE_LOGGING_ENABLED = False

_EXACT_SEQUENCE_ADDRESSES = {
  0x249: "SCCM_leftStalk",
  0x3C2: "VCLEFT_switchStatus",
  0x3E9: "DAS_bodyControls",
  0x3F5: "ID3F5VCFRONT_lighting",
}
_STATE_ADDRESS = 0x39B  # DAS_status
_MAX_LOG_BYTES = 8 * 1024 * 1024
_FLUSH_INTERVAL_NS = 250_000_000
_HEARTBEAT_INTERVAL_NS = 1_000_000_000


def _source_details(source: int) -> tuple[int, str]:
  if source >= 0xC0:
    return source - 0xC0, "rejected"
  if source >= 0x80:
    return source - 0x80, "txEcho"
  return source, "rx"


def _signed_6bit(value: int) -> int:
  value &= 0x3F
  return value - 0x40 if value & 0x20 else value


def decode_tesla_probe_frame(address: int, data: bytes) -> dict:
  decoded = {}
  if address == 0x3C2 and len(data) == 8:
    decoded = {
      "switch_status_index": data[0] & 0x3,
      "left_scroll_ticks": _signed_6bit(data[2]),
      "right_scroll_ticks": _signed_6bit(data[3]),
      "left_pressed": (data[0] >> 5) & 0x3,
      "right_pressed": (data[1] >> 4) & 0x3,
    }
  elif address == 0x249 and len(data) == 4:
    decoded = {
      "turn_stalk_state": data[2] & 0xF,
      "counter": data[1] & 0xF,
      "checksum": data[0],
    }
  elif address == 0x3E9 and len(data) >= 8:
    decoded = {
      "turn_request": data[1] & 0x3,
      "turn_request_reason": (data[2] >> 1) & 0xF,
      "autopilot_active": data[3] & 0x1,
      "acc_active": (data[3] >> 5) & 0x1,
      "counter": (data[6] >> 4) & 0xF,
      "checksum": data[7],
    }
  elif address == 0x3F5 and len(data) == 8:
    raw = int.from_bytes(data, byteorder="little")
    left_state = (raw >> 50) & 0x3
    right_state = (raw >> 52) & 0x3
    decoded = {
      "left_blinker": left_state == 1,
      "right_blinker": right_state == 1,
      "left_blinker_state": left_state,
      "right_blinker_state": right_state,
    }
  elif address == _STATE_ADDRESS and len(data) >= 8:
    raw = int.from_bytes(data, byteorder="little")
    decoded = {
      "autopilot_state": raw & 0xF,
      "fused_speed_limit_raw": (raw >> 8) & 0x1F,
      "auto_lane_change_state": (raw >> 46) & 0x1F,
      "counter": (raw >> 52) & 0xF,
      "checksum": data[7],
    }
  return decoded


class TeslaCanProbe:
  """Bounded, read-only capture of Tesla messages needed for turn/speed validation."""

  def __init__(self, enabled: bool, log_path: str = TESLA_CAN_PROBE_PATH) -> None:
    self.enabled = enabled and TESLA_CAN_PROBE_LOGGING_ENABLED
    self.log_path = log_path
    self.pending: list[dict] = []
    self.write_queue: queue.Queue[list[dict]] | None = queue.Queue(maxsize=64) if self.enabled else None
    self.last_flush_ns = 0
    self.last_das_status_signature: tuple | None = None
    self.last_das_status_log_ns = 0
    self.last_state_signature: tuple | None = None
    self.last_state_log_ns = 0
    self.last_speed_wheel_ticks: dict[tuple[int, str], int] = {}
    if self.enabled:
      threading.Thread(target=self._writer, name="tesla-can-probe-writer", daemon=True).start()
      self._queue("capture_started", monotonic_ns=time.monotonic_ns(),
                  addresses=["0x249", "0x39b", "0x3c2", "0x3e9", "0x3f5"])

  def _queue(self, event: str, **values) -> None:
    self.pending.append({
      "prefix": TESLA_CAN_PROBE_PREFIX,
      "monotonic_ns": time.monotonic_ns(),
      "event": event,
      **values,
    })

  def _writer(self) -> None:
    assert self.write_queue is not None
    while True:
      records = self.write_queue.get()
      try:
        if os.path.exists(self.log_path) and os.path.getsize(self.log_path) > _MAX_LOG_BYTES:
          os.replace(self.log_path, f"{self.log_path}.1")
        with open(self.log_path, "a", encoding="utf-8") as log_file:
          for record in records:
            log_file.write(json.dumps(record, sort_keys=True, default=str) + "\n")
      except OSError:
        pass
      finally:
        self.write_queue.task_done()

  def _flush_if_due(self, now_ns: int, force: bool = False) -> None:
    if not self.pending or (not force and len(self.pending) < 128 and now_ns - self.last_flush_ns < _FLUSH_INTERVAL_NS):
      return
    records, self.pending = self.pending, []
    self.last_flush_ns = now_ns
    assert self.write_queue is not None
    try:
      self.write_queue.put_nowait(records)
    except queue.Full:
      # Diagnostics must never block or interfere with the 100 Hz controls loop.
      pass

  def update_can(self, can_list) -> None:
    if not self.enabled:
      return
    latest_ns = time.monotonic_ns()
    for mono_time, frames in can_list:
      latest_ns = max(latest_ns, mono_time)
      for address, data, source in frames:
        if address not in _EXACT_SEQUENCE_ADDRESSES and address != _STATE_ADDRESS:
          continue
        decoded = decode_tesla_probe_frame(address, data)
        if address == _STATE_ADDRESS:
          signature = tuple((key, decoded[key]) for key in ("autopilot_state", "fused_speed_limit_raw", "auto_lane_change_state"))
          if signature == self.last_das_status_signature and mono_time - self.last_das_status_log_ns < _HEARTBEAT_INTERVAL_NS:
            continue
          self.last_das_status_signature = signature
          self.last_das_status_log_ns = mono_time

        bus, direction = _source_details(source)
        if address == 0x3C2 and len(data) == 8 and decoded["switch_status_index"] == 1:
          stream = (bus, direction)
          right_ticks = decoded["right_scroll_ticks"]
          previous_ticks = self.last_speed_wheel_ticks.get(stream)
          if right_ticks != previous_ticks:
            self._queue(
              "speed_wheel_change",
              can_monotonic_ns=mono_time,
              source=source,
              bus=bus,
              direction=direction,
              previous_right_scroll_ticks=previous_ticks,
              right_scroll_ticks=right_ticks,
              data=data.hex(),
              decoded=decoded,
            )
            self.last_speed_wheel_ticks[stream] = right_ticks
        self._queue(
          "can_frame",
          can_monotonic_ns=mono_time,
          address=address,
          address_hex=f"0x{address:X}",
          message=_EXACT_SEQUENCE_ADDRESSES.get(address, "DAS_status"),
          source=source,
          bus=bus,
          direction=direction,
          data=data.hex(),
          decoded=decoded,
        )
    self._flush_if_due(latest_ns)

  def update_state(self, CS, CS_SP, now_ns: int | None = None) -> None:
    if not self.enabled:
      return
    now_ns = time.monotonic_ns() if now_ns is None else now_ns
    cruise_speed = round(float(CS.cruiseState.speed), 2)
    cruise_speed_cluster = round(float(CS.cruiseState.speedCluster), 2)
    speed_limit = round(float(CS_SP.speedLimit), 2)
    signature = (
      bool(CS.leftBlinker), bool(CS.rightBlinker), bool(CS.leftBlindspot), bool(CS.rightBlindspot),
      bool(CS.brakePressed), bool(CS.cruiseState.enabled), bool(CS.cruiseState.available),
      cruise_speed, cruise_speed_cluster, speed_limit, int(CS_SP.flags),
    )
    if signature != self.last_state_signature or now_ns - self.last_state_log_ns >= _HEARTBEAT_INTERVAL_NS:
      self.last_state_signature = signature
      self.last_state_log_ns = now_ns
      self._queue(
        "car_state",
        monotonic_ns=now_ns,
        v_ego=round(float(CS.vEgo), 2),
        v_ego_cluster=round(float(getattr(CS, "vEgoCluster", CS.vEgo)), 2),
        left_blinker=signature[0],
        right_blinker=signature[1],
        left_blindspot=signature[2],
        right_blindspot=signature[3],
        brake_pressed=signature[4],
        cruise_enabled=signature[5],
        cruise_available=signature[6],
        cruise_speed=cruise_speed,
        cruise_speed_cluster=cruise_speed_cluster,
        speed_limit=speed_limit,
        car_state_sp_flags=signature[10],
      )
    self._flush_if_due(now_ns)

  def flush(self) -> None:
    if self.enabled:
      self._flush_if_due(time.monotonic_ns(), force=True)
      assert self.write_queue is not None
      self.write_queue.join()
