# Implementation gates (written before implementation)

- No system version read, AGNOS updater, manager, driving, camera or OTA may be reachable from either launcher.
- No gitlinks, .gitmodules, runtime downloads, dependency installation or source-tree Git queries.
- Missing/corrupt model, R2 or runtime assets: no erase/program.
- Different UIDs/serials/source firmware are accepted; unsupported SPI semantics and unstable reads fail.
- Backup three times, fsync, rewrite all 64 sectors (zero last), verify sectors and three full reads.
- Short USB transfer, SPI busy, lost PROGRAM ACK, erase residue or read corruption: fail without write retry.
- Service restarts during writing: mark interrupted, never resume uncertain erase/program or reflash that connection.
- After write, same connection must not trigger inference or another flash. Persist waiting state over restart.
- Reconnect can reuse USB address. Observe absence or a new enumeration identity. Board UID and full image must match before inference.
- Different reconnected board: fail without writes/inference, require removal before starting a new job.
- Activation check does not erase/program. Flash and inference statuses remain separate.
- Fixed model must use USB+AMD:LLVM, synchronize actual outputs, validate finite outputs and plan slice, carry recurrent state.
- Model loading and warmup excluded from the 60 second measurement. No CPU fallback or Hz performance gate.
- Inference error/NaN/timeout must never produce overall PASS. Record error and checksums.
- Finished/failed connection cannot be reflashed on process restart; removal/new enumeration permits next job.
- Host simulation is never device proof. No test opens USB or connects to a device.

## Offline runtime (before implementation)

- Missing/old/broken system Python must select bundled ARM64 Python without invoking apt, pip, uv or a downloader.
- Compatible system Python + NumPy are reused; a missing/incompatible NumPy may only use the bundled cp311 wheel with Python 3.11, otherwise use the bundled interpreter.
- Import success alone is insufficient: perform a finite NumPy calculation, libusb symbol/API-version probe, and actual AMDGPU LLVM kernel compilation without creating a USB context.
- An absent/crashing/incompatible system native library is probed in a child and falls back to the local copy. No cross-ABI mixing of NumPy or host architecture libraries.
- Probe LLVM with the actual selected NumPy and libusb paths; revalidate the complete combination in a fresh child before starting the station.
- A corrupt/missing bundle file, wrong ELF architecture, missing DT_NEEDED library, or too-new GLIBC symbol prevents startup before USB enumeration/writes.
- Bundle Python and native libraries are fixed artifacts with licenses and hashes; never bundle/replace glibc or a system loader and never write /usr, /lib or OS version files.
- Startup must work without system Python and without fuser on PATH. Privilege elevation occurs before dependency selection so sudo cannot discard the chosen library paths.
- Check-only startup prints interpreter/NumPy/native-library identities and exits; it cannot import station or access USB/sysfs.
- Both system and bundled candidates failing must return nonzero and retain errors; no infinite installation loop, downgrade or system update.
- Child environment and interpreter selection must be identical for station, preflight and inference; no later implicit return to system python3.
- Host E2E uses a fake station entry; real station.py and flash device entry must never run on host.
- Git text normalization, LFS pointers and symlinks must not alter payload bytes after a fresh offline checkout.

## Dedicated screen (before implementation)

- Screen never opens USB, imports station or starts flashing; preview/device display-only invocation cannot mutate job state.
- Waiting, preflight, backup, 64-sector progress, final readback, power-cycle instructions, activation check, model loading, timed inference, closing, success and failure must all be visible.
- Missing state means waiting; corrupt/non-dict JSON, unknown stages and invalid result files cannot display success.
- Atomic writer updates and partial JSONL tails must not crash the reader or fabricate progress.
- DONE requires all three PASS flags. Child inference PASS while parent still running is not overall DONE.
- Chinese glyphs and ASCII errors must render without missing glyphs; long paths/messages wrap within the canvas.
- Display runs separately so blocking erase/program/inference cannot freeze updates. No disk snapshots in the flashing hot path.
- Display readiness is required before the first station tick; failure to acquire/draw the screen prevents blind flashing.
- Borrow existing magic.service DRM descriptor via its supported local socket when present; no system service replacement.
- Correct native portrait-to-landscape rotation and pitch, visible backlight; restore previous CRTC and close display resources on exit.
- Screen exit/crash cannot cause a flash retry. Parent owns display lifetime; display-only validation uses real prior DONE data only.
- Host E2E emits repeatable PPM and JSON snapshots; device proof records an actual mapped display frame without touching the bottom dock.

## Installer payload without LFS (before implementation)

- GitHub LFS quota exhaustion must not yield a published branch whose current checkout contains pointers instead of executable data.
- Current installer checkout must consist entirely of ordinary Git files under the per-file upload limit; preserve earlier local source history.
- Reconstruct only fixed targets from shipped parts, using system SHA-256 tools before Python/LLVM use. No network/apt/pip/uv.
- Existing valid targets are reused; corrupt targets are replaced only after all part and assembled hashes pass. Partial temporary files cannot become active.
- Missing/corrupt/reordered parts must fail before station/device discovery; raw originals remain available locally and in device backups.
- Fresh offline index checkout must reconstruct exact model/LLVM hashes and modes using only tracked current files, with LFS disabled.
- Real installer test preserves original xpilot directory, continue.sh, parameter snapshot and flasher state before installing; restore even on failure.
- Device must have no dock connected while proving fresh flasher startup, so installation cannot cause another erase/program.
