# NavAssist closed-course P0

This module is an isolated, closed-course-only ingress path for high-level
mobile navigation observations. It does not accept actuator, curvature,
acceleration, CarState, or CAN commands.

## Arming

The manager keeps the network-only `navassistd` receiver available on a Tesla
C3XL so an installed TesNav App can reconnect without a manually copied token.
`lane_topologyd` still runs only onroad. Network availability grants no control
authority. Active use separately requires valid realtime navigation, SP control
authority, and valid local localization. No per-drive Track Mode, token, or
geofence configuration step exists. The normalized snapshot remains invalid
unless C3XL's own `liveLocationKalman` is healthy; enabling SP never bypasses
that condition.

On first use, C3XL trusts a bounded set of up to four self-signed App identities,
and it adds each new identity only while offroad. Those P-256 public keys are
persisted as `NavAssistPairedApp`; unknown App keys cannot replace existing
entries while onroad. The C3XL device private key
is stored in the `PERSISTENT | DONT_LOG` `NavAssistDevicePrivateKey` Param and never transmitted. Clearing or
changing an App identity requires an explicit offroad maintenance action; it is
not a network command. First-use TOFU removes shared-secret configuration, but
it cannot identify the owner before the first pin: pair only on a controlled
private LAN.

## Transport

The phone discovers C3XL without scanning every HTTP address. It sends a signed
IPv4 UDP broadcast to port 7765, then constructs the HTTP URL
from the source IP of a verified unicast offer. The offer never supplies a host
name or IP address. Both datagrams are compact JSON, at most 512 bytes, with
exact field sets:

```json
{"messageType":"navassist_discovery_request","schemaVersion":3,"nonce":"<32-lower-hex>","appKeyId":"<32-lower-hex>","appPublicKey":"<P-256-X.509-SPKI-base64url>","signature":"<ECDSA-DER-base64url>"}
{"messageType":"navassist_discovery_offer","schemaVersion":3,"nonce":"<same-nonce>","appKeyId":"<same-app-key-id>","deviceId":"<32-lower-hex>","devicePublicKey":"<P-256-X.509-SPKI-base64url>","port":7766,"path":"/v3/snapshot","signature":"<ECDSA-DER-base64url>"}
```

Both keys use P-256. `appKeyId` and `deviceId` are the lower-case hexadecimal
first 16 bytes of SHA-256 over the canonical 91-byte X.509 SubjectPublicKeyInfo
DER. Public keys and standard DER ECDSA signatures use unpadded base64url. The
request is signed using ECDSA with SHA-256 over the exact UTF-8 bytes below
(newline separators, no trailing newline):

```text
navassist_discovery_request
3
<nonce>
<appKeyId>
<appPublicKey>
```

The offer signature covers:

```text
navassist_discovery_offer
3
<nonce>
<appKeyId>
<deviceId>
<devicePublicKey>
7766
/v3/snapshot
```

With the longest valid P-256 DER signature, the compact request is at most 403
bytes and the offer is at most 484 bytes. Parsers reject noncanonical keys,
invalid curves, duplicate or unknown fields, incorrect primitive types, and
datagrams over 512 bytes. C3XL replies only to RFC1918 IPv4 sources and silently
drops malformed, unauthenticated, unpaired, or rate-limited requests. A bounded
two-second `(source, appKeyId, nonce)` cache suppresses duplicate bursts. The
outstanding random nonce on the phone prevents an old offer from matching a new
round, while HTTP retains separate TTL and persistent sequence replay controls.
A verified offer identifies a candidate; the phone reports C3XL as online only
after an HTTP exchange also succeeds.

POST compact v3 navigation JSON to:

```text
http://<c3xl-private-address>:7766/v3/snapshot
```

Set `X-NavAssist-Key-Id` to the pinned App key ID. Set
`X-NavAssist-Signature` to the App's unpadded base64url DER ECDSA/SHA-256
signature over these prefix bytes followed immediately by the exact HTTP body:

```text
navassist_snapshot
3
POST
/v3/snapshot
<deviceId>
<appKeyId>
<body-byte-length>
<raw-body-bytes>
```

Binding both identities, method, path, byte length, and raw body prevents a
valid snapshot signature from being redirected to another C3XL or request.
Signatures authenticate and protect integrity but do not encrypt location data;
use only a controlled private network.

The receiver bounds request size, rate, and concurrent connections, rejects malformed/non-finite values,
requires a strictly increasing sequence and non-decreasing route revision, and
assigns the control-relevant TTL on C3XL receipt only after also bounding the
signed source-wall timestamp. A receiver may join a
new authenticated session above sequence 1 after earlier HTTP attempts failed;
once replaced, that retired session cannot become active again. A source-wall
freshness bound rejects old captures, and an atomic high-water checkpoint in
`/dev/shm` preserves active/retired session state if only `navassistd` crashes
and restarts. A manager restart leaves the receiver available for the
already-paired Apps; transport availability never grants control authority. If
one paired App owns a fresh active navigation session, snapshots from another
paired App cannot preempt it until the active session expires.

Transport freshness cannot make an old SDK callback fresh: active use also
requires phone location accuracy no worse than 25 m, location observation age
no more than 1 s, guidance observation age no more than 2 s, a known coordinate
system, route matching, and healthy C3XL GPS/localization. The local ECEF
position standard deviation must be at most 10 m.
The phone SDK's `gpsWeak` flag remains visible as diagnostic state but is not a
control gate; explicit accuracy/freshness checks and C3XL localization remain
the control authority boundary.
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
deceleration. An experimental typed `navLaneIntentSP` path can also request one
Tesla physical turn signal. A linked left/right route maneuver may request a
bounded pre-turn lamp with `targetLaneIndex = -1`; DesireHelper explicitly
ignores that display/signal-only intent. A real lane change is authorized only
after fresh lane-index alignment, ego-side dashed evidence, clear BSM, active
SP lateral, Panda TX echo, and physical lamp feedback. A same-direction pre-turn
lamp transfers to the lane-change request without blinking off. This path never
accepts phone curvature or bypasses Panda safety, and every lane is re-observed
before another request.

Follow the stationary gates and speed progression in
[`docs/NAVASSIST_CLOSED_COURSE_P0.md`](../../../docs/NAVASSIST_CLOSED_COURSE_P0.md)
before any active test.

Android P0 does not infer a directional `exit_left/right` or `ramp_left/right`
event from road text alone. Android and iOS can both carry explicit directional
maneuvers, but automatic highway-exit steering is not implemented.
