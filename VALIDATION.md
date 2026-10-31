# Host validation, 2026-10-31 Asia/Taipei

Base: dev-sp `25742df9417a3559dba7cfa75183f7a3b13a0674` (remote queried before branch creation).
Branch: sp-flasher. No device contacted, installed, reset or flashed.

## Fixed single official big model

Light Speed Model v2 (October 29, 2026), LSMV2, generation 12.
Official catalog: sunnypilot/sunnypilot-models gh-pages `e001cd183c66e144cd09fcc11f5019cd6185f000`,
`docs/driving_models_chestnut_v28.json`, newest catalog index 19, built 2026-10-30T08:59:39Z.
Model ref: `c7cbe5de6a9dae4bab032bc5faeb24a248c41f8f`.
Model bytes: 798366549. SHA-256: `9f70c95b846428d36f2f31b570b9e4c78cd24196864464801eb58dc30b0b79f8`.
Official loader source: sunnypilot/sunnypilot `6f7a2c94c10dffcf9a83b120ab1e6985e4496868`.
Matching catalog tinygrad: `52e8c3e840b44de2ac9e98a0a1484fa09caf0064`, vendored with optional backends/tools removed.
Only one model file; no ONNX, camera warp, small model, driver monitoring or selector assets.

## Repeatable evidence

Evidence root: `/private/tmp/sp-flasher-final`.
Commands in README.md reproduce the evidence in a fresh directory.

- `spi/result.json`: 7 file/register/SPI E2E cases passed, including full 64-sector write, restoration and destructive-operation faults.
- `workflow/result.json`: 9 persisted-lifecycle cases passed, including same-connection restart behavior and reconnection with reused USB address.
- `integrated/result.json`: station called the real SPI write algorithm and actual post-reconnect verification against a simulated dock;
  three activated-full images match target, 64 erases total, temporary registers restored; inference boundary simulated.
- `inference/result.json`: 5 subprocess E2E cases passed using the actual inference entry, simulated GPU/tensors/clock.
  Covers success, NaN, transfer exception, GPU error state and wrong backend. Does not run actual model kernels.
- `package.json`: actual official plain model metadata parsed without GPU allocation; 269 shipped files hashed, all 105 GPU firmware hashes verified.
- `inference.py --check`: actual NumPy/libusb/LLVM symbols loaded on macOS, with
  `LLVM_PATH=/opt/homebrew/opt/llvm/lib/libLLVM.dylib` and `/Users/mile/Desktop/mo-op/.venv/bin/python`.
- Required AMD/CPU/DISK/NPY/RDMA modules imported without opening devices.
- `bash -n launch_openpilot.sh launch_chffrplus.sh` passed.

## Proof boundaries

These are host simulation and package proofs. There is no C3 runtime, R2 activation, real USB/GPU inference, numerical-reference or 60-second physical performance proof.
The production loader enables the official model's compile-time reference-frame check; the host tests do not execute it on a GPU.
No software power-cycle command is assumed: workflow waits for 12V+USB removal/reconnection before post-activation validation.
No AGNOS version is read or upgraded. Existing Python 3.11+, NumPy, libusb and AMDGPU-capable LLVM remain required; errors do not trigger installation or upgrade.
Model and microcode are bundled; inference firmware lookup reads local hash-verified files only.
Git LFS contains the single model asset; publishing must make that object available. Nothing was pushed.

Source provenance and exact shipped-file identities are in provenance.json and assets.json.
After local commit, evidence receipt.json records the source commit and artifact checksums.

## Offline runtime extension, 2026-10-31

Development base: sp-flasher `474947dd625a6850ff64c37e3a037485f4c6f546`.
No device, USB bridge, C3, SSH or ADB was accessed. No system package was installed or updated.

Bundled ordinary folders contain ARM64 CPython 3.11.15 (python-build-standalone 20260508), NumPy 2.2.6 cp311,
libusb 1.0.23, LLVM 19.1.7 for Ubuntu focal, fuser 23.3 and their userspace shared-library dependencies.
The payload is about 247 MiB. Original archives are pinned by URL/SHA-256 in runtime/sources.json;
licenses and 1,222 payload file hashes are shipped. No glibc or system loader is included.

