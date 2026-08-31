import pytest

from openpilot.common.version import BuildMetadata, OpenpilotMetadata


@pytest.fixture
def openpilot_metadata():
  return OpenpilotMetadata(
    version="test", release_notes="", git_commit="0" * 40,
    git_origin="https://github.com/onemiless/openpilot.git",
    git_commit_date="", build_style="source", is_dirty=False,
  )


@pytest.mark.parametrize("branch", ("dev-sp-egpu", "dev-sp-egpu-lane", "navassist-track-p0"))
def test_published_c3xl_branch_is_tici_compatible(openpilot_metadata, branch):
  assert BuildMetadata(branch, openpilot_metadata).channel_type == "tici"


def test_other_development_branches_remain_unsupported_on_tici(openpilot_metadata):
  assert BuildMetadata("dev-unverified", openpilot_metadata).channel_type == "development"
