# Tesla Continental ARS408 optional backend behavior specification

Status: draft for review; no production implementation is authorized by this document.

## 1. Baselines and evidence boundary

This specification was derived from the current checked-out sources, not from a file copy or a historical branch assumption.

| Role | Repository | Branch | Reviewed commit |
|---|---|---|---|
| behavior reference | `/Users/mile/Desktop/cp/cpv9-mads-worktree` | `cpv9-0813` | `ac0fe96cdae5a69b3fd2a06aa58df54a60420ab2` |
| implementation target | `/Users/mile/Desktop/mo-op` | `dev-sp08` | `2411803e99c2cfdcf77c6130d4440d1c13573c69` |
| target opendbc | `/Users/mile/Desktop/mo-op/opendbc_repo` | submodule state | `295d9c8dff8b13ecbc28818bb6f683320a5ac60e` |

The CP branch is a behavioral and protocol reference only. Its complete files, classes, and functions are not an implementation source. The SP implementation must be independently structured around the responsibilities in `tesla_ars408_refactor_design.md`.

Primary source set reviewed:

- CP: `opendbc_repo/opendbc/car/tesla/radar_interface.py`, `ars408_can.py`, `ars408_log.py`, Tesla `interface.py`, `carcontroller.py`, `values.py`, `ARS408.dbc`, Tesla safety, and their ARS408 tests, plus the ARS408-specific `radard` tests.
- SP: Tesla OEM `radar_interface.py`, Tesla `interface.py`, `carcontroller.py`, base radar/card initialization, sunnypilot initialization/flags, Params schema, standard `RadarData`, `radard.py`, and Tesla safety/tests.

Evidence categories used below:

- **Observed SP fact**: behavior present in the reviewed SP source.
- **Observed CP fact**: behavior present in the reviewed CP source or tests.
- **Required SP behavior**: the contract proposed for the new implementation.
- **Unverified assumption**: requires a route, bench, gateway, or vehicle capture before it can be treated as fact.

The local CP reference tests passed as follows:

- ARS408 interface, transmitter, and downstream duplicate-reference tests: `64 passed`.
- ARS408-selected Panda safety tests: `12 passed, 6 skipped`.

The current SP Tesla Python baseline passed: `59 passed, 12 subtests passed`.

These are code-level results only. They do not prove gateway isolation, physical CAN compatibility, radar configuration persistence, replay behavior, or vehicle-level ACC/FCW safety.

## 2. Corrected premises

The current CP branch does **not** use Sensor ID 5. Its reviewed target-vehicle configuration is:

- CAN bus: logical bus 1.
- Sensor ID: 0.
- Maximum distance: 250 m.
- Output: object list with Quality and Extended information enabled.
- Ego-motion input: enabled through `0x300` and `0x301`.

Therefore the receive addresses are the base ARS408 addresses, without a Sensor-ID offset. Older notes referring to Sensor ID 5 and `0x65A`-series object frames are not applicable to this baseline.

The statement that Panda safety might not need changes is also resolved: the current SP allowlist does not permit the ARS408 transmit frames. In the CP reference, `0x300` and `0x301` are constrained only by bus and DLC, not by their encoded fields or values. If SP transmits these frames, SP needs a new backend-specific safety flag plus stricter payload validation.

## 3. Scope and non-goals

### 3.1 In scope

- An offroad-selected, initialization-latched ARS408 backend for Tesla.
- Independent RX parsing, cycle assembly, lifecycle tracking, diagnostics, interface adaptation, and ego-motion transmission.
- Standard SP `car.RadarData.points` output.
- Internal retention and rate-limited logging of ARS408-only metadata.
- Strict Panda TX gating for enabled ARS408 operation.
- Unchanged OEM Continental radar behavior when the OEM backend is selected.

### 3.2 Out of scope for the first implementation

- Changes to the global `RadarData` Cap'n Proto schema.
- Changes to `radard`, planner, longitudinal MPC, or lead fusion.
- Automatic radar configuration or NVM writes.
- Software workarounds for physical CAN-ID collisions; the external safety gateway owns that problem.
- Cluster-list output, collision-detection regions, relay control, or radar power changes.
- Claims of vehicle readiness without replay, gateway, bench, and controlled-road evidence.

## 4. Backend selection contract

The boolean `TeslaARS408Radar` is read once during car initialization and cached in `CarParamsSP` flags. It is never read in a per-frame path.

Selection behavior:

