# Develop from the source baseline and publish a prebuilt snapshot

Changes are maintained on the Source Baseline identified by each sunnypilot `dev` release message, then built into a separate Prebuilt Snapshot for deployment. The orphan, force-published `dev` history is intentionally not used as a merge or rebase base: it optimizes startup and distribution, while `master-dev` preserves reviewable source history.

The maintained source channel is `dev-sp-egpu`. A reviewed feature/device branch
may also be named explicitly in the C3XL compatibility allowlist while it is
validated against that source lineage. Arbitrary branches remain rejected; the
hardware/channel check is never globally bypassed. A future prebuilt artifact
must preserve its exact source commit and explicitly allowlisted channel
identity so a baseline sync cannot silently make the active device offroad-only.
