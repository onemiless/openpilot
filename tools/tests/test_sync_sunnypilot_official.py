import pytest

from tools import sync_sunnypilot_official as sync
from tools.sync_sunnypilot_official import SyncError, classify_files


POLICY = {
  "safe_prefixes": [".github/", "docs/"],
  "safe_exact_files": [".editorconfig"],
  "protected_prefixes": [
    "panda", "opendbc_repo", "openpilot/cereal/", "openpilot/selfdrive/controls/", "openpilot/selfdrive/ui/",
  ],
}


def test_docs_and_ci_are_safe():
  classification, _ = classify_files(("docs/README.md", ".github/workflows/tests.yaml"), POLICY)
  assert classification == "safe"


def test_control_change_requires_manual_port():
  classification, reason = classify_files(("openpilot/selfdrive/controls/controlsd.py",), POLICY)
  assert classification == "manual"
  assert "protected runtime paths" in reason


def test_submodule_change_requires_manual_port():
  classification, reason = classify_files(("opendbc_repo",), POLICY)
  assert classification == "manual"
  assert "opendbc_repo" in reason


def test_unknown_path_is_not_auto_applied():
  classification, reason = classify_files(("pyproject.toml",), POLICY)
  assert classification == "manual"
  assert "not in auto-apply allowlist" in reason


def test_fetch_adds_missing_official_remote(monkeypatch):
  calls = []

  def fake_git(*args, check=True):
    calls.append((args, check))
    return "" if args[:3] == ("remote", "get-url", "sunnypilot") else ""

  monkeypatch.setattr(sync, "git", fake_git)
  sync.fetch_upstream({
    "upstream_remote": "sunnypilot",
    "upstream_url": "https://github.com/sunnypilot/sunnypilot.git",
    "upstream_branch": "master",
  })

  assert (("remote", "add", "sunnypilot", "https://github.com/sunnypilot/sunnypilot.git"), True) in calls
  assert (("fetch", "sunnypilot", "master"), True) in calls


def test_fetch_rejects_wrong_remote(monkeypatch):
  monkeypatch.setattr(sync, "git", lambda *args, **kwargs: "https://example.com/not-sunnypilot.git")

  with pytest.raises(SyncError, match="points to"):
    sync.fetch_upstream({
      "upstream_remote": "sunnypilot",
      "upstream_url": "https://github.com/sunnypilot/sunnypilot.git",
      "upstream_branch": "master",
    })