Startup validates the payload before executing bundled code, probes system dependencies first, and uses local fallback paths when probes fail.
Probes run in separate processes so incompatible system LLVM crashes cannot poison a later fallback process.
Privilege elevation happens before selection, preserving the final interpreter/library environment for station and inference.
The final NumPy calculation and native probes revalidate the combined library environment.
`--check-runtime` stops after reporting dependencies and never imports station or enumerates USB.

Evidence root for this extension: `/private/tmp/sp-flasher-offline-final`.

- `runtime-flow/result.json`: 13 subprocess bootstrap E2E cases passed with simulated interpreters/probes and a fake station.
  Includes healthy system reuse, missing/broken system dependencies, corrupt payload, all candidates failing, fuser fallback,
  check-only mode, argument rejection and NumPy becoming incompatible after native-path changes.
- `runtime-elf.json`: 44 actual ARM64 ELF payloads passed architecture, symlink/dependency closure and required GLIBC-symbol checks.
  Highest required GLIBC is 2.30. All 25 compiler C API symbols used by tinygrad exist in bundled LLVM 19.
- `native-report.json`: actual host Python 3.12.13, NumPy 2.5.2, libusb 1.0.30 and host LLVM loaded through runtime.sh --check-runtime.
  NumPy computation and actual gfx1200 AMDGPU LLVM compilation passed. A version-only fuser fixture substitutes for macOS fuser's different CLI.
  This is macOS dependency-probe proof, not execution of bundled Linux ELF files or GPU inference.
- Fixed-archive rebuild into `/private/tmp/sp-flasher-runtime-reproduced-2` produced byte-identical SHA256SUMS to runtime/SHA256SUMS.
  `tools/build_runtime.py` reproduces the payload; it is a development tool and is never called by startup.
- Existing 7 SPI cases, 9 lifecycle cases, station/SPI integration, 5 inference-entry cases, package hashes/model metadata,
  and all launcher syntax checks passed again. Package verification now covers 1,494 shipped files.

Linux ARM64 binary execution was not performed: this host has no running Docker backend and Virtualization.framework reports unsupported.
Static ELF closure plus macOS probes cannot establish C3 ABI compatibility or true USB/GPU behavior.
An older incompatible glibc remains an actual loader limitation; no AGNOS version gate or upgrade is added.
The fixed LSMV2 model and flash algorithm are unchanged. Nothing was deployed or pushed.
- Additional offline Git-index/local-LFS checkout E2E passed all 1,222 payload hashes in
  `/private/tmp/sp-flasher-offline-final/git-checkout`. Runtime vendor bytes disable Git text normalization;
  original upstream whitespace is preserved rather than rewritten. No LFS download was performed.

## First C3XL device test, 2026-11-01 Asia/Taipei

Tested product source: `940109dcb9b83d1302548d460edf9dcf6274b2c1`.
User explicitly authorized parked/offroad/disengaged exclusive testing on 172.16.1.202.
Device hostname comma-9c13c9f5; AGNOS label 19.9, glibc 2.39, kernel 4.9.103.
Existing /data/openpilot remains xpilot `ae189b2e594c922b60f3892e0efc167655e49551`.
Payload ran from /data/sp-flasher-test-940109d; no system update or active checkout replacement.

Actual ARM64 runtime check PASSED: missing system NumPy caused selection of bundled Python 3.11.15 + NumPy 2.2.6.
System libusb 1.0.27, LLVM 20 and /usr/bin/fuser were reused. Actual gfx1200 LLVM compilation passed.
A transfer exclusion accidentally omitted runtime/tools/fuser; the fixed artifact was uploaded before full runtime checksum/preflight passed.

