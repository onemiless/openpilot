# NavAssist closed-course P0

## Scope

This branch accepts authenticated Android/iOS navigation observations and
exposes three closed-course behaviors: a bounded navigation speed ceiling
before a supported maneuver, a bounded physical pre-turn lamp, and an
experimental one-lane-at-a-time navigation request through SP's existing
DesireHelper. On Tesla, both signal paths use the bounded 0x3E9 turn-signal
controller. The pre-turn lamp uses no lane-change target and cannot enter
DesireHelper; lane-change authority additionally requires Panda TX echo plus
physical lamp feedback.

The phone never supplies curvature, steering angle, acceleration, CarState, or
CAN. C3XL aligns AMap's recommended lane index with fresh visual topology. When
AMap has not yet published LaneInfo, an ordinary/sharp/U-turn may select the
visual extreme lane in its direction inside 1 km; directional exit/ramp/merge
maneuvers may do so inside 2 km. Explicit fresh AMap LaneInfo always takes
priority. C3XL requests one physical turn signal, waits for ego-side dashed
evidence and a clear blind spot, then lets the existing SP lane-change state
machine act. It cancels the signal after a stable one-lane visual index
transition and observes again before another request.

This is not the full requested navigation stack. Android does not infer a
directional ramp/exit maneuver from road text alone, phone/tici positions are
not yet cross-correlated, and no intersection-turn curvature path is accepted
from the phone. Lane positioning remains one visual lane at a time through
SP's existing lane-change state machine.
Lane positioning alone never creates a navigation speed target. If a supported
turn or directional exit enters its computed comfort-braking window while the
last lane change is still active, maneuver deceleration remains eligible; it is
not suppressed merely because lateral motion is in progress.

## Preconditions

- Use `navassist-track-p0` based on `dev-sp-egpu-lane`.
- Test only on a physically closed course with a safety driver and observer.
- Configure a dedicated private phone/C3XL network.
- Install the v3 TesNav App and perform its first automatic C3XL pairing while
  the vehicle is offroad on a controlled private LAN. No shared token is
  configured. C3XL can pin up to four P-256 App identities, adding each new
  identity only while offroad; unknown onroad keys are ignored.
- Synchronize phone and C3XL system clocks to within one second before arming.
- Physically secure the configured phone in the tested vehicle; P0 validates
  both devices independently inside their own data gates but does not yet prove
  that the two reported positions, headings, and speeds agree.
- Confirm the target is a Tesla C3XL, the official longitudinal backend is
  selected, and SP has active longitudinal authority before active deceleration.

TesNav generates a non-exportable P-256 private key in Android Keystore. C3XL
generates its own persistent P-256 device key and stores only the bounded App
public-key set in `NavAssistPairedApp`. First-use trust-on-first-use cannot
distinguish the owner from another live App on that LAN before a new key is
pinned, so do not perform initial pairing on a shared network. Reinstalling an
App changes its identity and requires offroad pairing; reset clears the entire
set. A fresh active navigation session cannot be preempted by another paired
App until it expires.

Do not place real track coordinates or private keys in the repository. P-256
signatures protect authenticity and integrity after TOFU pinning, not
confidentiality; do not use P0 on a shared network.

There is no per-drive Track Mode, shared-token, or geofence step. A fresh
realtime TesNav route becomes eligible only while SP has the required control
authority and the authenticated realtime route/data gates pass.

## Mandatory stationary checks

1. With no realtime phone navigation, verify `navassistd` remains available for
   pairing and transport, but `navAssistStateSP.valid` is false and all existing
   longitudinal sources are unchanged. `lane_topologyd` remains onroad-only.
2. Start a realtime route with SP disengaged. The HUD must report navigation unavailable;
   no speed target may change.
3. Broadcast malformed, oversized, unknown-field, and wrong-signature discovery
   requests. C3XL must remain silent. A valid request must receive a
   nonce-matched, authenticated unicast offer from UDP source port 7765, but the
   App must not report `ONLINE` until its HTTP POST on port 7766 succeeds.
4. Send missing-signature, wrong-signature, duplicate-sequence, decreasing
   route-revision, expired source-wall timestamp, contradictory inactive mode,
   malformed, non-finite, and oversized requests. Every request must be rejected
   or remain control-invalid and must not make `navAssistStateSP.valid` true.
5. Invalidate local localization. The state must report `localLocalization`
   while fresh matched phone guidance remains control-valid. Repeat with weak
   phone GPS and confirm the diagnostic remains visible without disabling the
   admitted route event.
6. Stop phone updates for more than 500 ms. The state must become stale and the
   speed ceiling must release upward at its bounded release rate, never jump to
   zero or command braking directly.
7. Restart the manager. The already-paired App must automatically rediscover the
   receiver, while old snapshots remain unable to affect planning until fresh
   realtime navigation and SP authority return.
8. Restart only `navassistd`, replay the last accepted signed request, and verify
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

## Navigation-requested single-lane change checks

This path is experimental and must progress from stationary signal validation
to HIL/replay before any moving test. `TeslaTurnSignalValidation` must be
enabled offroad and the onroad cycle restarted so the matching Panda safety
capability is present. Without confirmed physical lamp feedback, the state may
request a signal but must never authorize lateral motion.

Use painted single dashed, single solid, and dashed-to-solid boundaries and
keep the target lane physically empty. Confirm the independent
`laneTopologyStateSP` message:

- becomes stale after model or image evidence ages out;
- clears `validForControl` on any raw `unknown` evidence even when the UI
  tracker remembers a previous marking;
- clears on ambiguous topology, calibration loss, or ego source-pair change;
- distinguishes relative visible lane index from total road lane count.
- preserves the left/right component order of mixed solid-dashed boundaries and
  allows crossing only when the ego-side component has current dashed evidence;
- requires AMap and vision lane counts/indexes to match, a real neighboring
  lane, physical one-sided lamp feedback, clear BSM, and active SP lateral;
- tolerates at most one second of expected source-pair handoff while changing,
  then requires a stable one-lane index transition before cancelling the lamp;
- cancels on route/session change, pedals, physical-signal loss, stale input,
  direction conflict, or bounded timeout.

Never begin moving tests solely because unit tests pass. Capture a real model /
lane-topology replay and verify outer-line visibility cannot imitate a completed
lane change before authorizing closed-course motion.

## Immediate stop criteria

Stop the active test and return to HIL/root-cause analysis after any:

- unintended lateral actuation;
- failure of brake/cancel/driver override;
- accepted unauthenticated, replayed, or stale input;
- speed target below the configured non-stop floor;
- harsh braking caused by a late navigation event;
- route revision causing an old maneuver to reactivate;
- any behavior difference while navigation is invalid or SP is disengaged;
- model, camera, calibration, Panda, EPS, or longitudinal ownership fault.

Missing an instruction is the required fallback. The vehicle must never use
hard braking, a solid-line crossing, or a gore crossing to recover a missed
turn or exit.
