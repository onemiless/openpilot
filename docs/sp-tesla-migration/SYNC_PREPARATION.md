# dev-sp synchronization boundary

The validated C3 source checkpoint was captured before this preparation in three
commits: d830fe6727 (model/warp/availability), a332a01b9b (road scaling), and
c1feb88734 (BMS UI). They preserve the previously deployed dirty implementation.
This preparation does not merge a newer upstream revision or deploy to the device.

Use retained-features.json to review dependency closure, and RELEASE_WORKFLOW.md
for the executable source-lock/staging process. Published dev-sp history is merged
through a temporary sync candidate; do not rewrite the branch used by a device.
The fixed 16322aef baseline was ahead of the inspected official master by124 commits.
Future candidates must be chosen by reviewed lineage and runtime compatibility.

## Repository setup

Run `git submodule sync --recursive` and `git submodule update --init --recursive`
in a fresh candidate. The root gitlinks are the dependency lock. Child fork
commits must be reachable on the configured remotes before publishing a parent
commit that references them. Check a fresh recursive clone using remote object
stores; an existing local object cache does not prove remote availability.

Git LFS endpoint configuration matters: .lfsconfig points at the official
Hugging Face store, whereas this workstation has a local LFS override to the
owner's GitHub repository. The release manifest records the effective endpoints.
Do not silently rewrite global Git configuration or assume the effective store
is the one printed in .gitmodules. Publish required custom LFS objects to the
chosen release store and verify hydration in a fresh checkout.

Two former dirty files (Chestnut icon and stock driving ONNX) were verified to
match HEAD's LFS object IDs exactly and normalized without a code change. Actual
font changes are versioned; use FONT_BUILD.md to reproduce them. /artifacts is
local output/evidence, explicitly ignored, never a hidden source dependency.

## Scope and follow-up gates

Runtime readiness now has a public selected-model owner; stock modeld remains
independent. Updates for tici use one explicit branch policy including dev-sp.
No silent no-op tuning adapter was added: configure_runtime_tuning is a maintained
contract listed in the feature manifest; upstream MPC changes require review of
that hook and the existing longitudinal replay, not automatic weakening of tuning.

Panda DOS/F4 compatibility and opendbc Tesla safety remain separate dependency
patches. Their vendor header line counts are not a reason to rewrite working
firmware during this preparation. No CAN/safety/DM behavior or official Chestnut
power code was changed here. Cap'n Proto fields require explicit semantic review;
the CLI does not pretend a partial regex parser proves schema compatibility.

A clean source lock and successful local staging do not prove a deployed image.
Artifact completeness, executable permissions, real launch PATH, offroad startup,
and relevant device/road gates remain required for the next release. New changes
in this preparation have source/integration E2E evidence only until deployed.
