# B model chain failure cases and acceptance, before implementation

Source: fixed tn 557c55b54d6da1ec78975735c9c602dca0e85c87; catalog da2d8dac5f77e3a6f72fefbfb14edea3555f05f6; runtime tinygrad candidate 69fd4d34d4430036378aba2b43f9d339cdd6ea73. D0 device exclusively owned by root. This draft changes no product source.

| Failure | Acceptance / E2E proof |
|---|---|
| Old bundle identity disappears after selector 20 -> 21 | All 14 previous Chestnut refs and all 77 QCOM refs map one-to-one to new catalog; selected ref and qcom/chestnut slot stay independent. |
| New plain bytes replace same-named D0 OOB/chunks | New full artifacts live beneath SHA256 directory; relative filename confined to model root. Old files/chunks and saved D0 Params remain byte-for-byte. |
| Interrupted or corrupt new download makes active model unavailable | Download temporary file, compare official SHA256, atomic replace only after success; existing valid file remains. Cancel/HTTP/hash failure must not write selected slot or delete old file. |
| Parsed catalog is used before new selected artifact is ready | Reconcile legacy slot by ref; change slot to v21 only after all new files validate. Preserve legacy raw until migration completes. |
| New runtime pretends to load old v27 OOB | Plain loader requires SPTGPLN1. Previous model identities run v28 recompilations. Old v27 bytes remain exclusively for D0 rollback. |
| Stock fallback OOB is rejected by plain loader | Explicit stock/native OOB adapter path uses new-runtime generated stock artifacts; default small works without a qcom selector slot. |
| Tinygrad Buffer/UOp/JIT API mismatch | Exercise actual PlainJit reconstruction + real registered model inference, stock small + DM + every actual warp resolution; no format-header-only claim. |
| Fused frame layout reads wrong NV12 offsets | Match pack_layout stride/height/size and transforms; two fresh camera frames plus recurrent state execute finite outputs. |
| Shader graph cache survives changed runtime/warp | Cache identity includes tinygrad source and extended/fused warp programs; cold and warm load execute finite outputs. |
| Model references/weights are mixed between runs | Record source SHA, runtime SHA, catalog SHA, selected ref, actual artifact hash, warp hash, dimensions, frame count, real USB+AMD device before inference. |
| Default or selected small outputs are non-finite | Existing finite check preserved for both big/small; invalid selected small triggers existing bundled fallback contract. |
| Chestnut init/inference fails and small model not ready | Actual standby small must instantiate and run; timeout/error changes published big state and output continues through small model. No hazardous physical fault injection. |
| DM artifact generated with old runtime is silently reused | Rebuild DM + luma warp at new runtime and perform real inference separately from driving proof. |
| Offroad warmup touches production Params or consumes USB concurrently | Warmup targets selected QCOM only; real device inference/root worker exclusive; fixed profile + isolated Params scope. |
| New download/clear-cache deletes v27 rollback objects | First migration cache purge disabled; D0 backup restore/hash and restart prove recovery independently. |
| Filesystem fills mid-download | Per-model storage admission; transfer/infer one model at a time on device; original D0 retained; no all-16-model device residency requirement. |

Required identity regression matrix: device original bundled big (stock runtime path, rebuild/compatibility explicit), LM, BMV6, CTM, CTMV2, CTV3M, MDM, MDMV3; stock small, selected QCOM model, DM, and Chestnut->small fallback. These model identities do not imply equal compiled bytes or driving behavior. Full catalog contains 16 Chestnut entries; unexecuted entries stay unverified.

Evidence split: host catalog/paths/download transaction and reconstruction checks; device real model inference and USB submissions; full live daemon/camera/fallback test; rollback and later road acceptance. Synthetic inputs through the real model prove inference only, not live camera or road behavior.

## Native default build follow-up, failure contract before the fix

- The original default big ONNX is SHA256 `6fee5937923c74848df4a63f6239eb6331c6274dd4bdb7a5d6ec0388a8b543d5`, 766018462 bytes, available via the official commaai/openpilot-lfs LFS batch endpoint. Its native `new_img`/recurrent-state graph is distinct from v28 CTMV2's historical queue export, despite their matching training checkpoint.
- A tinygrad bump must not retain the old NEXT_BUFFER big pickle or publish it under the new runtime identity. Register the original ONNX as a LFS source and give SCons a real Chestnut compile target; CI must build from this exact source. Root owns actual source download, native GPU compile, new output hashing and inference. Source, compiled bytes and catalog ref are recorded separately.
- A CI compiler path can disappear (`compile3.py` in the pinned runtime); exercise the real CLI and reject missing script paths. DM must use `compile_onnx.py --out-of-band`, matching the native loader.
- The CI matrix extractor can silently miss f-string catalog URLs and produce zero models; execute the actual workflow extractor against the fixed source and reject an empty or incomplete QCOM/Chestnut matrix. Catalog model download must verify its registered SHA256.
- Default big compile and warp targets must share the existing Chestnut flock/SCons side effect. A dry plan is insufficient: native compilation must run with exclusive GPU ownership and round-trip/inference evidence.
- Preserve stock ModelState/runner/default Params semantics. Do not replace native default with a legacy plain model solely because its checkpoint matches. The new native pickle must have persistent Buffer references rather than NEXT_BUFFER, correct original metadata/shapes, new runtime identity and real finite model output.
- Do not overwrite D0 or require the source ONNX to remain in a prebuilt runtime deployment. Keep source/object provenance recoverable for later builds and rollback, and admit temporary compile/runtime/model storage before transfer.

## Pending selector migration follow-up, before product correction

- A ready v21 Chestnut slot plus a retained v20 QCOM pick and an unavailable QCOM catalog must not enqueue the default small model. After the catalog recovers, download the retained ref, not an automatic default that overwrites the old selection. Exercise one actual manager tick with isolated real Params, then the real download/activation path.
- Desired legacy names and refs remain visible as preparing in both model settings UIs. Runtime selection, readiness, carrying-model indication and loaders remain strict v21; a saved v20 pick must not be advertised or executed as ready. After activation, preserve ref, display name, generation and 20 Hz flag.
- Content-addressed subdirectories contain the actual model bytes. Cache-size UI must count their files, preserving existing half-second caller throttles rather than walking on every render frame. The catalog migration E2E compares actual temporary file sizes.

## Native big compiler environment parity, before correction

The accepted original-6fee/TG69 compile and CI use OPENPILOT_HACKS=1. The local Chestnut ONNX compile must use the same model compilation flags; DEBUG is excluded because it controls diagnostic output. Execute the actual SCons compile_model command builder against a non-executing target collector and compare its flags with the actual CI big compile step. Record red before adding OPENPILOT_HACKS only to the big ONNX command; do not alter native warp flags or runtime. GPU compile proof remains the independently verified native output, not this command-generation gate.
