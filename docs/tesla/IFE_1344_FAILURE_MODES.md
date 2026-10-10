# C3XL 1344x760 IFE port: pre-change failure inventory

Base e40d859dbbd4504ee866a897206f5e29aa262421, branch dev-sp-chipmunk. Reference is read-only mo-op-sp-dev-mac: a332a01b9be and original 2a69709f063.

- Changing advertised buffer geometry without changing IFE MNDS Y/UV registers corrupts output: compile/run actual scale header, assert input/output fields and independent X/Y phase values.
- C3/C4/cabin/RAW/BPS must remain unchanged: replay actual camera_open geometry selection with explicit C3XL profile + C3XL_IFE_ROAD_SIZE=1344x760 only, both road cameras, unknown values off, non-OX sensor off, wrong dimensions off.
- Anisotropic scaling must not apply horizontal scale to vertical AE geometry. Port existing separate fl_pix_y adjustment; prove scaled ROI remains in the visible frame.
- Aligned NV12 stride differs from visible width (1408 vs 1344): use actual buffer stride in scaled AE sampling, retain original unscaled branch.
- Keep sensor frame_width/frame_height/HDR/exposure/RAW mode values unchanged; only processed output changes.
- Preserve pre-existing no-scale register block byte-for-byte. Native header/config checks are not hardware proof.
- Parent must configure environment, physical camera intrinsics and model compilation consistently. No camera.py, bigmodeld, launch or model runtime edits by this worker; no device operation, commit or push.

Local replay outputs JSON containing profile matrix, compiled Y/UV register arrays and NV12 geometry. Device acceptance still requires camera output/stride/frame continuity, exposure stability and corresponding model artifact dimensions.
