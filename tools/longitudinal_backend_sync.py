#!/usr/bin/env python3
"""Read-only drift report for the isolated Official and Experimental backends."""
import argparse
import difflib
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_MAPS = {
  "official": {
    "source_candidates": {
      "openpilot/selfdrive/controls/lib/longitudinal_planner.py":
        "openpilot/selfdrive/controls/lib/longitudinal_planner_local.py",
      "openpilot/selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py":
        "openpilot/selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py",
    },
    "legacy_source_candidates": {
      "selfdrive/controls/lib/longitudinal_planner.py":
        "openpilot/selfdrive/controls/lib/longitudinal_planner_local.py",
      "selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py":
        "openpilot/selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py",
    },
  },
  "experimental": {
    "source_candidates": {
      "selfdrive/controls/lib/longitudinal_planner.py":
        "openpilot/selfdrive/controls/lib/longitudinal_planner_official.py",
      "selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py":
        "openpilot/selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc_official.py",
    },
    "legacy_source_candidates": {},
  },
}


def git_show(ref: str, path: str) -> list[str]:
  result = subprocess.run(
    ["git", "show", f"{ref}:{path}"], cwd=ROOT, check=True, capture_output=True, text=True,
  )
  return result.stdout.splitlines(keepends=True)


def source_map(ref: str, backend: str) -> dict[str, str]:
  config = BACKEND_MAPS[backend]
  for candidate in (config["source_candidates"], config["legacy_source_candidates"]):
    if not candidate:
      continue
    first_path = next(iter(candidate))
    exists = subprocess.run(
      ["git", "cat-file", "-e", f"{ref}:{first_path}"], cwd=ROOT,
      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0
    if exists:
      return candidate
  raise ValueError(f"{ref} does not contain the expected {backend} planner paths")


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--ref", default="sunnypilot/master", help="already-fetched SP ref for Official")
  parser.add_argument("--experimental-ref", default="moumou/dev260628XL-tici",
                      help="already-fetched implementation ref for Experimental")
  parser.add_argument("--backend", choices=("all", "official", "experimental"), default="all")
  parser.add_argument("--diff", action="store_true", help="print the complete source-to-adapter diff")
  args = parser.parse_args()

  backends = ("official", "experimental") if args.backend == "all" else (args.backend,)
  for backend in backends:
    ref = args.ref if backend == "official" else args.experimental_ref
    print(f"[{backend}] {ref}")
    for source, adapter in source_map(ref, backend).items():
      upstream = git_show(ref, source)
      downstream = (ROOT / adapter).read_text().splitlines(keepends=True)
      delta = list(difflib.unified_diff(upstream, downstream, fromfile=f"{ref}:{source}", tofile=adapter))
      print(f"{source} -> {adapter}: {len(delta)} diff lines")
      if args.diff:
        print("".join(delta), end="")

  print("Adapter-owned tuning and solver changes require regeneration plus contract tests after any port.")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