| Switch | Backend | Behavior |
|---|---|---|
| Off | OEM | Preserve current SP fingerprint/DBC gating and instantiate the existing Tesla OEM Continental interface unchanged. This is the default. |
| On | ARS408 | Ignore OEM radar fingerprint absence, instantiate the external ARS408 backend, set the ARS408 safety flag, and enable the ARS408 motion transmitter. |
| malformed | Off | Fail closed, report radar unavailable, and emit no radar TX. |

Changing the Param while onroad does not change the active backend. A car/card restart is required. This avoids parser, tracker, and Panda policy changes during a drive.

The user's target vehicle is expected to run value 1. Value 0 remains the regression-protected SP default even though the target vehicle's OEM radar is not usable.

## 5. Protocol contract

### 5.1 RX frames

All frames below are accepted only on logical bus 1 and only with the exact DLC shown.

| Address | DLC | Meaning | Use |
|---:|---:|---|---|
| `0x60A` | 4 | `Obj_0_Status` | Starts a new object cycle and closes the preceding cycle. Contains raw object count and interface version. |
| `0x60B` | 8 | `Obj_1_General` | Raw ID, longitudinal/lateral position, longitudinal/lateral relative velocity, RCS, dynamic property. |
| `0x60C` | 7 | `Obj_2_Quality` | Raw ID, existence probability, measurement state, quality fields. |
| `0x60D` | 8 | `Obj_3_Extended` | Raw ID, longitudinal acceleration, object class, size/orientation fields. Optional for core tracking. |
| `0x201` | 8 | `RadarState` | Faults, configuration readback, Sensor ID, output mode, motion-input state. |
| `0x203` | 2 | `FilterState_Header` | Number of configured cluster/object filters. |
| `0x204` | 5 | `FilterState_Cfg` | One multiplexed filter readback record. |

Frames with another bus, address, or DLC must not mutate cycle, tracking, or diagnostic state. They may increment a bounded diagnostic counter.

### 5.2 TX frames

| Address | DLC | Meaning | First-version policy |
|---:|---:|---|---|
| `0x200` | 8 | `RadarConfiguration` | Independently packable and unit-tested, but not automatically emitted. Current radar configuration is accepted as correct. |
| `0x202` | 5 | `FilterCfg` | Independently packable and unit-tested, but not automatically emitted. No runtime filter/NVM workflow in v1. |
| `0x300` | 2 | `SpeedInformation` | Emit at 20 Hz while ARS408 backend is active and vehicle state is valid. |
| `0x301` | 2 | `YawRateInformation` | Emit with `0x300` at 20 Hz while ARS408 backend is active and vehicle state is valid. |

This resolves the apparent conflict between “reimplement all four transmit messages” and “configuration messages need not be reimplemented when the radar is already configured”: v1 contains independently authored, bounded encoders for all four, but only `0x300/0x301` are in the production periodic schedule. `0x200/0x202` remain unreachable from the periodic path until a later reviewed configuration workflow is authorized.

## 6. Object-cycle assembly

1. The first valid `0x60A` opens a cycle. No object point is published before both a valid `RadarState` and a closable object cycle have been observed.
2. The next valid `0x60A` closes the previous cycle before opening the next one.
3. The status count must be in `0..100`, and interface version must equal 1.
4. General and Quality frames are indexed by their raw object ID. Duplicate parts for the same raw ID make the cycle non-exact and are logged.
5. A complete core cycle has exactly the advertised count of unique General IDs and Quality IDs, with identical ID sets and no duplicate core frames.
6. A partial cycle may salvage only the intersection `General IDs ∩ Quality IDs`. Missing Quality data never inherits probability or measurement state from an older cycle.
7. Extended data is merged only for matching raw IDs. Missing Extended data produces neutral acceleration and internal class `7` (unknown); it never reuses stale Extended data.
8. A malformed core DLC invalidates that part. A malformed Extended frame does not invalidate otherwise valid General+Quality pairs.
9. A zero-object cycle is valid and produces an empty measured set, after lifecycle grace is applied to previously established tracks.
10. An incomplete cycle is not by itself a CAN disconnect. Transport timeouts and cycle completeness are diagnosed independently.

## 7. Internal object model

The internal assembled-object record retains at least:

- raw object ID;
- measurement counter/cycle number;
- `dRel`, `yRel`, `vRel`, `yvRel`, optional `aRel`;
- measurement state;
- existence probability code;
- dynamic property;
- object class, using 7 for unknown/missing;
- RCS;
- which component frames were present;
- rejection reason, when rejected.