Flash E2E FAILED before erase/program. Dock: 3801:0001, custom 8516b768-CLEAN, USB 5000 Mbps,
JEDEC three reads 854012, UID three reads 4250304833343816113545184c028278, initial SPI status 1c0020.
First two 256 KiB backups match SHA-256 `628498e6b7847fbaae3f789c303a02a560b681d54bbd2fe31a923351de85171e`.
Third backup failed with OSError(71, Protocol error); cleanup also failed. result.json reports
persistent_attempts=[], completed_sectors=[], controller_restored=false, protection_restored=false.
No target image was written; 60-second inference was NOT_RUN. Kernel confirms E4 control read -71 and USB descriptor/reset errors.
This establishes a real transport failure, not its firmware/cable/host root cause.

The test service was stopped without retry. User disconnected both 12V and USB and reconnected the dock.
New kernel disconnect/enumeration events observed despite reused USB devnum 2. Read-only E4 checks then confirmed
CC33=0, C805=2, CA81=14, C8A6=4, matching the original four key values; product and USB 5000 Mbps restored.
Other register restoration and post-boot complete Flash contents were not independently re-read.
Both comma.service and sp-flasher-test-940109d.service remain stopped. No product code was changed during this test.

Device evidence: /data/sp-flasher/1683d293-27a9-4cbb-9040-043a42aa4f7f.
Host evidence: /private/tmp/sp-flasher-device-20261101, including raw backups, kernel log, runtime JSON,
recovery read-only script/results, receipt.json and SHA256SUMS.

## Follow-up diagnosis and complete C3XL E2E PASS, 2026-11-01

Product source stayed at `940109dcb9b83d1302548d460edf9dcf6274b2c1`; only temporary diagnostic scripts were used.
After the preceding full physical power cycle, six instrumented and three uninstrumented read-only sessions each completed
three full 256 KiB backups. All 27 match SHA-256 `628498e6b7847fbaae3f789c303a02a560b681d54bbd2fe31a923351de85171e`.
Every session restored controller/protection state and issued no persistent SPI operation.
The previous USB -71 was not reproduced. Fixed third-read failure and a fixed short timeout are unsupported by these trials;
firmware/cable/host root cause remains unresolved. No speculative delay, retry or product-code fix was added.

A subsequent controlled complete workflow on the same board reached DONE:
- Job: `/data/sp-flasher/1ff7d5f3-4487-4532-80fc-d538d80e1e5e`.
- All 64 sectors erased, order 1..63 then 0. Recorded SPI operations: 64 erase, 768 program, 2 volatile WRSR.
- Three pre-write images match the original source. Three post-write and three post-power-cycle images match the target.
- Target SHA-256: `d1234f6ecef4f3976a7c6e082a59f1bcf6848c75298bd70607fc2f62d9f83ce0`.
- Target wrapper bytes match bundled R2 SHA-256 `6c82e3add05b668f093dbe74282c92405b834989627c7af8201a81ccd23abcde`.
- Original first 256 bytes and all bytes from 0x17FE0 preserved; volatile-register and protection restoration reported PASS.
- User physically removed both 12V and USB before activation. Same-board UID and all three activation readbacks passed.
- Official single LSMV2 big model, real USB+AMD:LLVM backend, finite output and plan present.
- Warmup/loading: 32.064014902 s. Sustained inference: 60.055451302 s, 429 runs, 7.143398155 Hz.
- Mean 139.956684 ms, P95 145.933468 ms, maximum 151.562258 ms. Synthetic model inputs; no camera/warp/driving processes.
- Inference subprocess exited normally and station reached DONE with flash=PASS, activation_readback=PASS, inference=PASS.

The inference test synchronizes/copies outputs and recurrent state, so this is not driving-loop throughput proof or a 20 Hz claim.
A successful second workflow does not establish that the original intermittent -71 has been fixed.
Test service sp-flasher-test-940109d-round2 was stopped after DONE; comma.service remains inactive.
Original active checkout ae189b2e594c922b60f3892e0efc167655e49551 and AGNOS 19.9 were unchanged. No push or normal startup replacement.

