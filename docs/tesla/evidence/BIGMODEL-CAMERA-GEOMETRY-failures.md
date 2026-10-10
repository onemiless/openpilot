# Camera geometry failures before implementation

Target e40d859, dev-sp-chipmunk. Native bigmodeld responsibility only; other workers own IFE/Python camera configuration. No device work, commit or push.

- OX1928x1208 sampled with C4 K: incorrect principal point and focal length. Matching C4 dimensions must not substitute OS lens focal length for AR/OX.
- OX1344x760 full-frame IFE resize is nonuniform: fx=f*1344/1928, fy=f*760/1208, cx=672, cy=380. Treating fx=fy or scaling only principal point is wrong.
- Camera identity must come from actual per-stream cereal sensor metadata; resolution alone cannot identify the lens. Startup missing/invalid/stale metadata must send no frames.
- Native AR/OX1928x1208 and C4 OS1344x760 must retain correct geometry; unknown sensor/dimensions must fail closed and clear any previous geometry.
- Geometry changes must rebuild actual WarpLut pixel addresses; frame-header matrices must match the matrices actually applied to source pixels even when calibration changes.

Before production edits, add a native pipeline E2E that drives explicit sensor-family/size metadata into MetaProvider, both road/wide warps over patterned NV12 with padded stride, and wire-header roundtrip. Emit matrices and outcome JSON; cross-check emitted matrices against Python authoritative native K scaled per axis. Run existing C4 numerical/golden suites unchanged. New API initially fails to compile; preserve that expected baseline diagnostic outside the tree. The native E2E excludes hardware IFE/cereal process transport/phone inference, which remain integration checks.

## Implemented interface and local evidence

`CameraModel` distinguishes actual AR/OX sensor family from OS04C10; it is not inferred from dimensions. Each capture thread now subscribes to its own cameraState, requires alive+valid metadata, maps the generated cereal sensor enum explicitly, and combines that identity with the actual VisionIPC dimensions. Metadata missing/invalid/stale skips the frame before encoding-buffer acquisition. Unknown sensor/size skips that stream and logs the geometry once until recovery.

`camera_intrinsics()` accepts AR/OX1928x1208 or1344x760 and OS1344x760 only. AR/OX focal lengths2648/567 retain their original physical lens identity and scale separately by width/1928 and height/1208. Principal point is half the new frame size. C4 OS K is copied byte-for-byte from the existing constants. `set_camera_geometry()` caches per-stream K under the existing mutex, recomputes only on changes, clears rejected geometry to a zero warp, and continues to use the existing rpy update path. Capture stores the actually-used matrix with the frame; existing sender code copies that matrix into the wire header. Existing constructor defaults are retained for legacy C4 metadata/golden compatibility, but the production capture path never sends with those defaults before valid actual sensor geometry is accepted.

Local validation:

- New native E2E:6 road/wide geometry cases pass; padded-stride synthetic NV12 output agrees byte-for-byte with the direct warp oracle; metadata and serialized header matrices agree; unknown sensor/size fails closed and valid geometry recovers.
- Actual modified Python camera.py native configs and `_ife_road_camera` independently produce matching matrices; maximum absolute float32 warp difference3.052e-5, within the recorded6e-5/1e-7 tolerance. C4 native matrix comparisons remain byte-exact.
- Existing `test_bigmodeld`:660 checks,0 fails.
- Existing `test_warp_lut`:ALL PASS.
- Existing `test_warp_golden`:ALL PASS (tinygrad reference tie differences remain within its unchanged tolerance).
- Generated cereal enum names and SubMaster valid/alive APIs verified against current headers. `main.cc` is device-only and still needs target compilation/live transport validation by the parent; these host checks do not claim to execute its capture threads or hardware encoder.

Repeat native E2E from repository root:

```bash
clang++ -std=c++17 -O1 -Iopenpilot/selfdrive/bigmodeld \
  tools/tesla/bigmodel_geometry_e2e.cc \
  openpilot/selfdrive/bigmodeld/frame_meta.cpp \
  openpilot/selfdrive/bigmodeld/frame_codec.cpp \
  openpilot/selfdrive/bigmodeld/warp_pack.cpp \
  -o /Users/mile/work/tesla-port/c3xl-1344-20261010/bigmodel_geometry_e2e
/Users/mile/work/tesla-port/c3xl-1344-20261010/bigmodel_geometry_e2e
```

Artifacts outside source: `before-build.log`, `bigmodel-native.json`, `bigmodel-python-parity.json`, `c4-native-regression.log`, `c4-warp-lut.log`, `c4-warp-golden.log` under `/Users/mile/work/tesla-port/c3xl-1344-20261010`. No device operations, commits or pushes by this worker. Hardware IFE output, model rebuild, phone inference and calibration/trajectory acceptance remain integration checks.
