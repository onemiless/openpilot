# NavAssist source baselines

## Target

- Branch: `dev-sp-egpu-nva`
- Original eGPU source baseline: `bd2966b712f9e61e10efd87383502f3b033068dd`
- Synchronized eGPU maintenance head: `49bbb58ddb6a113932c0fa5c066220e2070bcdb5`
- Carrot protocol source: `jixiexiaoge/openpilot:Carrot`
- Carrot protocol commit: `3fb1121ecb7837e47f5edf12c5882e38c57c05bd`
- Protocol: Carrot Navi WebSocket v2, catalog revision 1
- NaviPilot Android source: `jixiexiaoge/navipilot:Amapauto`
- NaviPilot audited commit: `3f1af5f50bfb3c414aa40b9ab48a2fe6cf5afbda`
- AMap Companion source: `zuo-qirun/amap-companion`
- AMap Companion audited commit: `f7cc42d44a27588c67264657983c0e75ed739f42`
- AMap NavAssist bridge commit: `66989cb` (`navassist-v1`)
- AMap NavAssist APK version: `1.0.2-navassist` (versionCode `1787720682`)

## Network contract

- The openpilot device is the Carrot TCP/WebSocket server on port `7714` and
  the AMap Companion newline-JSON TCP server on port `7715`.
- The device broadcasts discovery JSON to UDP port `7705`.
- The Android app is the client.
- NavAssist enables only `vehicle`, `guidance_current`, `guidance_next`,
  `speed`, `route`, and `navigation_status` JSON streams.
- Media, image, render, cluster, terminal, command, and Web UI capabilities are
  not exposed by NavAssist.

The current protocols use unauthenticated plain local-network sockets. This
branch accepts that limitation only for supervised prototype testing. It is
not evidence of public-road readiness.

`dev-sp-egpu-nva` is explicitly allowlisted as a supervised C3XL/TICI test
channel. Accepted changes must return to the maintained `dev-sp-egpu` channel;
the allowlist is not generalized to other development branches.

## Cereal allocation

The eGPU baseline already uses reserved slot 10 / Event `@136` for
`TrafficRadarState`. NavAssist therefore uses the next empty reserved binding:

- `NavAssistSP` preserves `CustomReserved11` identifier
  `@0xc2243c65e0340384`.
- `navAssistSP` preserves Event ordinal `@137`.

## First-stage control scope

- Navigation maneuver, camera, section, and route-curve speed constraints may
  enter the existing longitudinal planner when all feature, driver, service,
  and Tesla runtime-owner gates pass.
- Navigation road limits enter the existing SpeedLimitResolver as a separate
  source, preserving the configured policy and offset.
- Left/right turns and forks can request the existing validated Tesla turn-signal
  CAN path near a maneuver. Existing SP blindspot and lane-change logic decides
  whether any lateral maneuver is safe; navigation never injects a model desire.
- Roundabout, U-turn, arrival, tollgate, traffic-light, and direct route steering
  remain outside this stage.

## Safety defaults

All control switches default off. Shadow defaults on. Stream freshness is
checked independently so unrelated heartbeats cannot keep an old maneuver or
speed target alive.

The current CarState contracts do not expose a reliable trailer-connected
signal. NavAssist therefore cannot enforce a trailer gate in this stage and
must not be tested with a trailer attached. It does enforce the existing
blindspot, road-edge, LaneTurn speed, brake, opposite steering-torque, lateral
active, and matching real-turn-signal gates.

The TICI Navigation settings panel exposes the feature toggles plus a read-only
connection/data-validity status. Shadow lateral decisions are recorded on
`modelDataV2SP` as the actual request, would-request, suppression reason, and
maneuver ID for replay inspection.
