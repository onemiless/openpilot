#!/usr/bin/env python3
"""Offroad-only official YOLOP lane-head benchmark on the selected tinygrad device."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import numpy as np

from openpilot.common.params import Params
from openpilot.sunnypilot.lane_topology.yolop_adapter import YOLOPOnnxLaneModel


def percentile(values: list[float], q: float) -> float:
  return float(np.percentile(np.asarray(values, dtype=np.float64), q * 100.0))


def write_exclusive(path: Path, value: dict) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  with path.open("x") as output:
    json.dump(value, output, indent=2, sort_keys=True)
    output.write("\n")


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--model", type=Path, required=True)
  parser.add_argument("--runs", type=int, default=100)
  parser.add_argument("--report", type=Path, required=True)
  args = parser.parse_args()
  if args.runs <= 0:
    raise ValueError("runs must be positive")

  params = Params()
  if not params.get_bool("IsOffroad"):
    raise RuntimeError("YOLOP lane benchmark requires IsOffroad=1")

  from tinygrad.runtime.support.usb import USB3

  original_control_write = USB3.control_write
  original_bulk_read = USB3.bulk_read
  trace = {"f2_in": 0, "bulk_ok": 0, "bulk_fail": 0, "pending": False,
           "transferred_bytes_min": None, "transferred_bytes_max": None}

  def traced_control_write(self, request, value=0, index=0, data=b"", timeout=1000):
    result = original_control_write(self, request, value, index, data, timeout)
    if request == 0xF2 and value & 0x8000:
      trace["f2_in"] += 1
      trace["pending"] = True
    return result

  def traced_bulk_read(self, length, timeout=1000):
    try:
      result = original_bulk_read(self, length, timeout)
      if trace["pending"]:
        transferred = len(result)
        trace["bulk_ok"] += 1
        trace["pending"] = False
        low, high = trace["transferred_bytes_min"], trace["transferred_bytes_max"]
        trace["transferred_bytes_min"] = transferred if low is None else min(low, transferred)
        trace["transferred_bytes_max"] = transferred if high is None else max(high, transferred)
      return result
    except Exception:
      trace["bulk_fail"] += 1
      raise

  USB3.control_write = traced_control_write
  USB3.bulk_read = traced_bulk_read

  rgb = np.zeros((320, 320, 3), dtype=np.uint8)
  load_started = time.perf_counter()
  model = YOLOPOnnxLaneModel(args.model)
  load_seconds = time.perf_counter() - load_started

  warmup_latencies: list[float] = []
  for _ in range(3):
    started = time.perf_counter()
    logits, _ = model.lane_logits(rgb)
    warmup_latencies.append((time.perf_counter() - started) * 1000.0)

  latencies: list[float] = []
  lane_pixels = 0
  for run in range(args.runs):
    if run % 20 == 0 and not params.get_bool("IsOffroad"):
      raise RuntimeError("IsOffroad changed during YOLOP benchmark")
    started = time.perf_counter()
    logits, _ = model.lane_logits(rgb)
    latencies.append((time.perf_counter() - started) * 1000.0)
    if logits.shape != (1, 2, 320, 320) or not np.all(np.isfinite(logits)):
      raise RuntimeError(f"invalid YOLOP lane output at run {run + 1}: {logits.shape}")
    lane_pixels = int(np.count_nonzero(logits[0, 1] > logits[0, 0]))

  model.close()
  if trace["bulk_fail"] or trace["pending"] or trace["f2_in"] != trace["bulk_ok"]:
    raise RuntimeError(f"incomplete USB trace: {trace}")
  report = {
    "schema": "yolop-lane-usbgpu-benchmark-v1",
    "status": "PASS",
    "model": str(args.model),
    "model_sha256": "86d6e8b6dfdef195c061e9bcad82d9487bb5ee1ac4a1cf9a3dc4736657a07369",
    "input_shape": [1, 3, 320, 320],
    "lane_output_shape": [1, 2, 320, 320],
    "load_seconds": load_seconds,
    "warmup_ms": warmup_latencies,
    "runs": args.runs,
    "latency_ms": {
      "mean": sum(latencies) / len(latencies),
      "p50": percentile(latencies, 0.50),
      "p95": percentile(latencies, 0.95),
      "p99": percentile(latencies, 0.99),
      "min": min(latencies),
      "max": max(latencies),
    },
    "last_lane_pixels": lane_pixels,
    "trace": trace,
    "offroad": params.get_bool("IsOffroad"),
  }
  write_exclusive(args.report, report)
  print(json.dumps(report, indent=2, sort_keys=True))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