The raw count from `0x60A`, object class, and existence probability stay inside this model and the diagnostics/logging layer. They are not added to the global `RadarData` schema in v1.

## 8. Acceptance and filtering

### 8.1 Existence hysteresis

- A new target requires probability code at least 3 (`>=75%`).
- An established target requires probability code at least 2 (`>=50%`).
- A low-probability observation is treated as a missed cycle for an established target, not as a new measurement.

### 8.2 Measurement-state semantics

| State | Meaning used by backend | New track | Existing track | Output `measured` |
|---:|---|---:|---:|---:|
| 0 | deleted/invalid | reject | miss/delete handling | false |
| 1 | new | accept if all gates pass | accept | true |
| 2 | measured | accept if all gates pass | accept | true |
| 3 | predicted | reject | accept only after a real observation established the logical track | false |
| 4 | deleted for merge | reject | eligible as explicit handover source, otherwise miss/delete handling | false |
| 5 | new from merge | accept if all gates pass | accept | true |
| 6–7 | unsupported/reserved | reject | miss/delete handling | false |

### 8.3 Numeric bounds

An accepted object must satisfy all of the following:

- finite numeric values;
- `0 <= dRel`;
- `hypot(dRel, yRel) <= 250 m`;
- `abs(yRel) <= 100 m`;
- `-100 <= vRel <= 100 m/s`;
- `abs(yvRel) <= 60 m/s`;
- class is in `0..7` when Extended data is present.

### 8.4 Static/crossing filtering

For ARS408 dynamic-property values classified as stationary, crossing-stationary, or stationary candidate (reference values 1, 3, and 5), require `abs(yRel) <= 5.5 m`. This rejects obvious roadside infrastructure while retaining stopped lead vehicles and adjacent-lane candidates. It is not a semantic claim that every object within the corridor is drivable-lane traffic.

Moving and oncoming classifications still pass the general numeric bounds. Replay must verify whether additional lateral filtering is needed; v1 must not invent a path-relative filter without evidence.

## 9. Track lifecycle and identity

### 9.1 Grace and measured state

- A newly accepted raw target creates one logical track.
- A measured update resets its miss count to zero.
- On the first and second consecutive missed cycles, retain the last kinematics and output `measured=false`.
- On the third consecutive missed cycle, delete the track.
- Reappearance before deletion keeps the logical track ID and resumes `measured=true` when the measurement state is measured.

### 9.2 No logical track-ID reuse

- A raw ID may be used as its first logical `trackId` only if that value has never been assigned during the backend instance lifetime.
- Reuse of an expired raw ID receives a new monotonically allocated logical ID, starting at 256.
- The used logical-ID set is not cleared by an empty cycle or a temporary transport fault.

### 9.3 Raw-ID handover

Two mechanisms preserve logical continuity:

1. Explicit merge handover: an established raw ID reports state 4 and a new raw ID reports state 5 in the same cycle. If class and kinematics match within the handover envelope, move the old logical track to the new raw ID.
2. Kinematic handover: an established raw ID disappears and one new raw ID is tightly colocated. Use the stricter duplicate envelope and transfer only when exactly one best candidate is unambiguous.

Reference envelopes:

| Envelope | `dRel` | `yRel` | `vRel` | `yvRel` |
|---|---:|---:|---:|---:|
| duplicate / kinematic | 1.5 m | 0.6 m | 1.5 m/s | 0.8 m/s |
| explicit merge handover | 2.5 m | 1.0 m | 2.5 m/s | 1.5 m/s |

When either class is unknown, multiply all limits by 0.7. Known unequal classes do not match.

### 9.4 Duplicate suppression

- Compare active objects only after handover processing.
- Never merge two established logical tracks solely because their kinematics overlap.
- If at least one overlapping raw ID is new, keep the established target first; otherwise rank by measurement state, existence probability, then stable raw-ID order.
- Suppression affects only the current candidate set; it must not silently transfer identity unless handover rules pass.
- Log keep/drop raw IDs, logical ID, deltas, and a cumulative suppression count when the signature changes.

The new backend must suppress duplicates before producing `RadarData.points`. The CP reference contains an additional `radard` duplicate defense, but SP `radard` remains unchanged unless replay proves the interface-level contract insufficient.

## 10. Standard SP output mapping

