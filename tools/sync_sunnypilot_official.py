#!/usr/bin/env python3
"""Audit new sunnypilot commits and optionally apply only low-risk updates.

This tool deliberately refuses to auto-apply runtime, control, schema, UI,
model, submodule, Panda, or Tesla-adjacent changes. Those commits require a
feature-level port onto this fork's current baseline.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "tools" / "sunnypilot_sync_policy.json"


class SyncError(RuntimeError):
  pass


@dataclass(frozen=True)
class CommitAudit:
  sha: str
  subject: str
  files: tuple[str, ...]
  classification: str
  reason: str


def git(*args: str, check: bool = True) -> str:
  result = subprocess.run(
    ["git", *args], cwd=ROOT, text=True, capture_output=True, check=False,
  )
  if check and result.returncode != 0:
    raise SyncError(result.stderr.strip() or f"git {' '.join(args)} failed")
  return result.stdout.strip()


def load_policy(path: Path) -> dict:
  with path.open() as f:
    return json.load(f)


def changed_files(commit: str) -> tuple[str, ...]:
  output = git("diff-tree", "--root", "--no-commit-id", "--name-only", "-r", commit)
  return tuple(line for line in output.splitlines() if line)


def path_has_prefix(path: str, prefixes: tuple[str, ...]) -> bool:
  return any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in prefixes)


def classify_files(files: tuple[str, ...], policy: dict) -> tuple[str, str]:
  if not files:
    return "manual", "commit has no ordinary file delta"

  protected = tuple(policy["protected_prefixes"])
  protected_hits = tuple(path for path in files if path_has_prefix(path, protected))
  if protected_hits:
    return "manual", f"protected runtime paths: {', '.join(protected_hits)}"

  safe_prefixes = tuple(policy["safe_prefixes"])
  safe_exact = set(policy["safe_exact_files"])
  unsafe = tuple(path for path in files if path not in safe_exact and not path_has_prefix(path, safe_prefixes))
  if unsafe:
    return "manual", f"not in auto-apply allowlist: {', '.join(unsafe)}"

  return "safe", "all files are in the documentation/CI allowlist"


def commit_audit(commit: str, policy: dict) -> CommitAudit:
  sha, subject = git("show", "-s", "--format=%H%x00%s", commit).split("\0", 1)
  files = changed_files(sha)
  classification, reason = classify_files(files, policy)
  return CommitAudit(sha, subject, files, classification, reason)


def assert_apply_context() -> None:
  branch = git("branch", "--show-current")
  if not branch.startswith("codex/"):
    raise SyncError("--apply-safe is only allowed on an isolated codex/* branch")

  tracked_changes = git("status", "--porcelain", "--untracked-files=no")
  if tracked_changes:
    raise SyncError("tracked worktree changes exist; commit or restore them before applying")


def fetch_upstream(policy: dict) -> None:
  remote = policy["upstream_remote"]
  expected_url = policy["upstream_url"]
  configured_url = git("remote", "get-url", remote, check=False)
  if not configured_url:
    git("remote", "add", remote, expected_url)
  elif configured_url != expected_url:
    raise SyncError(f"remote {remote} points to {configured_url}, expected {expected_url}")

  git("fetch", remote, policy["upstream_branch"])


def list_new_commits(policy: dict) -> list[str]:
  upstream = f"{policy['upstream_remote']}/{policy['upstream_branch']}"
  reviewed = policy["last_reviewed_upstream"]
  if git("merge-base", "--is-ancestor", reviewed, upstream, check=False) == "":
    result = subprocess.run(
      ["git", "merge-base", "--is-ancestor", reviewed, upstream], cwd=ROOT, check=False,
    )
    if result.returncode != 0:
      raise SyncError(f"reviewed commit {reviewed} is not an ancestor of {upstream}; upstream may have been rewritten")
  output = git("rev-list", "--reverse", f"{reviewed}..{upstream}")
  return output.splitlines() if output else []


def print_report(audits: list[CommitAudit]) -> None:
  if not audits:
    print("No new sunnypilot commits after the reviewed baseline.")
    return

  for audit in audits:
    print(f"[{audit.classification.upper():6}] {audit.sha[:12]} {audit.subject}")
    print(f"         {audit.reason}")
    for path in audit.files:
      print(f"         - {path}")


def apply_safe(audits: list[CommitAudit]) -> None:
  assert_apply_context()
  safe = [audit for audit in audits if audit.classification == "safe"]
  for audit in safe:
    print(f"Applying safe commit {audit.sha[:12]} {audit.subject}")
    git("cherry-pick", audit.sha)

  manual = len(audits) - len(safe)
  print(f"Applied {len(safe)} safe commit(s); {manual} commit(s) still require feature-level review.")


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
  parser.add_argument("--fetch", action="store_true", help="fetch the configured official branch before auditing")
  parser.add_argument("--apply-safe", action="store_true", help="cherry-pick only allowlisted commits on a codex/* branch")
  parser.add_argument("--create-branch", action="store_true", help="create a dated codex sync branch before applying")
  return parser.parse_args()


def main() -> int:
  args = parse_args()
  try:
    policy = load_policy(args.policy)
    if args.fetch:
      fetch_upstream(policy)

    if args.create_branch:
      if args.apply_safe is False:
        raise SyncError("--create-branch requires --apply-safe")
      branch = f"codex/sp-official-sync-{date.today().strftime('%Y%m%d')}"
      git("switch", "-c", branch)

    audits = [commit_audit(commit, policy) for commit in list_new_commits(policy)]
    print_report(audits)
    if args.apply_safe:
      apply_safe(audits)
  except (OSError, ValueError, SyncError) as exc:
    print(f"sync audit failed: {exc}", file=sys.stderr)
    return 2
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
