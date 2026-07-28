#!/usr/bin/env python3
"""Passively capture Tesla CAN changes across an offroad sleep/wake interval.

Start this tool immediately after closing the car. It keeps the comma device
powered, records changed CAN payloads plus one-second bus statistics, and marks
the first CAN activity after a configurable fully quiet interval. No CAN frames
are transmitted and Panda configuration is not changed.
"""

import argparse
import gzip
import json
import signal
import sys
import time
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_OUTPUT_ROOT = Path("/data/tesla_offline_wake_capture")


@dataclass
class CaptureState:
  record_all: bool
  last_payloads: dict[tuple[int, int], bytes] = field(default_factory=dict)
  second_frame_counts: Counter[int] = field(default_factory=Counter)
  second_change_counts: Counter[int] = field(default_factory=Counter)
  last_frame_monotonic: float | None = None
  quiet_marked: bool = False
  wake_detected: bool = False
  wake_monotonic: float | None = None

  def record_frames(self, frames: Iterable[Any], now: float, force_all: bool = False) -> list[dict[str, Any]]:
    records = []
    for frame in frames:
      bus, address, payload = int(frame.src), int(frame.address), bytes(frame.dat)
      key = (bus, address)
      previous = self.last_payloads.get(key)
      changed = payload != previous
      self.second_frame_counts[bus] += 1
      self.last_frame_monotonic = now

      if changed:
        self.second_change_counts[bus] += 1
      if self.record_all or force_all or changed:
        records.append({
          "type": "frame",
          "t_monotonic_s": round(now, 6),
          "bus": bus,
          "address": address,
          "data": payload.hex(),
          "changed": changed,
          "previous_data": previous.hex() if changed and previous is not None else None,
        })
      self.last_payloads[key] = payload
    return records

  def update_quiet_state(self, now: float, quiet_seconds: float) -> str | None:
    if self.last_frame_monotonic is None:
      return None
    quiet_for = now - self.last_frame_monotonic
    if not self.quiet_marked and quiet_for >= quiet_seconds:
      self.quiet_marked = True
      return "quiet_entered"
    if self.quiet_marked and self.last_frame_monotonic == now:
      self.quiet_marked = False
      self.wake_detected = True
      self.wake_monotonic = now
      return "wake_activity"
    return None

  def consume_second_stats(self, now: float) -> dict[str, Any]:
    record = {
      "type": "second_stats",
      "t_monotonic_s": round(now, 3),
      "frame_counts": dict(sorted(self.second_frame_counts.items())),
      "changed_counts": dict(sorted(self.second_change_counts.items())),
      "tracked_addresses": len(self.last_payloads),
    }
    self.second_frame_counts.clear()
    self.second_change_counts.clear()
    return record


class JsonlWriter:
  def __init__(self, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=False)
    self.output_dir = output_dir
    self.path = output_dir / "capture.jsonl.gz"
    self.file = gzip.open(self.path, "wt", encoding="utf-8")

  def write(self, record: dict[str, Any]) -> None:
    self.file.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")

  def flush(self) -> None:
    self.file.flush()

  def close(self) -> None:
    self.file.close()


def make_output_dir(output_root: Path) -> Path:
  timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
  return output_root / f"tesla_sleep_wake_{timestamp}"


def set_powerdown_disabled(params: Any) -> bool:
  if params.get_bool("ForcePowerDown") or params.get_bool("DoShutdown"):
    raise RuntimeError("ForcePowerDown or DoShutdown is set; clear it before starting a long capture")
  previous = params.get_bool("DisablePowerDown")
  params.put_bool("DisablePowerDown", True)
  return previous


def restore_powerdown_setting(params: Any, previous: bool) -> None:
  params.put_bool("DisablePowerDown", previous)


