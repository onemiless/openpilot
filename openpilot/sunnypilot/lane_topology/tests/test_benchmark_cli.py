import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "tools/benchmark_lane_topology.py"


def test_replay_cli_writes_machine_readable_report(tmp_path: Path):
  fixture = tmp_path / "fixture.json"
  report = tmp_path / "report.json"
  fixture.write_text(json.dumps({"samples": [{
    "frame_id": 0,
    "primary_latency_ms": 40.0,
    "boundaries": [
      {"source_id": 1, "points": [[5, 1.8], [10, 1.8], [40, 1.8]], "marking_type": 1, "confidence": 0.9},
      {"source_id": 2, "points": [[5, -1.8], [10, -1.8], [40, -1.8]], "marking_type": 2, "confidence": 0.9},
    ],
  }]}))
  subprocess.run([sys.executable, str(SCRIPT), "--fixture", str(fixture), "--report", str(report)],
                 cwd=ROOT, check=True, capture_output=True, text=True)
  result = json.loads(report.read_text())
  assert result["status"] == "PASS"
  assert result["lane"]["runs"] == 1
  assert result["last_topology"]["visible_lane_count"] == 1