Each accepted logical track maps to one standard `car.RadarData.RadarPoint`:

| SP field | ARS408 source |
|---|---|
| `trackId` | logical, never-reused ID |
| `dRel` | `Obj_DistLong` |
| `yRel` | negative `Obj_DistLat`, matching the reviewed reference coordinate convention |
| `vRel` | `Obj_VrelLong` |
| `aRel` | current-cycle `Obj_ArelLong`, or 0 when Extended is absent |
| `yvRel` | `Obj_VrelLat` |
| `measured` | true only for measurement states 1, 2, and 5 |

No `vLead`, object class, existence probability, raw object count, or ARS-specific status field is added to the schema.

In the actual `dev-sp08` schema, `aRel`, `yvRel`, and `measured` already exist inside the
standard point's `deprecated` group. The backend writes those existing nested fields; it does
not add, move, or rename any Cap'n Proto field.

## 11. RadarState and FilterState diagnostics

### 11.1 Independent health channels

Track these independently:

- CAN parser validity;
- object-status freshness;
- RadarState freshness;
- exact/partial/malformed cycle counts;
- current RadarState faults and configuration;
- FilterState Header and per-index records;
- motion-input health;
- lifecycle rejection/handover/suppression counters.

### 11.2 Timeouts

The initial implementation shall express timeouts in monotonic nanoseconds, not in caller-update counts, so behavior does not change with card scheduling rate.

Proposed reference-equivalent defaults:

- startup health grace: 10 s;
- object-status timeout while object output is enabled: 0.5 s;
- RadarState timeout: 3.0 s;
- RadarState configuration grace: 10 valid RadarState reports;
- interference confirmation: 10 consecutive RadarState reports.

These values reproduce the intent of the CP update-count constants while removing their hidden 100 Hz assumption.

### 11.3 Error mapping

| Condition | SP error |
|---|---|
| parser invalid or required status/state timeout after startup grace | `canError` |
| persistent voltage error or persistent radar error | `radarFault` |
| confirmed interference, temperature error, or radar temporary error | `radarUnavailableTemporary` |
| wrong Sensor ID, unsupported output type, missing Quality in object mode, or invalid max-distance configuration after grace | `wrongConfig` |

Expected critical configuration for the target is Sensor ID 0, OutputType Objects, Quality enabled, and 250 m max distance. Extended information may be disabled without invalidating core tracking, but the change is logged and internal class/acceleration fall back to unknown/zero.

`RadarState_MotionRxState != 0` is logged immediately. Whether it should become `radarUnavailableTemporary` after a sustained interval remains a review decision: CP treats it as advisory, but an enabled ego-motion backend can produce degraded object velocities when motion input is absent. The safer recommendation is to promote a sustained nonzero state after TX startup grace to `radarUnavailableTemporary`; this requires replay/bench confirmation before implementation.

### 11.4 FilterState

- Decode `0x203` and `0x204` only on bus 1 with exact DLC.
- Retain Header counts and the latest valid Object-filter record for each index `0..14`.
- Reject reserved index 15 and unsupported Cluster-filter records from the active state model.
- Bounds-check decoded min/max values against the signal's protocol range and require min <= max.
- Log changes and invalid records; do not modify radar filters automatically in v1.

## 12. Transmitter behavior

### 12.1 Initialization-only configuration

The transmitter is constructed only when the cached backend flag is ARS408. It receives immutable configuration and does not own a `Params` object.

### 12.2 Ego-motion schedule

- Schedule `0x300` and `0x301` together at 20 Hz using controller frame/monotonic timing.
- Emit neither frame unless `CarState.canValid` is true and both source values are finite.
- Speed source: `vEgoRaw` magnitude.
- Direction: 0 at standstill (`abs(vEgoRaw) < 0.05 m/s`), 1 forward, 2 reverse.
- Yaw rate: convert radians/s to degrees/s and invert sign in reverse, matching the reviewed CP behavior.
- Independent encoder bounds: speed `0..85 m/s`; yaw rate `-100..100 deg/s`. Values outside these operational bounds cause no TX and a rate-limited diagnostic; they are not silently clipped.

The operational bounds are intentionally narrower than the DBC representable ranges. They cover the Tesla speed envelope and avoid turning corrupted state into extreme radar motion input.

### 12.3 Configuration frames

`0x200` and `0x202` encoders must support only reviewed field-scoped operations and must reject all other combinations. No periodic or startup code calls them in v1. In particular, v1 does not change Sensor ID, power, relay, RCS threshold, or NVM.

