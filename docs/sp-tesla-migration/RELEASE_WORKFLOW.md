# dev-sp source sync and local release staging

This workflow preserves the existing Tesla feature set and produces a reviewable
source lock plus a local staged directory. It does not push Git refs, contact a
device, alter boot partitions, install a model, or prove vehicle acceptance.
The implementation uses only Python's standard library and the installed Git CLI.

## Start from an identified candidate

Record the exact current worktree, branch and HEAD before changing source. Keep
dirty worktrees intact and do sync work in an isolated candidate checkout. The
reviewed official baseline for this migration is
`16322aef167fe14de8af28a9e437101ed3c4dac5`. The existing `master` was 124 commits
behind this baseline when this workflow was introduced; its branch name is not
evidence of freshness. Do not switch to or publish `master` blindly.

1. Fetch official changes without replacing the current feature branch. Identify
   the candidate official SHA, commit date, its relationship to the previous
   baseline, and the retained Tesla feature manifest.
2. Build a sync candidate branch and review the official delta. Merge or port
   only after checking the full dependency closure: parent source, recursive
   gitlinks, DBC/CAN/safety, Params, schemas, UI, model catalog and loader, warp
   settings, launch configuration and hardware profile.
3. Track carried patches against their upstream replacement. Once an official
   implementation covers a patch, remove the superseded patch in the candidate
   and verify its behavior once at the responsible layer. Do not stack duplicate
   guards or keep obsolete compatibility code solely because it was carried before.
4. Resolve Cap'n Proto schema field/type/ordinal conflicts explicitly, inspect
   generated-schema consumers, and run the existing schema build. Never auto-renumber
   ordinals to make a merge compile. This small release CLI does not implement a
   partial schema parser that could claim false conflict detection.
5. Validate the candidate, review the complete diff, then commit its final source
   and gitlinks. Manifest generation intentionally rejects dirty checkouts, including
   untracked nonignored files and every dirty nested submodule.

An explicit `--baseline FULL_SHA` supports the next official update; review that
SHA's official provenance before using it. The CLI verifies that the full SHA is
available and is an ancestor of the candidate, and records the candidate commit
count. It does not independently establish that an arbitrary SHA is an official
release. Divergent selective ports require a reviewed descendant sync candidate;
this strict gate does not silently waive ancestry.

## Generate and verify the lock

Run from the final clean candidate checkout. Use a directory **outside** its source
tree for generated outputs. These examples use shell variables and retain the
current physical profile explicitly:

```sh
SOURCE="$(git rev-parse --show-toplevel)"
RELEASE_DIR="$(mktemp -d /tmp/dev-sp-release.XXXXXX)"
python3 "$SOURCE/tools/dev_sp_release/release.py" --repo "$SOURCE" manifest \
  --profile standard \
  --output "$RELEASE_DIR/manifest.json"
python3 "$SOURCE/tools/dev_sp_release/release.py" --repo "$SOURCE" preflight \
  --manifest "$RELEASE_DIR/manifest.json"
python3 "$SOURCE/tools/dev_sp_release/release.py" --repo "$SOURCE" stage \
  --manifest "$RELEASE_DIR/manifest.json" \
  --destination "$RELEASE_DIR/staged"
```

For a C3XL candidate, use `--profile c3xl`. Add
`--chestnut-road-size 1344x760` only when that model/camera combination requires
the calibrated road dimensions. The generated `dev-sp-boot-template.sh` always
uses `exec ./launch_openpilot.sh` from `/data/openpilot` and sets
`SUNNYPILOT_HARDWARE_PROFILE` explicitly. It prepends `/usr/local/venv/bin` to
the inherited `PATH`, matching the current C3 runtime so the official forwarding
chain into `launch_chffrplus.sh` resolves the installed Python dependencies.
`--venv-bin /absolute/runtime/bin` can select another reviewed device runtime;
the chosen directory is recorded as `boot_venv_bin`. Other inherited settings,
including PCIe configuration and timezone, remain available to the official
launch chain. It is a proposed device boot configuration,
not an installed boot override. The existing official launch flow reads the physical
profile and selects the relevant AGNOS manifest; verify that device configuration
separately before deployment.

To include model/runtime readiness inputs, repeat `--artifact` for **each** required
relative file and use `--catalog` for the selected catalog. Include chunk manifests
and every referenced chunk individually; the CLI does not infer chunk dependency
closure or claim a downloaded model from catalog presence. Paths may name ignored
local build outputs, but files must be regular files inside the checkout. External
artifacts must first be placed into the approved candidate artifact location.

```sh
python3 "$SOURCE/tools/dev_sp_release/release.py" --repo "$SOURCE" manifest \
  --profile c3xl --chestnut-road-size 1344x760 \
  --artifact openpilot/selfdrive/modeld/models/driving_supercombo.onnx \
  --output "$RELEASE_DIR/runtime-manifest.json"
python3 "$SOURCE/tools/dev_sp_release/release.py" --repo "$SOURCE" preflight \
  --manifest "$RELEASE_DIR/runtime-manifest.json" --rehash
```

