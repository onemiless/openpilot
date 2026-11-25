# Update branch selection policy

Failure cases recorded before implementation:

- `dev-sp` disappears from the actual tici settings dialog despite available updater metadata.
- An arbitrary `*-tici` branch is mistaken for a supported update target.
- C3XL offers ordinary upstream tici builds without its required hardware seams.
- A currently installed branch disappears because it is absent from remote metadata or outside the allowlist.
- Merely opening or cancelling the dialog changes the updater target or signals updated.
- A prebuild branch is placed under ordinary source branches because only `-prebuilt` is recognized.
- A confirmed choice writes a branch not presented by the dialog.
- Branch names are rewritten, or C3XL source compatibility is reported as physical-device validation.

Standard tici targets: `dev-sp`, `release-tici`, `staging-tici`, `master-tici`,
`release-tici-staging`. Explicit names preserve the existing upstream release,
staging and migration targets without accepting arbitrary suffix matches.

C3XL source targets: `dev-sp`, `dev-sp-egpu`, `dev-sp-egpu-nva`,
`dev-sp-egpu-prebuild`, `navassist-track-p0`. Legacy entries remain available
only when advertised by the updater. This list describes retained source seams;
physical C3XL inference, firmware, boot and onroad validation remain pending.

The installed branch is always retained once, including when absent from remote
metadata. That exception applies only to the installed name, not other custom
branches or an unsupported pending updater target. Selection uses exact names;
opening/cancelling does not migrate or rename a branch.

Repeatable check (run from repository root):

```sh
PYTHONPATH=. /Users/mile/Desktop/mo-op/.venv/bin/python tools/sp_tesla_e2e/branch_selection_e2e.py
```

The JSON artifact records actual `SoftwareLayoutSP._on_select_branch` dialog
construction, selection and cancel callbacks with isolated Params and mocked
updater signalling. It establishes local UI policy behavior, not rendered GUI,
network download, device, or onroad acceptance.

The obsolete `openpilot/sunnypilot/hardware/tests/test_branches.py` is replaced
by this actual UI call-chain E2E. Its meaningful checks survive as C3XL remote
subset filtering, standard tici target filtering, and real dialog grouping of
both `-prebuild` and `-prebuilt` spellings (including ordinary source branches).
Its frozen old allowlist and assertion against the nonexistent
`common.version.TICI_COMPATIBLE_BRANCHES` are retired: branch-name selection
does not attest build metadata or hardware acceptance.
