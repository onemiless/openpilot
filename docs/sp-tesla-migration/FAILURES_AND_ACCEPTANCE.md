# Tesla / longitudinal migration: failures and E2E acceptance

Written before product changes, 2026-10-04. Official base:
16322aef167fe14de8af28a9e437101ed3c4dac5. Feature source:
b6ceca145001958f88c686d57feac8c9e8a7073c. Ambient source is the actual
2026-10-04 dev-sp-8E5 worktree, whose selected files are hashed in provenance.json.

## Scope and failure cases

- Ordinary C3 incorrectly inferred as C3XL: loses DM/audio or gets wrong Panda/boot image.
- C3XL incorrectly inferred as standard: starts absent cabin/audio hardware or flashes incompatible boot partitions.
- C4 settings unreachable, traffic lamp absent, or copied C3 camera geometry used on C4.
- Tesla Params/flags/schema disagree between core and opendbc; mixed owners emit conflicting commands.
- OEM/ARS408/off radar selection ignored, wrong CAN bus accepted, stale observation used for control.
- Speed-limit sync overrides driver's manual speed setting or cannot resume correctly.
- Four-finger longitudinal switch conflicts with MADS or AP hybrid transition handling.
- Official/Experimental/TN-NoDEC unavailable, wrong solver ABI, tuning shared between backends, live mode change splits planner/controlsd.
- Traffic Off changes the base plan, red stop loses event continuity, stale green starts the vehicle, physical lead ignored at launch.
- Ambient linkage uses wrong side, resets duration every loop, transmits without fresh seven-byte source, exceeds 10 Hz/range/duration, or Panda rejects legitimate bounded frames.
- Ambient on/off and 0..100 day/night brightness settings not applied; dual blindspots suppress one side; night source stale.
- Web listener, console/settings URL, vehicle homepage dashboard survives scope removal.
- DM off only hides alerts while processes still run, or stops DM but triggers communication/process faults.
- DM off suppresses unrelated longitudinal, CAN, calibration, road camera or thermal checks.
- DM changes during onroad; enabled-on-C3 default or disabled-on-C3XL capability lost; reenabling leaves stale lockout state.
- Internal SPI plus external USB Panda, or internal DOS plus external USB, selects different boards for firmware confirmation and C++ runtime; propagate one verified serial through the startup chain.
- New model/compiler/tinygrad format mismatched; missing LFS/chunks, native runner fails, fallback loses valid model publication.
- Device experimentation occurs with ignition/controls active or switches to a partially built tree.

## Acceptance and artifacts

1. Source import/compile and dependency closure; explicit retention manifest for all Tesla features.
2. Existing route replay with matched inputs, three backends, native Cap'n Proto messages and solver outputs; produce JSON result and input/code SHA256 manifest.
3. Ambient CAN observation -> adapter -> actual bounded send -> compiled safety TX/RX check, covering off, both sides, day/night brightness, stale CAN and rate/duration limits; produce frame JSONL and summary.
4. DM lifecycle on C3/C3XL/C4: session-latched Params, actual process manager predicates and selfdrived event path; enabled default, disabled, reenabling, onroad edits, unrelated faults retained. Produce executable-check JSON evidence.
5. Offroad C3 172.16.1.210 identity, full native build and actual UI/settings/DM startup. Only start bounded synthetic replay/bench processes after fresh offroad/ignition/control gates. Capture process/message health and native build logs.
6. C3XL/C4 source/build coverage is separate from physical device acceptance; absent devices remain pending. Road acceptance remains pending after offroad verification.

No unit tests are to be written after implementation. Existing regression fixtures may be retained, but acceptance centers on repeatable end-to-end evidence. Do not claim static/source checks establish hardware or road success.

## Installation

The user authorizes a clean C3 software installation without preserving existing
runtime content. No OS/boot flash is implied. Install a complete separate source
runtime, verify its build, then switch /data/openpilot during an offroad window.