## 13. Panda safety recommendation

Panda changes are required only because the ARS408 backend transmits. The recommended policy is:

- Add a dedicated `TeslaSafetyFlagsSP.ARS408_RADAR` bit set only from the initialization-latched backend selection.
- Do not add ARS408 messages to the normal Tesla TX list.
- When the flag is absent, reject `0x200`, `0x202`, `0x300`, and `0x301` on every bus and DLC.
- When present, allow only bus 1 and exact DLC.
- `0x300`: direction must be 0, 1, or 2; reserved bits must be zero; encoded speed must be <= 85 m/s.
- `0x301`: encoded yaw must be within -100..100 deg/s and must reject reserved/out-of-policy encodings.
- `0x200/0x202`: because v1 never schedules configuration writes, keep them rejected in the production safety allowlist. Their encoder tests do not grant wire authority.

If a later reviewed configuration workflow enables `0x200/0x202`, safety must use exact byte-pattern validation for the approved single-field operations, not merely address/bus/DLC checks. Filter writes require index-specific payload/range validation; the CP reference's header-only validation is insufficient.

The external gateway's CAN collision policy does not replace Panda TX validation. The gateway owns physical forwarding/isolation; Panda owns which host-generated frames may leave the device.

## 14. OEM regression contract

When backend 0 is selected:

- `opendbc.car.tesla.radar_interface` remains the implementation.
- OEM fingerprint and Tesla radar DBC gating are unchanged.
- Trigger address, parser frequencies, A/B pairing, fault mapping, point allocation, and output values remain unchanged.
- No ARS408 parser or transmitter is constructed.
- No ARS408 safety bit or TX message is enabled.

The target vehicle may not have a usable OEM radar, but the mode's software behavior still requires regression tests because upstream SP users do.

## 15. Validation gates for implementation

### 15.1 Unit/static gate

- Parser bus/address/DLC rejection and numeric bounds.
- Complete, partial, duplicate, zero-object, and malformed cycles.
- Every lifecycle rule in sections 8 and 9.
- RadarState, FilterState, timeout, and recovery transitions.
- Selector fail-closed behavior and OEM instance/output parity.
- Transmitter scheduling, invalid-state suppression, direction/sign conversion, and encoder rejection.
- Panda flag/bus/DLC/reserved-bit/value-range tests.
- Type checks, lint, DBC generation/checks, and no Params reads in per-frame methods.

### 15.2 Replay gate before changing radard/planner/MPC

- Recorded ARS408 route produces stable logical IDs and no duplicate leadOne/leadTwo target.
- Two-cycle grace does not create unsafe ghost leads.
- Partial cycles do not generate false CAN disconnects.
- RadarState faults propagate using standard errors.
- Standard SP radard consumes the points without a required code change.

Only a concrete replay failure attributable to SP downstream code can authorize a scoped `radard` change. Planner/MPC changes require a separate defect and evidence.

### 15.3 Bench/gateway gate

- Confirm logical bus 1 maps to the gateway-managed ARS408 segment.
- Confirm Sensor ID 0 addresses and exact DLCs.
- Confirm `0x300/0x301` are received by the radar at 20 Hz and `MotionRxState` clears.
- Confirm non-ARS modes emit none of the four ARS408 TX IDs.
- Confirm Panda rejects wrong bus, DLC, reserved bits, direction, speed, and yaw values.

### 15.4 Controlled-road gate

- Lead continuity, cut-in/cut-out, stopped lead, crossing/static roadside objects, and high-object-count scenes.
- ACC/FCW response with an independent driver and abort plan.
- Gateway collision/isolation evidence.
- No claim beyond the tested vehicle, firmware, gateway configuration, and route.

## 16. Review decisions required before implementation

1. Accept backend values `0=OEM`, `1=ARS408`, `2=Off`, with OEM as default.
2. Accept that `0x200/0x202` are encoded/tested but not wire-enabled or automatically sent in v1.
3. Decide whether sustained nonzero `MotionRxState` is advisory or `radarUnavailableTemporary` after startup grace; the safer recommendation is temporary-unavailable.
4. Accept 20 Hz motion TX with operational safety bounds of 85 m/s and ±100 deg/s.
5. Accept that no settings UI is added in the first core implementation; selection is an offroad Param requiring restart. A UI can be a separate later commit.
