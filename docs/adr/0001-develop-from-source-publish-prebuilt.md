# Develop from the source baseline and publish a prebuilt snapshot

Changes are maintained on the Source Baseline identified by each sunnypilot `dev` release message, then built into a separate Prebuilt Snapshot for deployment. The orphan, force-published `dev` history is intentionally not used as a merge or rebase base: it optimizes startup and distribution, while `master-dev` preserves reviewable source history.

The maintained source and device branch is `dev-sp-egpu`.  That exact published
channel is allowlisted as TICI-compatible in the build-metadata seam; arbitrary
development branches remain rejected by the upstream hardware/channel check.
A future prebuilt artifact must preserve the same source commit and channel
identity instead of renaming the maintained branch or globally bypassing the
check.

`dev-sp-egpu-nva` is the explicitly named, supervised NavAssist vehicle-test
channel. It may carry the same isolated C3XL profile while the feature is being
validated, but it is not a replacement maintained channel and must not broaden
the allowlist to arbitrary `dev-*` branches. Accepted NavAssist work returns to
`dev-sp-egpu` before the next maintained Prebuilt Snapshot is published.