The manifest records the baseline, runtime parent SHA, every recursive actual HEAD
and expected gitlink, effective LFS endpoint URLs from `git lfs env` (or explicit
unavailability), tracked file count, changed-file SHA256 and permissions, optional
runtime file SHA256/size/mtime/mode, catalog path and boot template. Changed gitlinks
include the current tracked contents of that dependency in the hash inventory.
Missing, uninitialized, mismatched or dirty dependencies fail explicitly; a populated
directory is not accepted as a valid submodule checkout.

LFS endpoint identity is a sorted, deduplicated URL list. Enumeration order and
remote labels are excluded, and trailing `(auth=...)` state is excluded because
credential-cache/session state can change independently of source identity.
A changed endpoint URL still fails preflight. Regenerate manifests created by an
older tool that stored raw endpoint lines before using this normalized check.

Manifest creation hashes requested runtime files once. Normal preflight rechecks
Git identities, cleanliness, metadata, pointer headers and changed files up to
64 MiB, avoiding repeated GB hashing. It is a quick source check, not a fresh
cryptographic verification of large artifacts: same-size corruption with preserved
mtime needs `--rehash`. Staging always performs full SHA256 checks before copying,
checks the copied bytes and permissions, and rechecks source afterward.

## Local staging and acceptance evidence

Staging copies the current recursive tracked source and explicit runtime files,
preserves relative symlinks that resolve within the source and all file permissions, and
adds the lock and executable boot template. It includes source metadata such as
`.gitmodules`; it does not include Git object databases or recreate a Git checkout.
Absolute symlinks are rejected even when their targets are inside source: copying
them unchanged would leave the staged directory dependent on the old checkout path.
The tool does not rewrite link targets or change their semantics.
The destination must not exist and must be outside source. Files are assembled in
a temporary sibling directory and renamed into place only after verification.
Failures remove the unpublished temporary directory. Producers using this tool
also take an exclusive destination lock; no other process should manipulate that
destination while staging. A crash can leave a temporary sibling or lock file;
inspect it before removing it and retry with a new destination.

A source-only staged tree may contain LFS pointers for files that were not requested
as runtime artifacts. Requested artifacts reject pointers and missing files. The
bundle is not automatically a compiled deploy image: compiled binaries, firmware,
LFS hydration, device paths and chosen model dependencies must be declared and
validated before a separate approved deployment procedure. The JSON explicitly
keeps `device` and `onroad` as `pending`.

Choose E2E gates from the changed dependency closure, not a fixed exhaustive test
matrix. A CAN/safety change needs its existing safety/vehicle integration gates;
a schema change needs generated consumers; a launch/profile change needs an
offroad startup session on each affected physical profile; a model loader/warp
change needs the chosen artifact hash, selected Params, actual modeld runner and
input/output/warp evidence. Preserve Official/Experimental/TN-NoDEC behavior and
the retained Tesla UI and ambient behavior. Store exact commands, identities,
machine-readable results and logs outside source. Source/build success, a model
selection UI, device startup, hardware inference and road acceptance are distinct
acceptance stages. Absent hardware keeps its acceptance pending.

## Repeatable E2E demonstration

Failure cases were listed in `tools/dev_sp_release/FAILURES.md` before implementation.
Run the executable demo against temporary tiny parent and nested-submodule repositories:

```sh
python3 tools/dev_sp_release/demo.py --output /tmp/dev-sp-release-e2e.json
cat /tmp/dev-sp-release-e2e.json
```

The demo invokes the real CLI with an explicit fixture baseline and produces JSON
evidence. It verifies clean recursive dependency locking, stage bytes and executable
permissions, existing/source destination rejection, missing/LFS artifact rejection,
permission regression, same-size/same-mtime corruption under `--rehash` and staging,
dirty parent/nested dependency rejection, uninitialized-submodule rejection, and
that generated files do not dirty source. Manifest and stage independently reject
an absolute symlink to an internal source file. It also executes the staged boot template
through an actual shell chain (`launch_openpilot.sh` to `launch_chffrplus.sh` to
`python3`) with competing host/venv executable stubs, checking that the specified
venv wins and the inherited PCIe setting survives. Only the device directory `cd`
is mapped to the temporary staging directory through a Bash function; the generated
script itself is executed unchanged. It creates no unit-test framework,
changes no live source refs and proves no device behavior.

The LFS regression uses a deterministic CLI Git wrapper only for `git lfs env`,
delegating every other operation to the real Git executable. It changes endpoint
order and auth state between manifest and repeated preflight, verifies those
changes are accepted, and verifies that a changed endpoint URL is rejected.
