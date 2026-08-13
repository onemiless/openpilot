from tools.sync_sunnypilot_official import classify_files


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
