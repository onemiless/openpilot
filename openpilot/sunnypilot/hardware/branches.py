from collections.abc import Iterable

from openpilot.sunnypilot.hardware.profile import HardwareProfile


# Update targets with retained source compatibility; not hardware validation.
STANDARD_TICI_BRANCHES = ("dev-sp", "release-tici", "staging-tici", "master-tici", "release-tici-staging")
C3XL_COMPATIBLE_BRANCHES = ("dev-sp", "dev-sp-egpu", "dev-sp-egpu-nva", "dev-sp-egpu-prebuild", "navassist-track-p0")


def is_prebuild_branch(branch: str) -> bool:
  return branch.endswith(("-prebuild", "-prebuilt"))


def selectable_tici_branches(branches: Iterable[str], profile: HardwareProfile, current_branch: str = "") -> list[str]:
  """Offer explicit source targets and retain only the installed custom branch."""
  supported = C3XL_COMPATIBLE_BRANCHES if profile == HardwareProfile.C3XL else STANDARD_TICI_BRANCHES
  available = set(branches)
  return list(dict.fromkeys(([current_branch] if current_branch else []) + [branch for branch in supported if branch in available]))
