# NavAssist closed-course P0

This module is an isolated, closed-course-only ingress path for high-level
mobile navigation observations. It does not accept actuator, curvature,
acceleration, CarState, or CAN commands.

## Arming

The manager starts `navassistd` and `lane_topologyd` only on a Tesla C3XL while
onroad when:

- `NavAssistTrackMode` was enabled offroad for the current manager session; and
- `NavAssistToken` contains at least 16 UTF-8 bytes.
- `NavAssistTrackGeofence` contains a WGS-84 test-track polygon, for example:

```json
{"coordinateSystem":"wgs84","polygon":[[31.0,121.0],[31.0,121.01],[31.01,121.01],[31.01,121.0]]}
```

`NavAssistTrackMode` clears on manager restart and on the following offroad
transition. The phone cannot arm it. Configure the token offroad using the local
service console (`Params().put("NavAssistToken", "<test secret>")`), configure the surveyed test polygon, then enable the
closed-course toggle in developer settings. The normalized snapshot remains
invalid unless C3XL's own `liveLocationKalman` is valid and inside this polygon.
The developer screen reports only `token configured` or `token not configured`;
it never displays the secret itself.

## Transport

The phone discovers an armed C3XL without scanning every HTTP address. It sends
an authenticated IPv4 UDP broadcast to port 7765, then constructs the HTTP URL
from the source IP of a verified unicast offer. The offer never supplies a host
name or IP address. Both datagrams are compact JSON, at most 512 bytes, with
exact field sets:

```json
{"messageType":"navassist_discovery_request","schemaVersion":2,"nonce":"<32-lower-hex>","proof":"<64-lower-hex>"}
{"messageType":"navassist_discovery_offer","schemaVersion":2,"nonce":"<same-nonce>","port":7766,"path":"/v2/snapshot","proof":"<64-lower-hex>"}
```

The request proof is lower-case hex HMAC-SHA256 with `NavAssistToken` over the
exact UTF-8 bytes below (with newline separators and no trailing newline):

```text
navassist_discovery_request
2
<nonce>
```

The offer proof covers this exact UTF-8 material:

```text
navassist_discovery_offer
2
<nonce>
7766
/v2/snapshot
```

The nonce is a new 16-byte random value for each discovery round. C3XL replies
only to RFC1918 IPv4 sources and silently drops malformed, oversized,
unauthenticated, or rate-limited requests. A bounded two-second `(source,
nonce)` cache suppresses duplicate bursts; because the request has no timestamp,
this cache is not persistent replay protection. The outstanding random nonce on
the phone prevents an old offer from matching a new round, while HTTP retains
its separate TTL and replay controls. Only the manager-gated `navassistd`
process owns the UDP socket, so Track Mode off means there is no discovery
responder. A verified offer identifies a candidate; the phone reports the C3XL
as online only after an HTTP exchange also succeeds.

POST compact JSON matching `nav-assist-v2.schema.json` to:

```text
http://<c3xl-private-address>:7766/v2/snapshot
```

Set `X-NavAssist-Signature` to lower-case hex HMAC-SHA256 of the exact request
body using `NavAssistToken`. Use only a dedicated private test network; P0 HMAC
authenticates and protects message integrity but does not encrypt location data.
Use a random test token of at least 32 bytes in practice; the protocol's 16-byte
minimum is only a configuration floor.

The receiver bounds request size, rate, and concurrent connections, rejects malformed/non-finite values,
requires a strictly increasing sequence and non-decreasing route revision, and
assigns the control-relevant TTL on C3XL receipt only after also bounding the
signed source-wall timestamp. A receiver may join a
new authenticated session above sequence 1 after earlier HTTP attempts failed;
once replaced, that retired session cannot become active again. A source-wall
freshness bound rejects old captures, and an atomic high-water checkpoint in
`/dev/shm` preserves active/retired session state if only `navassistd` crashes
and restarts. A manager restart disarms Track Mode before the process can run.

Transport freshness cannot make an old SDK callback fresh: active use also
requires phone location accuracy no worse than 25 m, location observation age
no more than 1 s, guidance observation age no more than 2 s, a known coordinate
system, route matching, and healthy C3XL GPS/localization inside the geofence.
The local ECEF position standard deviation must be at most 10 m, and the point
must remain at least 20 m plus that uncertainty inside the surveyed boundary.
Only Android/iOS `realtime` navigation can become control-valid; simulation and
generic track sources remain diagnostic-only.

## Active scope

`NavigationSpeedController` can only lower the common cruise speed ceiling for
an admitted maneuver below 60 km/h. It never requests a stop or acceleration,
and it leaves `controlsd`, lateral curvature, CarState, CarController, and Panda
unchanged. On Tesla it additionally requires fresh `carStateSP` proof that SP,
not stock longitudinal control, owns the vehicle. Active P0 deceleration is
allowed only with the official longitudinal planner, whose cruise contribution
is limited to -1.2 m/s²; the experimental and TN-NoDEC backends fail closed.
Lead, FCW, or other existing safety sources may independently request stronger
deceleration. Driver-confirmed lane changes
continue through the existing physical turn-signal/DesireHelper path; P0 does
not change either model runner's DesireHelper ordering or road-edge behavior.

Follow the stationary gates and speed progression in
[`docs/NAVASSIST_CLOSED_COURSE_P0.md`](../../../docs/NAVASSIST_CLOSED_COURSE_P0.md)
before any active test.

Android P0 does not derive a directional `exit_left/right` or `ramp_left/right`
event from road text or from road type 6/9, so automatic high-speed exit handling
is not implemented. iOS is schema-reserved but has no client implementation yet.
