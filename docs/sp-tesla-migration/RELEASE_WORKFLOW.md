# dev-sp source sync and local release staging

This workflow preserves the existing Tesla feature set and produces a reviewable
source lock plus a local staged directory. It does not push Git refs, contact a
device, alter boot partitions, install a model, or prove vehicle acceptance.
The implementation uses only Python's standard library and the installed Git CLI.

## Start from an identified candidate

Record the worktree, `dev-sp` HEAD, dirty state and agreed remote/ref's expected
SHA (`R0`) before changes. Preserve unrelated work and published history; use
scoped commits on `dev-sp` under `AGENTS.md`. Never infer freshness from a branch
name or an old report.

1. Choose one continuous official source line. Resolve a release/build to its
   full source SHA, verify official provenance, ancestry and the actual merge-base
   against the previous source lock, and review equivalent/partially carried
   patches. Stop on unexplained divergence; do not merge orphan prebuilt trees.
2. Use `git merge` for routine mainline sync. Keep an optional model/runtime port
   as a separate checkpoint with fixed source and full dependency closure; it must
   not silently import unrelated control policies. For the mainline checkpoint,
   preserve custom gitlinks when that source has not advanced them; optional
   ports advance only their declared required dependencies.
3. Review parent and recursive dependency changes against
   `retained-features.json`: CAN/safety, control/session hooks, Params, schemas, UI,
   model/catalog/loader/warp, launch and physical profile. Remove a carried patch
   only after proving the replacement behavior equivalent.
4. Preserve published schema identities, field types/ordinals/tombstones, saved
   Params/defaults, backend IDs/enums and current model-selection semantics.
   Resolve conflicts at each owner and rebuild affected consumers; protocol
   redesign requires a separately accepted migration and rollback contract.
5. Prepare failure cases and E2E acceptance before product changes. Review and
   commit the complete candidate and gitlinks; manifests reject dirty parents,
   untracked nonignored files and dirty nested submodules.

Always supply `--baseline FULL_SHA` using this run's reviewed official source
SHA, including when producing an optional model checkpoint on top. Do not rely
on the CLI's historical default. Review provenance before using that SHA. The CLI
verifies that the full SHA is available and is an ancestor of the candidate, and records the candidate commit
count. It does not independently establish that an arbitrary SHA is an official
release. Divergent selective ports require a reviewed descendant sync candidate;
this strict gate does not silently waive ancestry.

## Generate and verify the lock

Run from the final clean candidate checkout. Use a directory **outside** its source
tree for generated outputs. These examples use shell variables and retain the
current physical profile explicitly. The official SHA below is the fixed source
for the first sync; select and verify it anew for every later run:

