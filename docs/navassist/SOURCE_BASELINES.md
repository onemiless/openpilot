# NavAssist source baselines

## Target

- Branch: `dev-sp-egpu-nva`
- eGPU source baseline: `bd2966b712f9e61e10efd87383502f3b033068dd`
- Carrot protocol source: `jixiexiaoge/openpilot:Carrot`
- Carrot protocol commit: `3fb1121ecb7837e47f5edf12c5882e38c57c05bd`
- Protocol: Carrot Navi WebSocket v2, catalog revision 1

## Network contract

- The openpilot device is the TCP/WebSocket server on port `7714`.
- The device broadcasts discovery JSON to UDP port `7705`.
- The Android app is the client.
- NavAssist enables only `vehicle`, `guidance_current`, `guidance_next`,
  `speed`, `route`, and `navigation_status` JSON streams.
- Media, image, render, cluster, terminal, command, and Web UI capabilities are
  not exposed by NavAssist.

The upstream protocol currently uses unauthenticated plain local-network
WebSockets. This branch accepts that limitation only for supervised prototype
testing. It is not evidence of public-road readiness.

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
- Ordinary left/right turns can emit one model desire pulse only at low speed
  after the driver activates the matching real turn signal.
- Fork/lane-change, roundabout, U-turn, arrival, tollgate, traffic-light, direct
  route steering, vehicle CAN, panda, and safety changes are outside this stage.

## Safety defaults

All control switches default off. Shadow defaults on. Stream freshness is
checked independently so unrelated heartbeats cannot keep an old maneuver or
speed target alive.
