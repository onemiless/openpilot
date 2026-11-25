#!/usr/bin/env python3
"""Source identity lock and local staging only; no device transport or deployment."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import shlex
import stat
import subprocess
import tempfile

OFFICIAL_BASELINE = "16322aef167fe14de8af28a9e437101ed3c4dac5"
LFS_POINTER = b"version https://git-lfs.github.com/spec/v1"
NORMAL_HASH_LIMIT = 64 * 1024 * 1024


def git(root, *args):
  return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.PIPE).decode().strip()


def outside(root, path):
  if Path(path).is_symlink():
    raise ValueError(f"output must not be a symlink: {path}")
  path = Path(path).resolve()
  if path == root or root in path.parents:
    raise ValueError(f"generated output must be outside source: {path}")
  return path


def source_path(root, relative):
  path = root / relative
  if Path(relative).is_absolute() or ".." in Path(relative).parts or relative == ".":
    raise ValueError(f"unsafe relative path: {relative}")
  if path.is_symlink() and Path(os.readlink(path)).is_absolute():
    raise ValueError(f"absolute symlink is not portable in staged source: {relative}")
  if root not in path.resolve().parents:
    raise ValueError(f"source path escapes checkout: {relative}")
  return path


def sha256(path):
  digest = hashlib.sha256()
  with path.open("rb") as stream:
    for block in iter(lambda: stream.read(1024 * 1024), b""):
      digest.update(block)
  return digest.hexdigest()


def file_record(root, relative, runtime=False):
  path = source_path(root, relative)
  info = path.lstat()
  if runtime:
    if not stat.S_ISREG(info.st_mode):
      raise ValueError(f"runtime artifact must be a regular file: {relative}")
    with path.open("rb") as stream:
      if stream.read(256).startswith(LFS_POINTER):
        raise ValueError(f"unresolved LFS pointer: {relative}")
  result = {"path": relative, "mode": stat.S_IMODE(info.st_mode), "size": info.st_size,
            "mtime_ns": info.st_mtime_ns}
  if path.is_symlink():
    result["symlink"] = os.readlink(path)
  else:
    result["sha256"] = sha256(path)
  return result


def checkout(root, prefix=""):
  """Lock every gitlink recursively, including neural data and nested dependencies."""
  if git(root, "rev-parse", "--show-toplevel") != str(root):
    raise ValueError(f"missing/uninitialized submodule checkout: {prefix or root}")
  dirty = git(root, "status", "--porcelain", "--untracked-files=all")
  if dirty:
    raise ValueError(f"dirty checkout {prefix or '.'}: {dirty[:1000]}")
  head = git(root, "rev-parse", "HEAD")
  lfs = subprocess.run(["git", "-C", str(root), "lfs", "env"], capture_output=True, text=True)
  lock = {"path": prefix or ".", "head": head,
          "lfs_endpoints": sorted({line.split("=", 1)[1].rsplit(" (auth=", 1)[0]
                                   for line in lfs.stdout.splitlines() if line.startswith("Endpoint") and "=" in line}),
          "lfs_env_available": lfs.returncode == 0}
  locks, files = [lock], []
  for entry in git(root, "ls-tree", "-rz", "HEAD").split("\0"):
    if not entry:
      continue
    metadata, name = entry.split("\t", 1)
    mode, kind, expected = metadata.split()
    relative = f"{prefix}/{name}" if prefix else name
    path = source_path(root, name)
    if kind == "commit":
      if not (path / ".git").exists():
        raise ValueError(f"missing/uninitialized submodule: {relative} (expected {expected})")
      children, child_files = checkout(path, relative)
      if children[0]["head"] != expected:
        raise ValueError(f"gitlink mismatch: {relative}: expected {expected}, actual {children[0]['head']}")
      children[0]["gitlink"] = expected
      locks.extend(children)
      files.extend(child_files)
    else:
      if not path.exists() and not path.is_symlink():
        raise ValueError(f"missing tracked file: {relative}")
      if mode in ("100644", "100755") and bool(path.stat().st_mode & 0o111) != (mode == "100755"):
        raise ValueError(f"tracked executable permission differs from Git mode {mode}: {relative}")
      files.append(relative)
  return locks, files


def baseline_relation(root, baseline):
  if len(baseline) != 40 or any(c not in "0123456789abcdef" for c in baseline):
    raise ValueError("baseline must be a full lowercase commit SHA")
  git(root, "cat-file", "-e", f"{baseline}^{{commit}}")
  git(root, "merge-base", "--is-ancestor", baseline, "HEAD")
  return {"sha": baseline, "ancestor_of_parent": True,
          "candidate_commits": int(git(root, "rev-list", "--count", f"{baseline}..HEAD"))}


def boot_template(profile, chestnut_size, venv_bin):
  if not Path(venv_bin).is_absolute() or ":" in venv_bin:
    raise ValueError("venv bin must be an absolute single PATH directory")
  lines = ["#!/usr/bin/env bash", "set -e", "cd /data/openpilot",
           f'export PATH={shlex.quote(venv_bin)}:"$PATH"',
           f"export SUNNYPILOT_HARDWARE_PROFILE={profile}"]
  if chestnut_size:
    lines.append("export CHESTNUT_ROAD_SIZE=1344x760")
  lines.append("exec ./launch_openpilot.sh")
  return "\n".join(lines) + "\n"


def manifest(root, baseline, profile, chestnut_size, artifacts, catalog, venv_bin):
  relation = baseline_relation(root, baseline)
  locks, files = checkout(root)
  changed = set(git(root, "diff", "--name-only", "--diff-filter=ACMRT", "-z", baseline, "HEAD").split("\0"))
  # A changed gitlink locks and hashes its current tracked contents, including nested gitlinks.
  selected = [name for name in files if name in changed or any(str(parent) in changed for parent in Path(name).parents)]
  records = [file_record(root, name) for name in selected]
  runtime = [file_record(root, name, runtime=True) for name in dict.fromkeys(artifacts + ([catalog] if catalog else []))]
  return {"version": 1, "source": str(root), "baseline": relation, "repositories": locks,
          "tracked_file_count": len(files), "changed_files": records, "runtime_artifacts": runtime,
          "model_catalog": catalog, "boot_profile": profile, "boot_venv_bin": venv_bin,
          "boot_template": boot_template(profile, chestnut_size, venv_bin),
          "validation": {"source_identity": "passed", "device": "pending", "onroad": "pending"}}


def preflight(root, data, rehash=False):
  if data["version"] != 1:
    raise ValueError("unsupported manifest version")
  baseline_relation(root, data["baseline"]["sha"])
  locks, files = checkout(root)
  if locks != data["repositories"] or len(files) != data["tracked_file_count"]:
    raise ValueError("repository identity / recursive dependency lock changed")
  changed_paths = {record["path"] for record in data["changed_files"]}
  runtime_paths = {record["path"] for record in data["runtime_artifacts"]}
  records = {record["path"]: record for record in data["changed_files"] + data["runtime_artifacts"]}
  for record in records.values():
    path = source_path(root, record["path"])
    info = path.lstat()
    for key, actual in (("mode", stat.S_IMODE(info.st_mode)), ("size", info.st_size), ("mtime_ns", info.st_mtime_ns)):
      if record[key] != actual:
        raise ValueError(f"file {key} changed: {record['path']}")
    if "symlink" in record:
      if os.readlink(path) != record["symlink"]:
        raise ValueError(f"symlink changed: {record['path']}")
    else:
      with path.open("rb") as stream:
        if record["path"] in runtime_paths and stream.read(256).startswith(LFS_POINTER):
          raise ValueError(f"unresolved LFS pointer: {record['path']}")
      if (rehash or (record["path"] in changed_paths and record["size"] <= NORMAL_HASH_LIMIT)) and sha256(path) != record["sha256"]:
        raise ValueError(f"SHA256 changed: {record['path']}")
  return files


def atomic_json(path, data):
  path.parent.mkdir(parents=True, exist_ok=True)
  with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
    temporary = Path(stream.name)
    json.dump(data, stream, indent=2)
    stream.write("\n")
  try:
    os.replace(temporary, path)
  finally:
    temporary.unlink(missing_ok=True)


def stage(root, data, destination):
  destination = outside(root, destination)
  if destination.exists() or destination.is_symlink():
    raise ValueError(f"destination already exists: {destination}")
  files = preflight(root, data, rehash=True)
  destination.parent.mkdir(parents=True, exist_ok=True)
  temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
  try:
    for name in dict.fromkeys(files + [r["path"] for r in data["runtime_artifacts"]]):
      source = source_path(root, name)
      target = temporary / name
      target.parent.mkdir(parents=True, exist_ok=True)
      shutil.copy2(source, target, follow_symlinks=False)
      if stat.S_IMODE(source.lstat().st_mode) != stat.S_IMODE(target.lstat().st_mode):
        raise ValueError(f"copy lost permissions: {name}")
    records = {record["path"]: record for record in data["changed_files"] + data["runtime_artifacts"]}
    for record in records.values():
      target = temporary / record["path"]
      if "sha256" in record and sha256(target) != record["sha256"]:
        raise ValueError(f"staged SHA256 mismatch: {record['path']}")
    (temporary / "dev-sp-boot-template.sh").write_text(data["boot_template"])
    (temporary / "dev-sp-boot-template.sh").chmod(0o755)
    atomic_json(temporary / "dev-sp-release-manifest.json", data)
    preflight(root, data, rehash=True)
    # Exclusive directory rename fails if another producer created a nonempty destination.
    # Use an exclusive lock also to avoid replacing an empty destination during rename.
    lock = destination.parent / f".{destination.name}.lock"
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
      if destination.exists() or destination.is_symlink():
        raise ValueError(f"destination appeared during stage: {destination}")
      os.rename(temporary, destination)
    finally:
      os.close(descriptor)
      lock.unlink()
  finally:
    if temporary.exists():
      shutil.rmtree(temporary)
  return {"destination": str(destination), "files": len(files), "status": "local_staged",
          "device": "pending", "onroad": "pending"}


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--repo", type=Path, default=Path.cwd())
  commands = parser.add_subparsers(dest="command", required=True)
  create = commands.add_parser("manifest")
  create.add_argument("--baseline", default=OFFICIAL_BASELINE, help="full reviewed official candidate SHA")
  create.add_argument("--output", type=Path, required=True)
  create.add_argument("--profile", choices=["standard", "c3xl"], required=True)
  create.add_argument("--venv-bin", default="/usr/local/venv/bin", help="device runtime executable directory")
  create.add_argument("--chestnut-road-size", choices=["1344x760"])
  create.add_argument("--artifact", action="append", default=[], help="relative runtime file, including ignored build outputs")
  create.add_argument("--catalog", help="relative model catalog; hashed and staged as runtime input")
  for name in ("preflight", "stage"):
    command = commands.add_parser(name)
    command.add_argument("--manifest", type=Path, required=True)
    if name == "stage":
      command.add_argument("--destination", type=Path, required=True)
    else:
      command.add_argument("--rehash", action="store_true", help="rehash runtime artifacts (GB files), too")
  args = parser.parse_args()
  root = args.repo.resolve()
  try:
    if args.command == "manifest":
      output = outside(root, args.output)
      data = manifest(root, args.baseline, args.profile, args.chestnut_road_size, args.artifact, args.catalog, args.venv_bin)
      atomic_json(output, data)
      result = {"status": "manifest_created", "manifest": str(output), "parent": data["repositories"][0]["head"]}
    else:
      data = json.loads(args.manifest.read_text())
      if args.command == "stage":
        result = stage(root, data, args.destination)
      else:
        files = preflight(root, data, args.rehash)
        result = {"status": "source_preflight_passed", "files": len(files), "large_artifacts_rehashed": args.rehash,
                  "device": "pending", "onroad": "pending"}
    print(json.dumps(result))
  except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
    print(json.dumps({"status": "failed", "error": str(error)}))
    raise SystemExit(1) from None


if __name__ == "__main__":
  main()