def run_capture(args: argparse.Namespace) -> Path:
  import cereal.messaging as messaging
  from openpilot.common.params import Params

  params = Params()
  previous_powerdown_setting = set_powerdown_disabled(params)
  output_dir = make_output_dir(args.output_root)
  writer = JsonlWriter(output_dir)
  state = CaptureState(record_all=args.record_all)
  sock = messaging.sub_sock("can", addr=args.addr, conflate=False, timeout=1000)
  started = time.monotonic()
  next_stats = started + 1.0
  raw_capture_until = started + args.raw_window_seconds
  stopped = False

  def stop_handler(_signum, _frame):
    nonlocal stopped
    stopped = True

  old_int = signal.signal(signal.SIGINT, stop_handler)
  old_term = signal.signal(signal.SIGTERM, stop_handler)
  try:
    writer.write({
      "type": "metadata",
      "started_at_utc": datetime.now(timezone.utc).isoformat(),
      "quiet_seconds": args.quiet_seconds,
      "post_wake_seconds": args.post_wake_seconds,
      "raw_window_seconds": args.raw_window_seconds,
      "record_all": args.record_all,
      "powerdown_was_disabled": previous_powerdown_setting,
      "note": "Passive capture only. Start after closing the car; open it normally to end the interval.",
    })
    print(f"Capturing to {writer.path}; DisablePowerDown is temporarily enabled.")

    while not stopped:
      now = time.monotonic()
      messages = messaging.drain_sock(sock, wait_for_one=True)
      had_can_frames = False
      for message in messages:
        event_time = message.logMonoTime / 1e9
        had_can_frames |= bool(message.can)
        wake_batch = bool(message.can) and state.quiet_marked
        if wake_batch:
          state.quiet_marked = False
          state.wake_detected = True
          state.wake_monotonic = event_time
          raw_capture_until = max(raw_capture_until, event_time + args.raw_window_seconds)
          writer.write({"type": "marker", "name": "wake_activity", "t_monotonic_s": round(event_time, 6)})
          print("Detected first CAN activity after a quiet interval; collecting post-wake window.")

        records = state.record_frames(message.can, event_time, force_all=event_time <= raw_capture_until)
        for record in records:
          writer.write(record)

      now = time.monotonic()
      if not had_can_frames:
        marker = state.update_quiet_state(now, args.quiet_seconds)
        if marker == "quiet_entered":
          writer.write({"type": "marker", "name": marker, "t_monotonic_s": round(now, 6)})
          print("CAN has been quiet long enough; armed for the next activity.")

      if now >= next_stats:
        writer.write(state.consume_second_stats(now))
        writer.flush()
        next_stats = now + 1.0

      if state.wake_monotonic is not None and now - state.wake_monotonic >= args.post_wake_seconds:
        stopped = True

    writer.write({
      "type": "metadata",
      "finished_at_utc": datetime.now(timezone.utc).isoformat(),
      "duration_s": round(time.monotonic() - started, 3),
      "wake_detected": state.wake_detected,
    })
    return output_dir
  finally:
    writer.close()
    restore_powerdown_setting(params, previous_powerdown_setting)
    signal.signal(signal.SIGINT, old_int)
    signal.signal(signal.SIGTERM, old_term)


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
  parser.add_argument("--addr", default="127.0.0.1", help="messaging endpoint address")
  parser.add_argument("--quiet-seconds", type=float, default=300.0,
                      help="continuous CAN silence required before automatic wake detection")
  parser.add_argument("--post-wake-seconds", type=float, default=120.0,
                      help="extra capture after automatic wake detection; use 0 to stop immediately")
  parser.add_argument("--raw-window-seconds", type=float, default=60.0,
                      help="retain every raw frame at capture start and after detected wake activity")
  parser.add_argument("--record-all", action="store_true", help="also retain identical repeated payloads")
  args = parser.parse_args()
  if args.quiet_seconds <= 0 or args.post_wake_seconds < 0 or args.raw_window_seconds < 0:
    parser.error("quiet-seconds must be positive; post-wake-seconds and raw-window-seconds must not be negative")

  try:
    output_dir = run_capture(args)
  except RuntimeError as error:
    print(f"Refusing to start: {error}", file=sys.stderr)
    raise SystemExit(2) from error
  print(f"Capture complete: {output_dir}")


if __name__ == "__main__":
  main()
