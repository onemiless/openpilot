# NaviPilot Carrot v2 adapter

NaviPilot is the preferred structured Android source for NavAssist. It uses the
existing Carrot Navi WebSocket v2 server on TCP `7714` after UDP `7705`
discovery. AMap Companion v1 remains available on TCP `7715` as a supervised
fallback while NaviPilot completes device validation.

## Enabled control streams

- `vehicle`
- `guidance_current`
- `guidance_next`
- `speed`
- `route`
- `navigation_status`

CP UDP `7706` is accepted as a validated navigation fallback, and the companion
bridge exposes allowlisted vehicle telemetry and offroad-only Params on `7000`
plus legacy vehicle telemetry on `7711`. Media, camera preview, terminal,
arbitrary Params, commands, and direct route steering are not enabled.

## Source selection

Carrot v2 and CP UDP `7706` are normalized as the preferred NaviPilot source;
the freshest connected Carrot snapshot is used. AMap Companion is selected only
after the preferred source disconnects, errors, or exceeds the local message
timeout. Recovery from AMap to NaviPilot requires one second of healthy data.

## Capability boundary

NaviPilot provides current and next guidance, road/camera/section speed data,
and WGS-84 vehicle position. Its AMap Auto path currently sends an empty route
polyline, so route summaries are accepted but `routeValid` and route-curve
speed remain false. AMap Auto also lacks a durable off-route source; it must not
advertise a transient UI flag as control truth.

## Validation and distribution

The audited Android source is
`jixiexiaoge/navipilot@3f1af5f50bfb3c414aa40b9ab48a2fe6cf5afbda`.
Its README claims MIT, but that tree has no LICENSE/COPYING file and GitHub does
not identify a license. Local interoperability work is permitted for testing;
do not publish a derivative source tree or APK until the maintainer provides a
license or written authorization.