```sh
SOURCE="$(git rev-parse --show-toplevel)"
OFFICIAL_SHA="27c132984df60e9ef42ebd1a805738b8c851356f"
RELEASE_DIR="$(mktemp -d /tmp/dev-sp-release.XXXXXX)"
python3 "$SOURCE/tools/dev_sp_release/release.py" --repo "$SOURCE" manifest \
  --baseline "$OFFICIAL_SHA" --profile standard \
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
  --baseline "$OFFICIAL_SHA" --profile c3xl --chestnut-road-size 1344x760 \
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

Run the fixed core every sync: FAULT withdrawal, OEM AP/ACC handoff, human
override, traffic stopping, backend/session consistency, Params compatibility and
model fallback. Compare against a valid pre-integration baseline with fixed
inputs, relevant fields and declared tolerances; record intentional upstream
changes, never replace a golden to hide a failure. Add gates for the changed
closure: compiled safety/final CAN, generated schema consumers, planner modes,
UI/DM and each affected physical profile, or actual selected model/warp inference.
Use the target checkout's source and native dependencies, not another worktree's
editable installs. Store commands, identities, raw results and logs outside source.
The release CLI does not run these gates, compile binaries or discover all model
chunks. Host, offroad device, inference and road acceptance remain separate;
missing hardware or road evidence stays pending.

## Recoverable checkpoints and publication

Before integration, preserve source checkpoint `S0` with its recursive objects
using persistent refs or bundles, and prove they can be restored. Before device
changes, preserve `D0` from the actual active path/HEAD, dirty state and running
artifacts, not a rebuild. Lock root/recursive SHAs, catalog commit, model/chunk/warp
hashes, runtime and model-compiler versions separately, binary hashes/modes,
physical profile and selected Params/launch configuration. A source tag or the CLI
manifest alone does not preserve this complete device state.

Key model/warp cache entries by content hashes; derived artifacts also include
runtime/compile configuration in their identity. Verify temporary files before
atomic activation; preserve old usable artifacts and do not clear
the first migration's rollback cache. Do not overwrite an old model's cache entry
with different bytes under the same identity.

An accepted mainline checkpoint may be published separately if an optional model
port is deferred. Declare source/offroad experimental versus road-accepted status
explicitly. Before road testing, actually restore `D0` (or the explicitly accepted
later device checkpoint), restart and check health, then reactivate the same
candidate and verify it. Restore the complete source/dependency/model/warp and
relevant per-device Params/configuration; preserve calibration and identity.
A backup's existence or `git revert` alone is not a device rollback test.

Before a normal non-force publication, ensure every referenced dependency commit
has a persistent, remotely fetchable ref. Re-read the agreed parent remote/ref;
require its SHA to equal the current `R0`, stopping to re-evaluate unexpected
changes. Publish dependencies before the parent, then record the published parent
as the new `R0`; an independently published mainline checkpoint replaces the
original `R0` for later optional work. Keep original `S0`/`D0` recoverable. Do not
batch-push local experiment tags or treat a source push as device activation.

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


## 2026-10-22 source integration checkpoint

This round merges official source `f78c6c23773f4e6badcf62ee3ac222eb94c0eeb3`.
Catalog `a89041fcbc13582893f81971214ff4120795b1d4` adds optional TTM while
preserving CTM/BMV6 and both selected slots. Use this reviewed source SHA with
`--baseline`; the earlier first-cycle command examples remain historical.
Recursive locks and permanent `exp/20261022-sync/integrated` tags identify the
opendbc/Panda/tinygrad fork commits. Check `retained-features.json` for their
contracts; these source tags do not certify a device release.

The user explicitly deferred device testing in this round. Do not infer C3,
C3XL, C4, jiayi or UT3G runtime acceptance from host builds, software protocol
loopback, loader parsing or another device's earlier report. Stock native
small/DM/warp artifacts must be rebuilt for the new runtime, not copied from S0.

Panda's new simple-SPI host and old firmware are mutually incompatible. Before
any future device activation, close the matching host/application/bootstub/safety
build and rollback gates. Keep C3XL's profile-specific manifest and boot-chain allowlist;
AGNOS19.9 and Chestnut8516 must never implicitly flash a custom adapter.

CarParams mass normalization saves exact original bytes in
`SPCarParamsMassNormalizationBackup`. Before starting an older manager, export
that JSON and restore the original CP bytes, or restore the full S0 Params
snapshot. An old manager removes unknown keys; the new backup key alone is not
a rollback plan after the old manager has started. Normalization is idempotent,
and historical log migration uses the same unit conversion.


Official tracked assets use the upstream Hugging Face `.lfsconfig`; the fork-only
217304-byte Chinese font is a normal Git blob with its original SHA, under one
explicit `.gitattributes` exception. This avoids copying upstream model weights
into the owner's GitHub LFS quota on every sync. Check `git lfs env` for old
local/worktree URL overrides before fetching; never change another worktree's
storage configuration to repair this checkout.

Before a source-only push with `GIT_LFS_SKIP_PUSH=1`, prove every candidate LFS
OID/size exists at that fixed official download endpoint and verify a fresh
isolated `git lfs pull` plus full byte hashes. This skips redundant upload to
storage that already has the exact objects; it does not permit publishing missing
assets or writing to the upstream account. A new fork-only large asset needs its
own reviewed storage plan. Keep the closure proof and directly stored font in
the version snapshot. Source publication still does not authorize device activation.


## 2026-10-24 incremental source checkpoint

Merge official continuous source `8e740e0ac680d9a960489c04436a701dd491505c`
over S0 `268fbdd10237899c58a46e986539d0052a9105da`. This adds plain-model
compiler/loader/converter compatibility checks and opendbc RX frequency exemptions.
Use this full source SHA explicitly as the release CLI baseline. The new opendbc
integration is recorded in retained-features.json; preserve existing Panda and
tinygrad source locks, catalog a89041fc and both selected model slots.

Before product changes, rx_frequency_e2e reproduced 9/12 timely-input failures;
the candidate passes all 12 protocol/configuration combinations and still rejects
stale RX. Existing three-backend planner replay matches this round's S0 exactly.
Host model round trips, MOCKUSB+AMD conversion, native safety/control/session
checks and F4/H7 builds have separate JSON/JUnit/log evidence under
`/Users/mile/Desktop/mo-op/artifacts/dev-sp-sync-20261024`.

UT3G/jiayi bridge images and update policy are unchanged. Rebuilding Panda against
the new opendbc safety does not authorize flashing it. Device identity, matched
host/application/bootstub, physical inference/CAN/road and full D0 rollback
acceptance remain pending; previous device evidence does not qualify this source.


## C3/tici boot-chain correction (2026-10-24)

A standard profile does not make C3/tici compatible with stock 3X/four boot images.
The verified stock19.9 A-slot update failed before Linux with Unsupported firmware
detected on C3 80c4514b. Do not repeat that image set on C3.

C3 keeps the official19.9 system partition but uses mr-one/c3-dev
`1ec51c0e5ef0f7ab5e00ecc4edeb5b60a39d245b` abl/xbl/xbl_config/boot.
The independent agnos-c3.json and C3 allowlist pin those images; C3XL retains its
separate manifest and boot-chain guard; all profiles now target19.9. Both launch and background
updater use the selected manifest, with no C3 fallback to an unvalidated stock
boot chain. Corrupt/missing images or weakened A/B verification fail before IO.

The C3 selection failed in the pre-fix E2E. The corrected shell/updater/manifest
E2E passes23 cases and the existing AGNOS profile E2E passes16. QDL readback
verified all four C3 images on slotA; only mismatched abl_a and boot_a were written.
System/userdata/slotB were not rewritten during recovery. The device subsequently
booted actual AGNOS19.9 with the mr-one C3 kernel; runtime/build and road acceptance
remain separate. See artifacts/c3-dev-sp-update-20261024-80c4514b in the Desktop
workspace for the complete initial-failure and recovery evidence.


## C3XL system target correction (2026-10-24)

C3XL targets AGNOS19.9, including when an older launch environment inherits19.7.
Its independent manifest uses exactly the official19.9 system partition. The six
non-system entries and their mr-one allowlist remain byte-for-byte unchanged;
C3XL's SPI/H7 Panda, absent driver camera and audio capability policies are
already implemented and require no new device-specific path.

The updated E2E first failed seven cases against the19.7 configuration. Require
shell/profile/updater checks for19.7-to19.9, no reflash when19.9 is installed,
rejection of a missing/tampered manifest, and independent C3/C4 selection.
Host validation does not establish C3XL physical boot/SPI/camera/inference or
road acceptance; do not transfer C3's installed19.9 result to C3XL.
