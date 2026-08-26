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

Media, images, render output, camera preview, terminal, remote Params, commands,
automatic overtake, and legacy Carrot transports are not enabled by NavAssist.

## Source selection

The source mux is session-sticky. A healthy Carrot v2/NaviPilot source is
preferred even when an AMap Companion packet arrived more recently. AMap is
selected only after the preferred source disconnects, errors, or exceeds the
local message timeout. Recovery to NaviPilot requires one second of healthy
data to avoid packet-by-packet oscillation.

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

