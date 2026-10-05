# Model readiness: failures and repeatable acceptance

Failure cases recorded before implementation:

- Catalog changes the assembled-file SHA while keeping the same chunk metadata.
- Activation resets assembled-only bundles despite the loader accepting the complete base.
- Valid chunks mask a corrupt or pointer base that the loader actually prefers.
- Chunk/manifest symlinks escape the model root despite a safe artifact base path.

- Loader accepts a fully assembled artifact but readiness still requires its old chunk manifest.
- Selected artifact escapes the model directory via absolute paths, parent traversal or symlinks.
- Oversized manifest counts cause an unbounded periodic file scan.
- Stock modeld imports selector internals or a selected bundle changes its default-only gate.
- No selection, malformed selection or stale selector version loses the existing default fallback.
- Empty bundle or a missing artifact/hash silently passes an all([]) check.
- Missing, empty or Git LFS pointer files are reported compiled.
- A manifest exists but is malformed, zero/negative, incomplete or disagrees with selected chunk count.
- Downloaded chunks exist without the loader's manifest, or disappear after an earlier ready check.
- Either stock Chestnut warp is missing or a pointer while the selected model is marked ready.
- QCOM selection contaminates the independent Chestnut slot.
- Tinygrad runner alone overrides the UI readiness result.
- UI and hardware uncompiled alerts disagree; ready is mistaken for active inference.
- Every UI refresh hashes gigabytes or caches readiness across file deletion/selection change.

Acceptance uses the actual Params, schema, readiness helpers, UI parameter-update/state
methods and ChestnutStatus alert flow with temporary files. It does not send CAN,
access a device, compile a real model or establish onroad/USB/inference acceptance.
Run from the repository root:

```sh
PYTHONPATH=. /Users/mile/Desktop/mo-op/.venv/bin/python tools/sp_tesla_e2e/model_readiness_e2e.py --output artifacts/model-readiness-e2e.json
```

The JSON records each scenario, default gate, selected gate, UI state and hardware
uncompiled alert. Repeat execution recreates its fixtures. Download/activation owns
SHA verification; readiness checks local nonempty files/LFS headers and manifest
completeness, not model ABI, metadata integrity or cryptographic content validity.

The loader prefers a complete base file over its manifest. Readiness follows that
priority, including assembled bundles originally described as chunked; a base LFS
pointer remains rejected even with valid chunks beside it. Selected paths must stay
inside the model root after symlink resolution. Manifest scans are capped at 1024
chunks (about 45 GiB with the current chunk size); raise the cap only when a larger
model is explicitly supported.

Actual activation checks run through `validate_active_bundles`: assembled base files
use the aggregate download SHA; base absence requires the declared manifest count
and all declared chunk SHAs. Both paths share the readiness file/path selection,
while only activation hashes content. The catalog comparison includes both aggregate
and chunk SHA metadata. Activation retains its existing once-per-selection cache;
E2E fixtures change selection refs to request fresh validation for each scenario.
