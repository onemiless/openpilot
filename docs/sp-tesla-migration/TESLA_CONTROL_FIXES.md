# Tesla control fixes — failure checklist written before implementation

Baseline: parent `91a9dacb0cdd29372d0742f79d1ec3a95bbc6332`, opendbc
`e15d18898f046e569f3e8d1a1415fa25d62c4508`. No physical CAN, device access,
network access, firmware flash, commit, or push is part of this work.

## Required failures and preserved behavior

- F02: manualStock, dynamicStock, and AP hybrid must not suppress a real
  DI_cruiseState=FAULT. A fault must terminate software ownership and send only
  zero-acceleration cancel / inactive steering, even when the latest carControl
  still requests active acceleration and steering. Do not acquire SP control
  as a consequence of a fault. Preserve accelerator override, pedal/fault events,
  and the existing non-fault handoff behavior.
- F03: carOutput must report the final steering command and longitudinal
  acceleration emitted by the controller, including cooperative steering and
  the stock-to-SP ramp. Retain the last emitted command on non-TX frames.
  Standard accel/curvature/torque fields must never carry angle debug values.
- F04: ARS408 must not transmit a default-zero yaw measurement during turns.
  Prefer a documented numerical Tesla CAN signal. If unavailable, explicitly
  estimate from measured steering and speed using the existing VehicleModel;
  check left/right, standstill, reverse, invalid CAN, and nonfinite inputs.
  The historical ARS408 wire sign is a software contract; physical sensor
  mounting/sign verification remains pending.
- Remove 0x082/0x3FD/0x370/0x399 TX permission and ineffective checks, since no
  production transmitter exists. The only remaining accessory TX permissions
  are automatic speed wheel 0x3C2, blindspot ambient 0x679, and ARS408 motion
  0x300/0x301 when configured; preserve core Tesla steering/longitudinal/AEB.
- Remove normal-card consumers of retired Web validation Params. Merely setting
  old request Params must not produce 0x3E9 or a manual red-light test. Ambient
  blindspot processing must run independently of the removed validation object.
  Preserve fresh-template, brightness, rate, duration, and safety checks.
- Consolidate Tesla startup configuration explicitly through the parent adapter
  without changing which settings are session-latched. Avoid an openpilot import
  inside opendbc and preserve capability flags. Do not silently live-reload
  startup speed thresholds, AP modes, or touch switching.
- Delete unused duplicate enums and the uncalled jerk experiment. Do not add
  new FSD/diagnostic TX behavior or a parallel control implementation.

## Reproducible offline acceptance

The entry point is `tools/sp_tesla_e2e/tesla_control_chain_e2e.py`. It feeds
synthetic CAN through actual Tesla CI/CarState, applies actual controls, decodes
the emitted frames, and calls freshly compiled Tesla safety hooks. It writes
the case results, source SHA-256 identities, import paths, and revision hashes
to the requested JSON artifact. Assertions run before any implementation edits
to capture the failing baseline. It is an offline integration check, not road
or physical-vehicle acceptance.

```sh
PYTHONPATH="$PWD/opendbc_repo:$PWD" /Users/mile/Desktop/mo-op/.venv/bin/python \
  tools/sp_tesla_e2e/tesla_control_chain_e2e.py \
  --output artifacts/sp-tesla-migration/tesla-control-chain.json
```

Pass status, final source hashes, remaining limitations, and any repaired
existing checks are recorded below after implementation.

## Implemented behavior and evidence

The baseline run produced four expected failures in
`artifacts/sp-tesla-migration/tesla-control-chain-before.json`: a swallowed real
FAULT, a final-angle/output mismatch, zero yaw during a modeled turn, and
permitted obsolete 0x3FD TX. The updated entry point passes five integrated
groups and records current source hashes in
`artifacts/sp-tesla-migration/tesla-control-chain.json`.

- F02: each of manualStock, dynamicStock, and apHybridStock is exercised for six
  consecutive encoded synthetic CAN FAULT samples. `accFaulted` and accelerator override
  events remain; software ownership clears. Stale active control requests
  generate zero-acceleration ACC_CANCEL_GENERIC_SILENT and steering NONE.
  Freshly compiled safety accepts the cancellation and closes OEM longitudinal
  forwarding. Fault-only proof is also saved as `tesla-control-chain-fault.json`.
- F03: cooperative steering reports the final command and holds it on non-TX
  frames. The synthetic 20 m/s, 2 Nm case emits approximately 8.85 degrees,
  reports acceleration 1.0 m/s², and the takeover ramp reports its emitted
  approximately -1.0 m/s² instead of a steering angle. The acceptance tolerance
  is the native CAN quantization (0.05 degree / 0.02 m/s²). Under OEM ownership,
  steering output follows measured steering and SP acceleration output is zero;
  actual vehicle acceleration remains separately available in carState.aEgo.
- F04: the available Tesla DBC declares yaw quality but no numerical yaw signal.
  CarState therefore explicitly estimates rad/s from measured steering/speed
  and the existing VehicleModel using this vehicle's CarParams. The established
  ARS408 convention negates it to deg/s. +5/-5 degrees at 72 km/h produce
  -2.34/+2.34 deg/s; standstill produces zero; +5 degrees in reverse at 18 km/h
  produces +0.71 deg/s. Invalid CAN/nonfinite yaw produces no radar motion TX.
- The four old TX permissions and 0x3E9 Web validation permission are absent
  from every allowlist. The essential 0x370 **RX** checksum/steering input is
  retained and a corrupted checksum is rejected. Automatic wheel 0x3C2 and
  blindspot ambient 0x679 still pass their compiled safety paths.
- Old Params requests cannot initiate normal-card test TX. The validation
  controller and manual ambient request consumer are retired; ambient no
  longer depends on a validation early return. Root retains legacy Params
  registrations/schema ordinals as compatibility tombstones.
- Card passes its Params reader into the adapter before the first cycle.
  `CarStateExt.update_config` latches one explicit snapshot. A 95/90 km/h session
  remains 95/90 after live Params edits; a new session reads 80/70. opendbc no
  longer imports openpilot Params. Accessory brightness and SLA enablement
  retain their existing live update behavior.
- Pure display-only teslaRoadContext parsing/publication, duplicate owner/radar
  enums, unused SCCM diagnostic encoder, and the disconnected jerk experiment
  are removed. The traffic-control observer and production state machine remain.

Retired component tests/imports for the removed visual publisher, validation
initializers, and SCCM encoder were deleted, and the existing safety allowlist
fixture was narrowed. Both existing Tesla test modules still import. No unit
tests were added or run after implementation; the predeclared integration
entry point provides the regression proof. Scoped Ruff and both repositories'
`git diff --check` pass.

Physical ARS408 mounting/sign calibration, vehicle handoff behavior, onroad
comfort, and Panda firmware deployment remain **pending**. The compiled host
safety result does not establish that any physical Panda runs these changes.