Host evidence: `/private/tmp/sp-flasher-device-round2-20261101` contains nine raw diagnostic sessions, both flash jobs,
request-tail traces, 27 stability reads, final images, inference/runtime JSON, kernel log, receipt.json and SHA256SUMS.
Host independently checked every target/readback image, board-data preservation, the embedded wrapper and job hashes.

## Dedicated screen, 2026-11-01

Added a separate read-only display process. It uses libdrm CPU scanout and the existing magic.service DRM descriptor handoff,
without starting SP UI, cameras, vehicle control, a compositor or a USB client. A 240-glyph Noto CJK raster atlas is approximately
115 KiB compressed; OFL license and source-font SHA-256 are shipped. ARM64 libdrm 2.4.101-2 is an offline fallback.
The C3XL native 1080x2160 buffer uses clockwise 90-degree image rotation for the physical landscape panel.

Station waits for the first displayed frame before any tick/USB discovery. Display startup failure prevents flashing;
the independent process continues to read state/events while station performs blocking work. Inference now publishes atomic
LOADING/RUNNING progress approximately once per second, FAIL on errors, and PASS after the timed loop.
Child PASS while its process is still exiting is shown as closing, not overall success. DONE requires all three parent PASS flags.
The final screen's “准备下一块” text was removed at the user's request; “可移除底座” remains.

Host evidence root: /private/tmp/sp-flasher-screen-final.
- 16 actual reader/renderer CLI lifecycle snapshots passed, including partial event tails, corrupt input, false DONE,
  underlying inference errors and 60-second progress. Each emits PPM, JSON and checksums.
- Actual station startup with a display subprocess and mocked tick passed readiness and failed-readiness cases; no USB access,
  and display subprocesses were reaped in both cases.
- Five inference-entry E2E cases passed; actual progress writes include LOADING -> RUNNING -> PASS and retain FAIL on errors.
- Existing nine lifecycle cases, station/SPI integration, seven SPI cases, thirteen runtime selection cases and package verification passed.
- 45 ARM64 ELF files passed architecture/ABI/dependency checks; runtime rebuilt from locked archives with identical payload hashes.
- Package hashes now cover 1,503 files. No system upgrade or network installation is reachable from startup.

Device proof: independent sp-flasher-status-screen.service displays the prior real DONE job from
/data/sp-flasher/1ff7d5f3-4487-4532-80fc-d538d80e1e5e. No station/flash/inference task was started during screen validation.
System magic.service remains unchanged. Initial panel rotation was reversed after user feedback; user confirmed corrected orientation.
User then requested removal of the next-board wording, which was applied on device. device.ppm/device.png and device.json
are read back from the actual mapped scanout buffer, not a photograph. Captured pixels and JSON show the final requested wording.

Current screen remains visible via the display-only test service; comma.service and both flashing test services stay stopped.
The active /data/openpilot checkout/normal boot entry was not replaced. Full physical flashing with the new screen-integrated code
was not repeated; prior R2 + 60.055-second GPU PASS remains proof for product commit 940109dcb9b83d1302548d460edf9dcf6274b2c1.
The previous intermittent USB -71 root cause remains unresolved.

## Installer distribution gate, 2026-11-01 (in progress)

Initial normal push was rejected before publishing any ref: GitHub reported the repository exceeded its LFS budget.
Current installer distribution therefore uses twenty ordinary Git parts, each <=45 MiB, rather than LFS pointers.
The original model/LLVM bytes and hashes are unchanged; local complete targets are ignored/generated files.
prepare_payload.sh validates shipped parts, concatenates to temporary targets, verifies complete hashes and atomically replaces them.
It reuses existing correct targets and performs no download/installation. Missing or corrupt data stops before runtime/station.
Five local materialization scenarios and thirteen existing runtime-selection scenarios passed.
An offline checkout of only current staged ordinary Git files reconstructed the complete model/LLVM and passed all 1,225 runtime hashes.
The current staged tree contains no LFS pointers. GitHub also rejected historical unknown LFS objects (GH008), so the initial publication cannot include that unpublished commit chain.
The complete local development history is retained under refs/archive/sp-flasher-pre-installer-20261101 and in a local Git bundle.
The public release snapshot uses the existing dev-sp base as parent and has the same current product tree, with no new LFS pointers.
Installer fresh-clones that ordinary-file tip at depth 1.
Package/model verification passed. Real installer and xpilot restoration evidence will be recorded after device execution.

