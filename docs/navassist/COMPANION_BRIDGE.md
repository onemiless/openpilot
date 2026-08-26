# CP Companion Bridge

`companiond` supplies the read-mostly device-to-phone half of the CP companion integration. It is enabled with
`NavAssistEnabled` and runs both offroad and onroad so pairing does not require forcing the vehicle into an onroad state.

## Local interfaces

- `GET :7000/health` reports service health.
- `GET :7000/api/params_bulk?names=...` reads an explicit parameter allowlist.
- `POST :7000/api/param_set` writes an explicit boolean allowlist while offroad only.
- `WS :7000/ws/raw_multiplex?services=...` sends length-prefixed service names followed by native Cap'n Proto payloads.
- `TCP :7711` sends legacy four-byte-length-prefixed JSON vehicle snapshots.
- `UDP :7706` accepts CP companion's validated legacy navigation snapshots when its v2 sockets only emit ping frames.

Only private, loopback, or link-local clients are accepted. The supported telemetry allowlist is `carState`, `modelV2`,
`controlsState`, `selfdriveState`, `deviceState`, `carrotMan`, and `gpsLocationExternal`; unavailable services are ignored.

The readable and writable parameter allowlist is deliberately limited to `ExperimentalMode`, `ShareData`, and
`SpeedFromPCM`. Writes are rejected unless `IsOffroad` is true and `IsEngaged` is false. No arbitrary Params access,
terminal, SSH, camera stream, or system command endpoint is exposed.

## Runtime dependency policy

The bridge and Carrot Navi v2 receiver use the Python standard library for HTTP and RFC 6455 WebSocket framing. AGNOS
does not provide `aiohttp` in its read-only runtime, so adding that package only to `pyproject.toml` is insufficient for
device deployment.
