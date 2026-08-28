# Radar lane occupancy

`radarlanesd` publishes the read-only `radarLaneStateSP` service from
`modelV2` lane geometry and `radarTracks` points. It reports occupancy and the
closest forward radar target in the left-adjacent, current, and right-adjacent
lane, plus a bounded global list of unique targets.
Navigation route data is intentionally not an input: it describes route intent,
not the live lane boundaries around the car.

This service intentionally does not modify or replace `radarState` and is not
consumed by longitudinal planning, FCW, lane-change control, or vehicle CAN.

## Semantics

- `occupied`: at least one radar target is inside the evaluated forward lane
  corridor.
- `clear`: trustworthy model lane boundaries cover the reported distance and
  the current accepted front-radar tracks contain no target in that corridor.
- `unknown`: the geometry or radar data cannot prove the corridor is clear.

All accepted targets participate in occupancy and cut-in-candidate selection.
The message publishes up to 24 unique target details in `targets`; `laneMask`
identifies left/center/right membership and boundary targets can set two bits.
`uniqueTargetCount` remains the full count, while `targetsTruncated` explicitly
reports that the bounded list omitted lower-priority details. Predicted cut-in
candidates are prioritized before distance, so a farther overtaking target is
not hidden by a closer target in the same lane.

Cut-in motion is estimated from the change in path-relative `dPath` across two
fresh radar timestamps. Repeated model ticks do not reapply the same radar
sample. `yvRel` is exposed only as raw diagnostic data because its ARS408 sign
has not yet been validated for this installation; it is not used to decide
cut-in direction. `cutInCandidate` means a measured lateral trend would reach
the center-lane boundary within the published three-second horizon. It is a
read-only candidate, not a collision decision or control command.

When an outer lane line is unavailable, the classifier can still report
positive evidence inside a nominal 3.6 m path-relative corridor. Absence in an
estimated corridor remains `unknown`, never `clear`.

This branch adds optional ARS408 object class, existence-probability, and
dynamic-property fields to `radarTracks`, then copies them into the read-only
lane service. Other radar backends retain safe unknown defaults. Classification
is radar-produced rather than camera-confirmed and can still be wrong. A front
radar also cannot establish rear
blind-spot clearance; consumers must not use this message as permission to
change lanes.

The three lanes are relative to the current `modelV2` frame, not stable map
lane identifiers. Consumers must require a live service and valid event, treat
`unknown` as unconfirmed, and must not carry a lane identity across a lane
change. `clear` does not prove complete sensor coverage and is not a substitute
for side/rear blind-spot monitoring.

The standard C3XL on-road renderer subscribes to this service only for the
left and right adjacent-lane display; the center lane keeps the stock SP lead
chevron without an added marker. Each adjacent lane displays at most one unique
representative target and reuses the exact stock SP chevron geometry, yellow
glow, red fill-alpha calculation, and `ChevronInfo` text formatting. There is
no L/C/R badge, class label, custom color, or custom text box. A predicted
cut-in target has priority over the closest target. Adjacent-lane markers use
the same 120 m forward limit as lane fusion instead of the stock path renderer's
100 m limit.
The legacy `leadOne`/`leadTwo` chevrons are also display-deduplicated by track
ID and spatial proximity. Leads without a stable common track use 3 m hide /
5 m show longitudinal hysteresis when laterally close. The ARS408 tracker remains
the sole owner of target lifetime, ID handover, and missed-cycle grace. While the
current radar track remains alive, adjacent-lane display requires a 6 m distance
advantage before switching to an ordinary challenger; cut-in candidates can
switch immediately. Lane membership also uses 0.5 m of additional boundary
hysteresis only for a track ID that occupied that lane in the previous radar
cycle. This stabilizes model-boundary jitter without extending the radar
target's lifetime: when the native radar ID disappears, its lane history is
removed. Classified cars, trucks,
pedestrians, motorcycles, and bicycles are never removed by the roadside-clutter
display filter. A radar-native stationary point/wide/unknown target outside the
center corridor is hidden even when isolated. Targets without a native static
property require three or more world-stationary side targets in a narrow
lateral band spanning at least 15 m longitudinally. Radar-native stationary
properties also prevent path motion from creating a cut-in candidate. Center
stopped targets and classified stopped vehicles/VRUs are retained.
These rules change only rendering and do not
remove any target from `radarTracks`, `radarState`, or control.
