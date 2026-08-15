#!/usr/bin/env python3
"""Read-only validation for an AGNOS manifest and a tici inactive slot."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request


EXPECTED_PARTITIONS = ("xbl", "xbl_config", "abl", "aop", "devcfg", "boot", "system")
REQUIRED_FIELDS = ("name", "url", "hash", "hash_raw", "size", "sparse", "full_check", "has_ab")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DEFAULT_APPROVAL_FILE = Path("/data/agnos/approved-manifest.sha256")


def load_manifest(path: Path) -> list[dict]:
  data = json.loads(path.read_text())
  if not isinstance(data, list):
    raise ValueError("manifest root must be a list")
  return data


def validate_manifest(manifest: list[dict]) -> list[str]:
  errors: list[str] = []
  names: list[str] = []

  for index, partition in enumerate(manifest):
    if not isinstance(partition, dict):
      errors.append(f"entry {index}: must be an object")
      continue

    missing = [field for field in REQUIRED_FIELDS if field not in partition]
    if missing:
      errors.append(f"entry {index}: missing {', '.join(missing)}")
      continue

    name = partition["name"]
    names.append(name)
    if not isinstance(name, str) or not name:
      errors.append(f"entry {index}: invalid name")
    if not isinstance(partition["size"], int) or partition["size"] <= 0:
      errors.append(f"{name}: size must be a positive integer")
    for field in ("sparse", "full_check", "has_ab"):
      if not isinstance(partition[field], bool):
        errors.append(f"{name}: {field} must be boolean")
    for field in ("hash", "hash_raw"):
      value = partition[field]
      if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        errors.append(f"{name}: {field} must be a lowercase SHA-256")
    url = partition["url"]
    if not isinstance(url, str) or not url.startswith("https://commadist.azureedge.net/agnosupdate/"):
      errors.append(f"{name}: unexpected download URL")
    if partition["has_ab"] is not True:
      errors.append(f"{name}: non-A/B partition is not accepted for this migration")

  if tuple(names) != EXPECTED_PARTITIONS:
    errors.append(f"partition order/names must be: {', '.join(EXPECTED_PARTITIONS)}")
  if len(names) != len(set(names)):
    errors.append("partition names must be unique")
  return errors


def check_urls(manifest: list[dict], timeout: float, retries: int) -> list[str]:
  errors: list[str] = []
  for partition in manifest:
    request = urllib.request.Request(partition["url"], method="HEAD", headers={"Accept-Encoding": "identity"})
    last_error: Exception | None = None
    for attempt in range(retries):
      try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
          if 200 <= response.status < 400:
            last_error = None
            break
          raise RuntimeError(f"HTTP {response.status}")
      except Exception as exc:
        last_error = exc
        if attempt + 1 < retries:
          time.sleep(attempt + 1)
    if last_error is not None:
      errors.append(f"{partition['name']}: URL check failed after {retries} attempts: {last_error}")
  return errors


def command_output(args: list[str]) -> str:
  return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT).strip()


def inspect_device(manifest: list[dict], expected_current: str | None) -> tuple[list[str], list[str]]:
  errors: list[str] = []
  notes: list[str] = []
  if not Path("/AGNOS").exists():
    return ["device check requires AGNOS hardware"], notes

  version = Path("/VERSION").read_text().strip()
  notes.append(f"current AGNOS: {version}")
  if expected_current is not None and version != expected_current:
    errors.append(f"current AGNOS is {version}, expected {expected_current}")

  model = Path("/sys/firmware/devicetree/base/model").read_bytes().rstrip(b"\0").decode(errors="replace")
  notes.append(f"device model: {model}")
  if model != "comma tici":
    errors.append(f"unsupported device model: {model}")

  offroad_path = Path("/data/params/d/IsOffroad")
  if not offroad_path.exists() or offroad_path.read_bytes() != b"1":
    errors.append("device must be offroad before an AGNOS upgrade")
  else:
    notes.append("offroad state: confirmed")

  current_slot = command_output(["abctl", "--boot_slot"])
  if current_slot not in ("_a", "_b"):
    errors.append(f"unexpected boot slot: {current_slot}")
    return errors, notes
  target_suffix = "_b" if current_slot == "_a" else "_a"
  notes.append(f"boot slot: {current_slot}; inactive target: {target_suffix}")

  for partition in manifest:
    path = Path(f"/dev/disk/by-partlabel/{partition['name']}{target_suffix}")
    if not path.exists():
      errors.append(f"{partition['name']}: missing inactive partition {path}")
      continue
    capacity = int(command_output(["blockdev", "--getsize64", os.fspath(path)]))
    required = partition["size"] + (0 if partition["full_check"] else 64)
    notes.append(f"{partition['name']}: {required}/{capacity} bytes")
    if required > capacity:
      errors.append(f"{partition['name']}: image exceeds inactive partition by {required - capacity} bytes")

  return errors, notes


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("manifest", type=Path)
  parser.add_argument("--device", action="store_true", help="also inspect this device's inactive A/B slot")
  parser.add_argument("--expected-current", help="require this currently booted AGNOS version")
  parser.add_argument("--check-urls", action="store_true", help="perform read-only HEAD requests for all images")
  parser.add_argument("--timeout", type=float, default=15.0)
  parser.add_argument("--url-retries", type=int, default=3)
  parser.add_argument("--approve", type=Path, nargs="?", const=DEFAULT_APPROVAL_FILE,
                      help="after all checks pass, atomically approve this exact manifest for activation")
  args = parser.parse_args()
  if args.url_retries < 1:
    parser.error("--url-retries must be at least 1")
  if args.approve is not None and (not args.device or not args.check_urls or args.expected_current is None):
    parser.error("--approve requires --device, --check-urls, and --expected-current")

  try:
    manifest = load_manifest(args.manifest)
  except (OSError, ValueError, json.JSONDecodeError) as exc:
    print(f"FAIL: {exc}")
    return 1

  errors = validate_manifest(manifest)
  notes: list[str] = []
  if args.check_urls and not errors:
    errors.extend(check_urls(manifest, args.timeout, args.url_retries))
  if args.device and not errors:
    device_errors, device_notes = inspect_device(manifest, args.expected_current)
    errors.extend(device_errors)
    notes.extend(device_notes)

  for note in notes:
    print(f"OK: {note}")
  for error in errors:
    print(f"FAIL: {error}")
  if errors:
    return 1
  if args.approve is not None:
    manifest_sha256 = hashlib.sha256(args.manifest.read_bytes()).hexdigest()
    args.approve.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.approve.with_name(f".{args.approve.name}.tmp")
    temporary.write_text(f"{manifest_sha256}\n")
    os.replace(temporary, args.approve)
    print(f"APPROVED: {args.approve} -> {manifest_sha256}")
  print(f"PASS: {args.manifest} is structurally valid" + (" and the inactive slot is compatible" if args.device else ""))
  return 0


if __name__ == "__main__":
  sys.exit(main())