## Real installer PASS and original xpilot restored, 2026-11-01

Published functional snapshot: `fa27df1c4d0e992e40666a3841fe6e420580c077`, onemiless/openpilot:sp-flasher.
Installer URL: https://installer.comma.ai/onemiless/sp-flasher. Device setup source explicitly expands the shorthand onemiless/sp-flasher.
Actual installer downloaded with AGNOSSetup-19.9 / tici headers; ARM64 ELF, 2,051,392 bytes,
SHA-256 `dd040f97393b77c2cd32d4f0f6df32f05ffb1ba699bdb31ecde4e76568a83017`, with expected repository/branch strings.

No factory reset was performed. Original /data/openpilot, exact continue.sh, flasher state/data and protected parameter snapshot were
preserved before executing the actual downloaded installer. It fresh-cloned the published branch at depth 1 into its normal paths,
checked out the exact expected commit, initialized zero submodules, and generated its standard /data/continue.sh.
The new checkout initially had no complete model/LLVM targets: prepare_payload.sh reconstructed both from ordinary Git parts with
full-file SHA-256 checks. Current tree has no LFS dependency, avoiding the repository's exceeded LFS budget.

The generated continue.sh was executed as comma under a temporary USB-isolated test unit, which hid bridge enumeration and access.
That isolated only the test service, not product code or the system USB configuration. No new flasher job directory was created.
Actual installed station and status_screen processes ran from /data/openpilot; bundled Python 3.11.15 + NumPy 2.2.6 selected,
system libusb 1.0.27, LLVM 20 and fuser reused. Full asset preflight passed.
After installer exited successfully, active DRM framebuffer ID 210 was read back (no modeset): pixels exactly matched the expected
“等待底座接入” canvas. This proves display takeover survived installer exit, not merely that a screen process existed.

Both installer/app test units were stopped. Original xpilot directory and exact continue.sh were restored, including the c3xl profile
and BLOCK=modem exports. The verified temporary installed checkout was removed; free /data space returned to approximately 5.5 GiB.
Normal comma.service startup first entered the stock tap-reset UI because /tmp/booted was initially absent and the touch count was high.
It was stopped without executing reset. The normal boot marker had been created; a second normal start correctly entered xpilot.
No reset marker exists and original files/parameters remain intact.

Final live proof:
- xpilot HEAD: ae189b2e594c922b60f3892e0efc167655e49551, same original status `?? prebuilt`.
- continue.sh SHA-256: 80be31fcf7e5b3b1f0ff9745d26ce6839af4f4c8d20d38390c5b9291a5bc7fc7, exact original.
- comma.service active; original manager, openpilot.selfdrive.ui.ui, pandad and hardwared running from restored tree.
- Manager environment SUNNYPILOT_HARDWARE_PROFILE=c3xl; offroad=1, engaged=0; AGNOS 19.9 unchanged.
- AdbEnabled, GithubSshKeys, GithubUsername, OpenpilotEnabledToggle and SshEnabled hashes unchanged.
- Only normal boot/updater uptime/cache metadata changed. No user model choice/config change was made by the flasher test.
- Original xpilot reports model-catalog ConnectionResetError and uses its cached data; this unrelated refresh issue was not modified.

Host evidence: /private/tmp/sp-flasher-installer-20261101, including the actual installer download identity, test stages,
installed preflight/runtime/processes, active-frame PPM/JSON, restoration proof and source-history archive bundle.
Protected raw parameter backups stay on-device, not in the exported evidence. Earlier USB -71 remains unresolved;
this installer test did not repeat firmware flashing or GPU inference. Full prior device E2E proof remains in earlier sections.
