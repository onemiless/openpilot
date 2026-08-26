# AMap Companion NavAssist bridge v1

## Why an adapter is required

Upstream `zuo-qirun/amap-companion` listens to Android-local AMap Auto
broadcasts (`AUTONAVI_STANDARD_BROADCAST_SEND/RECV`) and renders an overlay. At
audited commit `f7cc42d44a27588c67264657983c0e75ed739f42` it has no openpilot discovery,
TCP/WebSocket client, Carrot manifest, session, sequence, or network navigation
publisher. The original APK therefore cannot connect directly to NavAssist.

The companion `navassist-v1` branch adds a platform-API-only bridge. It keeps
GPL application code outside the MIT openpilot tree and shares only this JSON
wire contract.

## Discovery and transport

- Device broadcasts UDP JSON to port `7705`.
- Discovery includes `ip`, `amap_companion_protocol: 1`, and
  `amap_companion_port: 7715`.
- The Android app is the TCP client.
- The openpilot device listens on TCP `7715`.
- Each message is one UTF-8 JSON object followed by `\n`.
- Maximum encoded line size is 64 KiB.
- The app sends the latest snapshot every 500 ms.
- App `1.0.2-navassist` starts its foreground bridge when the app opens and
  reports discovery, connection, and AMap-data freshness on its home screen.
  It independently expires navigation, maneuver, road-limit,
  and camera source timestamps before each heartbeat. A live TCP connection
  therefore cannot keep stale AMap control fields valid.

## Snapshot schema

```json
{
  "protocol": "amap_companion_v1",
  "version": 1,
  "session_id": "uuid",
  "sequence": 42,
  "sent_at_ms": 1787000000000,
  "navigation_active": true,
  "cruise_mode": false,
  "road_name": "当前道路",
  "maneuver_icon": 2,
  "maneuver_distance_m": 80,
  "maneuver_road": "下一道路",
  "current_speed_kph": 45,
  "limit_speed_kph": 60,
  "camera_speed_kph": 40,
  "camera_type": 0,
  "camera_distance_m": 300
}
```

The receiver validates types, ranges, session changes, monotonic sequence,
exact duplicates, and line length before producing a `ProtocolSnapshot`.
`limit_speed_kph` is the current road limit (`LIMITED_SPEED`), while
`camera_speed_kph` is the upcoming camera limit (`CAMERA_SPEED`); they are
kept separate because AMap may report different values.

## Maneuver mapping

| AMap icon | NavAssist maneuver |
| --- | --- |
| 2 | turn left |
| 3, 19 | turn right |
| 4, 6 | fork/diagonal left |
| 5, 7 | fork/diagonal right |
| 8, 10, 11, 12 | U-turn |
| 13, 14, 17, 18 | roundabout |
| other/straight | none |

## Capability boundary

The AMap broadcast state supports current maneuver, current road, current
speed, speed limit, and camera type/distance. It does not expose the same
complete route polyline or stable next maneuver delivered by Carrot V2.
Therefore:

- current maneuver speed: supported;
- road-limit source: supported;
- speed-camera target: supported when AMap supplies distance and limit;
- driver-confirmed ordinary turns: supported;
- next-maneuver planning: unavailable for this source;
- route-curve speed: unavailable for this source;
- location/route deviation: unavailable for this source.

Carrot V2 remains available on TCP `7714`; AMap Companion uses TCP `7715`.
