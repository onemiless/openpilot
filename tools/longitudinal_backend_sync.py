#!/usr/bin/env python3
"""Read-only SP upstream drift report for the tunable longitudinal adapter."""
import argparse
import difflib
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_MAP = {
  "selfdrive/controls/lib/longitudinal_planner.py":
    "openpilot/selfdrive/controls/lib/longitudinal_planner_official.py",
  "selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py":
    "openpilot/selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc_official.py",
}


def git_show(ref: str, path: str) -> list[str]:
  result = subprocess.run(
    ["git", "show", f"{ref}:{path}"], cwd=ROOT, check=True, capture_output=True, text=True,
  )
  return result.stdout.splitlines(keepends=True)


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--ref", default="sunnypilot/dev-c3", help="already-fetched upstream ref")
  parser.add_argument("--diff", action="store_true", help="print the complete source-to-adapter diff")
  args = parser.parse_args()

  for source, adapter in SOURCE_MAP.items():
    upstream = git_show(args.ref, source)
    downstream = (ROOT / adapter).read_text().splitlines(keepends=True)
    delta = list(difflib.unified_diff(upstream, downstream, fromfile=f"{args.ref}:{source}", tofile=adapter))
    print(f"{source} -> {adapter}: {len(delta)} diff lines")
    if args.diff:
      print("".join(delta), end="")

  print("Structural solver changes remain in the adapter and require regeneration plus contract tests.")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
