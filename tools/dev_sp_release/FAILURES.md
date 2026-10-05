# Failure cases written before implementation

The executable E2E demo must leave JSON evidence and fail on regression:

- Baseline is unavailable or is not an ancestor of the candidate.
- Parent repository is dirty, including staged changes and untracked files.
- A recursive gitlink is uninitialized, has the wrong HEAD, or is dirty.
- Requested runtime artifact is missing, a symlink, or an unresolved Git LFS pointer.
- File content changes after manifest creation; stage must fail without publishing its destination.
- Executable bits change after manifest creation or are lost during copying.
- Destination already exists, is inside the source, or contains an incomplete previous attempt.
- Manifest path escapes the source, or a source symlink escapes its checkout.
- Absolute symlink points inside source but remains bound to the old source path
  after staging, making the local source bundle unusable when source is removed.
- Generation makes the source dirty; output must live outside the checkout.
- Boot template lacks an explicit standard/C3XL profile or uses a nonofficial launch path.
- Boot PATH selects the host Python instead of the specified C3 venv interpreter,
  so the official launch chain cannot import installed runtime dependencies.
- Boot template changes an inherited PCIe setting while correcting interpreter selection.

Source-only success cannot establish runtime model readiness, firmware flashing,
device startup, vehicle control behavior, or onroad acceptance.
