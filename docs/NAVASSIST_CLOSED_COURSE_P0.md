# NavAssist closed-course P0

## Scope

P0 accepts authenticated Android navigation observations and exercises one
active vehicle behavior: a bounded navigation speed ceiling before a supported
maneuver. It does not initiate a lane change, turn the steering wheel from route
geometry, synthesize a turn signal, request a stop, or send CAN.

Driver-confirmed lane changes continue through the existing physical turn
signal and DesireHelper path. NavAssist adds an onroad recommendation display
and an independent freshness-bounded lane observation for test diagnostics.

This is not the full requested navigation stack. Android P0 does not emit a
directional ramp/exit maneuver from road text or `roadType`, iOS has not been
implemented, phone/C3XL positions are not yet cross-correlated, and no automatic
lane change, intersection turn, or highway-exit steering is authorized.

## Preconditions

- Use `navassist-track-p0` based on `dev-sp-egpu-lane`.
- Test only on a physically closed course with a safety driver and observer.
- Configure a dedicated private phone/C3XL network.
- Survey a WGS-84 polygon with three to 64 vertices that contains the complete
  vehicle test envelope and excludes public access roads.
- Configure the same random test-only HMAC secret on TesNav and C3XL. Use at
  least 32 random bytes in practice (16 UTF-8 bytes is only the parser floor),
  do not distribute the APK containing it, and rotate it after testing.
- Synchronize phone and C3XL system clocks to within one second before arming.
- Physically secure the configured phone in the tested vehicle; P0 validates
  both devices independently inside their own data gates but does not yet prove
  that the two reported positions, headings, and speeds agree.
- Confirm the target is a Tesla C3XL, the official longitudinal backend is
  selected, and SP has active longitudinal authority before active deceleration.

On TesNav, place these values in the user Gradle properties used for the test
APK:

```properties
NAV_ASSIST_V2_URL=http://192.168.53.232:7766
NAV_ASSIST_V2_TOKEN=<test-only-shared-secret>
NAV_ASSIST_V2_INTERVAL_MS=200
```

On C3XL, configure `NavAssistToken` and `NavAssistTrackGeofence` offroad using
the local service console. The geofence value is JSON:

```json
{"coordinateSystem":"wgs84","polygon":[[31.0,121.0],[31.0,121.01],[31.01,121.01],[31.01,121.0]]}
```

Do not place a real secret or real track coordinates in the repository. HMAC
protects authenticity and integrity, not confidentiality; do not use P0 on a
shared network.

Finally, arm `CLOSED-COURSE nav assist` on the physical C3XL developer screen
while offroad. The phone protocol has no arming command. Arming clears on
manager restart and on the following offroad transition.

## Mandatory stationary checks

1. With Track Mode off, verify `navassistd` and `lane_topologyd` are not running
   and all existing longitudinal sources are unchanged.
2. Arm with no phone connection. The HUD must report navigation unavailable;
   no speed target may change.
3. Send missing-signature, wrong-signature, duplicate-sequence, decreasing
   route-revision, expired source-wall timestamp, contradictory inactive mode,
   malformed, non-finite, and oversized requests. Every request must be rejected
   or remain control-invalid and must not make `navAssistStateSP.valid` true.
4. Put the local LLK point outside the test polygon or invalidate localization.
   The state must report `outsideTrack` or `localLocalization` and remain unable
   to affect the planner.
   Repeat with GPS loss, local position uncertainty above 10 m, and a point less
   than 20 m plus its uncertainty from the polygon boundary.
5. Stop phone updates for more than 500 ms. The state must become stale and the
   speed ceiling must release upward at its bounded release rate, never jump to
   zero or command braking directly.
6. Restart the manager. Track Mode must be disarmed.
7. Restart only `navassistd`, replay the last accepted signed request, and verify
   the persisted receive high-water mark rejects it.

## Active longitudinal progression

Use a straight, empty lane. A maneuver event must first be observed with enough
distance to meet the comfort admission calculation; a late event is rejected
for its entire lifetime.

Suggested progression, subject to the actual vehicle and track safety plan:

1. 10–20 km/h, supported left/right turn events.
2. 30 km/h, varied early and late instruction distances.
3. 40–50 km/h only for the same supported maneuver classes after lower-speed
   tests pass; do not test automatic exit/ramp handling in Android P0.
4. At most 60 km/h only after every lower-speed combination passes and a C3XL
   closed-loop replay confirms the navigation-only deceleration envelope.

For every combination exercise phone loss, route-revision change, gas, brake,
cancel, longitudinal disengagement, and a new maneuver event. Navigation must
never produce a speed ceiling lower than 2 m/s, request a stop, or make the plan
less conservative than lead/FCW/base-planner constraints.

P0 actively contributes a target only with the official longitudinal backend.
Verify that experimental and TN-NoDEC reject the current event. On the official
backend, attribute deceleration carefully: the navigation-only cruise component
is bounded at -1.2 m/s², while an existing lead/FCW/model source may legitimately
be more conservative and therefore produce stronger braking.

## Driver-confirmed lane-change checks

P0 does not authorize a navigation-triggered lane change. It displays the
recommended lane while the driver uses the physical turn signal or steering
nudge to enter the existing ALC path.

Use painted single dashed, single solid, and dashed-to-solid boundaries and
keep the target lane physically empty. Confirm the independent
`laneTopologyStateSP` message:

- becomes stale after model or image evidence ages out;
- clears `validForControl` on any raw `unknown` evidence even when the UI
  tracker remembers a previous marking;
- clears on ambiguous topology, calibration loss, or ego source-pair change;
- distinguishes relative visible lane index from total road lane count.

No P0 result is permission to test automatic lane-change initiation.

## Immediate stop criteria

Stop the active test and return to HIL/root-cause analysis after any:

- unintended lateral actuation;
- failure of brake/cancel/driver override;
- accepted unauthenticated, replayed, stale, or outside-geofence input;
- speed target below the configured non-stop floor;
- harsh braking caused by a late navigation event;
- route revision causing an old maneuver to reactivate;
- any behavior difference with Track Mode disabled;
- model, camera, calibration, Panda, EPS, or longitudinal ownership fault.

Missing an instruction is the required fallback. The vehicle must never use
hard braking, a solid-line crossing, or a gore crossing to recover a missed
turn or exit.
