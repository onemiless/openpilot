#!/usr/bin/env python3
"""Run the real release CLI against tiny temporary Git repositories; emit JSON evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

CLI = Path(__file__).with_name("release.py")


def git(root, *args):
  return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.PIPE).decode().strip()


def init(root):
  root.mkdir()
  git(root, "init", "-q")
  git(root, "config", "user.name", "Release E2E")
  git(root, "config", "user.email", "release-e2e@example.invalid")


def commit(root, message):
  git(root, "add", ".")
  git(root, "commit", "-qm", message)
  return git(root, "rev-parse", "HEAD")


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--output", type=Path, required=True)
  args = parser.parse_args()
  output = args.output.resolve()
  actual_source = CLI.resolve().parents[2]
  if actual_source == output or actual_source in output.parents:
    parser.error("evidence output must be outside source")
  checks = []
  with tempfile.TemporaryDirectory(prefix="dev-sp-release-e2e-") as directory:
    home = Path(directory)
    leaf, dependency, root = home / "leaf", home / "dependency", home / "candidate"
    init(leaf)
    (leaf / "data").write_text("nested dependency\n")
    commit(leaf, "leaf")
    init(dependency)
    (dependency / "data").write_text("dependency\n")
    git(dependency, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(leaf), "nested")
    commit(dependency, "recursive dependency")
    init(root)
    (root / "launch_openpilot.sh").write_text("#!/bin/sh\nexec ./launch_chffrplus.sh\n")
    (root / "launch_openpilot.sh").chmod(0o755)
    (root / "launch_chffrplus.sh").write_text("#!/bin/sh\nexec python3\n")
    (root / "launch_chffrplus.sh").chmod(0o755)
    baseline = commit(root, "official fixture baseline")
    (root / "source.txt").write_text("candidate change\n")
    (root / ".gitignore").write_text("runtime.bin\n")
    (root / "catalog.json").write_text('{"model": "fixture"}\n')
    git(root, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(dependency), "dep")
    git(root, "-c", "protocol.file.allow=always", "submodule", "update", "--init", "--recursive")
    head = commit(root, "candidate")
    artifact = root / "runtime.bin"
    artifact.write_bytes(b"model fixture payload\n")
    artifact.chmod(0o755)
    manifest_path = home / "manifest.json"
    staging = home / "staged"
    venv_bin, host_bin = home / "venv bin", home / "host-bin"
    venv_bin.mkdir()
    host_bin.mkdir()
    (venv_bin / "python3").write_text('#!/bin/sh\nprintf "%s\\n" "venv|$SUNNYPILOT_HARDWARE_PROFILE|$CHESTNUT_ROAD_SIZE|$EXISTING_PCIE_SETTING"\n')
    (host_bin / "python3").write_text('#!/bin/sh\nprintf "wrong-host-python\\n"\n')
    (venv_bin / "python3").chmod(0o755)
    (host_bin / "python3").chmod(0o755)

    def cli(name, arguments, succeeds=True, contains=None):
      command = [sys.executable, str(CLI), "--repo", str(root), *arguments]
      result = subprocess.run(command, capture_output=True, text=True)
      payload = json.loads(result.stdout)
      assert (result.returncode == 0) == succeeds, (name, result.stdout, result.stderr)
      if contains:
        assert contains in payload.get("error", ""), (name, payload)
      checks.append({"check": name, "passed": True, "exit_code": result.returncode, "result": payload})
      return payload

    create = ["manifest", "--baseline", baseline, "--output", str(manifest_path), "--profile", "c3xl",
              "--chestnut-road-size", "1344x760", "--artifact", "runtime.bin", "--catalog", "catalog.json",
              "--venv-bin", str(venv_bin)]
    cli("create", create)
    data = json.loads(manifest_path.read_text())
    assert len(data["repositories"]) == 3
    assert data["repositories"][0]["head"] == head
    assert "exec ./launch_openpilot.sh" in data["boot_template"]
    assert "SUNNYPILOT_HARDWARE_PROFILE=c3xl" in data["boot_template"]
    cli("normal_preflight", ["preflight", "--manifest", str(manifest_path)])
    cli("stage", ["stage", "--manifest", str(manifest_path), "--destination", str(staging)])
    staged = staging / "runtime.bin"
    assert staged.read_bytes() == artifact.read_bytes()
    assert staged.stat().st_mode & 0o777 == 0o755
    assert (staging / "launch_openpilot.sh").stat().st_mode & 0o111
    assert (staging / "dep/nested/data").read_text() == "nested dependency\n"
    checks.append({"check": "recursive_content_and_executable_preserved", "passed": True,
                   "runtime_sha256": hashlib.sha256(staged.read_bytes()).hexdigest(), "mode": "0755"})
    # Run the generated script unchanged; map only its device cd into a temporary fixture.
    # The fixture launch_openpilot -> launch_chffrplus -> python3 chain uses native shells.
    shell_env = home / "bash-env.sh"
    shell_env.write_text('cd() { if [ "$1" = /data/openpilot ]; then builtin cd "$BOOT_FIXTURE_ROOT"; else builtin cd "$@"; fi; }\n')
    environment = {**os.environ, "PATH": f"{host_bin}:/usr/bin:/bin", "BASH_ENV": str(shell_env),
                   "BOOT_FIXTURE_ROOT": str(staging), "EXISTING_PCIE_SETTING": "retained"}
    launched = subprocess.run(["/bin/bash", str(staging / "dev-sp-boot-template.sh")],
                              env=environment, capture_output=True, text=True, check=True)
    assert launched.stdout.strip() == "venv|c3xl|1344x760|retained", (launched.stdout, launched.stderr)
    checks.append({"check": "boot_shell_chain_selects_venv_and_preserves_pcie", "passed": True,
                   "stdout": launched.stdout.strip()})
    default_manifest = home / "default-venv-manifest.json"
    cli("default_c3_venv_manifest", create[:-2] + ["--output", str(default_manifest)])
    assert json.loads(default_manifest.read_text())["boot_venv_bin"] == "/usr/local/venv/bin"
    cli("refuse_relative_venv_bin", create + ["--venv-bin", "relative"], False, "absolute single PATH directory")
    cli("refuse_existing_stage", ["stage", "--manifest", str(manifest_path), "--destination", str(staging)], False)
    cli("refuse_source_output", [*create[:4], str(root / "manifest.json"), *create[5:]], False, "outside source")
    cli("missing_baseline", [*create[:2], "0" * 40, *create[3:]], False)
    unrelated = git(root, "commit-tree", "HEAD^{tree}", "-m", "unrelated baseline")
    cli("unrelated_baseline", [*create[:2], unrelated, *create[3:]], False)
    artifact.unlink()
    cli("missing_artifact", create, False)
    artifact.write_bytes(b"version https://git-lfs.github.com/spec/v1\noid sha256:" + b"0" * 64 + b"\nsize 123\n")
    cli("lfs_pointer", create, False, "LFS pointer")
    artifact.write_bytes(b"model fixture payload\n")
    artifact.chmod(0o755)
    cli("recreate", create)
    artifact.chmod(0o644)
    failed_stage = home / "must-not-publish"
    cli("permission_regression", ["stage", "--manifest", str(manifest_path), "--destination", str(failed_stage)], False, "mode changed")
    assert not failed_stage.exists()
    artifact.chmod(0o755)
    cli("recreate_before_corruption", create)
    before = artifact.stat()
    artifact.write_bytes(b"X" * before.st_size)
    os.utime(artifact, ns=(before.st_atime_ns, before.st_mtime_ns))
    cli("content_corruption_rehash", ["preflight", "--manifest", str(manifest_path), "--rehash"], False, "SHA256")
    cli("content_corruption_stage", ["stage", "--manifest", str(manifest_path), "--destination", str(failed_stage)], False, "SHA256")
    assert not failed_stage.exists()
    (root / "source.txt").write_text("dirty\n")
    cli("dirty_parent", create, False, "dirty checkout")
    git(root, "checkout", "--", "source.txt")
    git(root, "submodule", "deinit", "-f", "--", "dep")
    cli("missing_submodule", create, False, "missing/uninitialized submodule")
    git(root, "-c", "protocol.file.allow=always", "submodule", "update", "--init", "--recursive")
    (root / "dep/nested/data").write_text("dirty nested\n")
    cli("dirty_recursive_dependency", create, False, "dirty checkout")
    git(root / "dep/nested", "checkout", "--", "data")
    assert not git(root, "status", "--porcelain", "--untracked-files=all")
    checks.append({"check": "source_remains_clean", "passed": True})
  evidence = {"status": "passed", "scope": "temporary repositories and local staging only",
              "checks": checks, "device": "pending", "onroad": "pending",
              "repeat_command": [sys.executable, str(Path(__file__).resolve()), "--output", str(output)],
              "tool_sha256": hashlib.sha256(CLI.read_bytes()).hexdigest(),
              "demo_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
  output.parent.mkdir(parents=True, exist_ok=True)
  output.write_text(json.dumps(evidence, indent=2) + "\n")
  print(json.dumps({"status": "passed", "checks": len(checks), "evidence": str(output)}))


if __name__ == "__main__":
  main()
