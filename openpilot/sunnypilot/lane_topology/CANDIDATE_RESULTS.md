# Lane-topology candidate decision

Baseline: `dev-sp-egpu` at `10c9442f479356b2e0f43e33ce2d8be999b4d4f2`.

All neural-network measurements below were executed Offroad on the target C3XL with a UT3G USBGPU at 5000 Mbps. They are screening results, not claims derived from desktop-GPU benchmarks.

| Candidate | Bound artifact SHA-256 | Steady p50 | Steady p99 | USB result | Decision |
| --- | --- | ---: | ---: | --- | --- |
| Official YOLOP 320 full | `86d6e8b6dfdef195c061e9bcad82d9487bb5ee1ac4a1cf9a3dc4736657a07369` | 99.324 ms | 145.964 ms | 227/227 F2 reads, 0 failures | Reject |
| YOLOP lane-only FP32 | `03690d106c5e59f8c6c55aa9a24b4bca795db1c7e1335887e26c50f43ee2feaf` | 86.857 ms | 128.282 ms | 215/215, 0 failures | Reject |
| YOLOP lane-only FP16 | `b7b09f3e918627b124943dcb7fa819b4c6968c7528f8eef9a474a082d4ef65ba` | 87.152 ms | 164.305 ms | 215/215, 0 failures | Reject |
| Official UFLDv2 TuSimple ResNet18 | `ea26570cc22ded75364e6a151236b8a496e9f700775501b4ed0f10c2c3204dc0` | 396.546 ms | 450.357 ms | 73/73, 0 failures | Reject |
| Official UFLDv1 TuSimple ResNet18 | `46a1864bcc8c13497fe0c18d4584fed993482d5170d3152ef5e138ff1e471b2d` | 348.654 ms | 410.358 ms | 15/15, 0 failures | Reject |

The auxiliary budget is 15 ms with automatic fail-closed disable after two overruns. None of the no-training neural candidates is suitable beside the current driving model on this runtime. The USB traces were complete, so the rejection is caused by end-to-end execution cost, not a broken 5 Gbps link.

## Selected candidate

Reuse the four `modelV2.laneLines` and `modelV2.laneLineProbs` already emitted by the active driving model. Run the topology geometry and tracker on CPU. This adds no model, no GPU owner, no USB traffic, and no model-selection parameter.

The target-device CPU stress test completed 100,000 full adapter-plus-topology iterations: mean 1.674 ms, p50 1.639 ms, p95 1.791 ms, p99 2.062 ms, and one 21.918 ms scheduling outlier. The computed result was four visible boundaries, three visible lane spaces, and ego-lane index 1 from both left and right. This passes the 15 ms p99 budget without using the GPU.

The primary model does not publish solid/dashed semantics. Marking type therefore remains `unknown` unless synchronized image evidence is explicitly supplied to a marking classifier. Returning `unknown` is intentional; deriving solid/dashed from lane geometry alone would be an unsupported guess.

The auxiliary neural candidates remain shadow-only. The validated primary-model geometry is exposed through the read-only UI bridge described below; cereal schemas, process configuration, `modeld`, planner, controls, Panda, Params, and UT3G firmware remain unchanged.

## Real-route replay follow-up

Four user route segments were recovered from the archived traffic-control logs in `~/Downloads`. Each segment contains 1,200 `modelV2` messages, 1,200 qcamera encode indices, calibrated extrinsics, and a synchronized 526x330 qcamera video. A separate public openpilot CI segment supplied 1,200 synchronized 1928x1208 fcamera frames.

The replay exposed and fixed a coordinate-boundary error: modelV2 is right-positive in y, while this module's public road convention is left-positive. `PrimaryModelLaneTopologyAdapter` now negates model y exactly once at its boundary. Camera projection continues to use the original model convention and visually aligns with lane markings.

At 4 Hz, all four user segments produced 239 exact model/video matches out of 240 sampled frames; the missing sample in each is the segment-start encoder/model offset. The image overlays confirmed that the four model lines project onto the visible road markings. A `0.50` enter / `0.25` exit probability hysteresis reduced ego-lane index transitions from `7/3/8/0` to `4/3/4/0` without retaining intersection lines as valid lanes.

The initial image-row continuity rule did **not** pass: low-resolution compression and shadows produced false solid/dashed results. It was replaced with a metric and temporal classifier. The final classifier first finds the two model source IDs that immediately surround vehicle y=0, then ignores every outer line. It interpolates only those ego-lane boundaries every 1 metre from 8–35 m, projects the samples into the synchronized camera Y plane, measures line contrast with vectorized lane-tangent strips searched along the projected normal, and reasons about physical lit/dark run lengths. A dashed result requires at least three lit runs, two complete internal gaps, bounded run-length variation, and repeated dominant evidence over multiple frames. A solid result requires high coverage with no internal dark gap longer than 1.5 m. Irregular occlusion remains `unknown`.

The final real-time-equivalent replay is intentionally conservative. Manual overlays show only the current lane boundaries in green/yellow; outer lines stay grey and never contribute type evidence. A change in the ego source-ID pair resets all temporal marking scores so a lane change cannot inherit the previous lane's type. An occluded or one-sided result remains hidden. The live HUD is shown only when both boundaries of the ego lane have stable non-unknown types. Its compact label is `L:DASHED|SOLID · LANE current/total · R:DASHED|SOLID · LINES visible`.

`LaneTopologyUIBridge` reads the already-subscribed modelV2 at approximately 4 Hz. `AugmentedRoadView` reuses its existing camerad `VisionBuf`, exposes only the zero-copy Y plane, and updates image evidence when camera/model frame IDs differ by no more than three. It does not add a camera client, service, schema field, parameter, process, GPU call, modeld hook, planner input, or control dependency. Offroad transition resets geometry and temporal marking state.

The target-device synthetic gate made all four model lines high-probability while requiring only the detected ego source pair `(1, 2)` to be classified. Across 300 iterations on a 1928x1208 Y plane, the outer lines remained `unknown`, the ego boundaries produced the expected `DASHED/SOLID` result, and timing was p50 6.36 ms, p95 7.45 ms, and p99 8.18 ms. Production runs at approximately 4 Hz and does not copy or convert the full Y plane.

## Blur robustness follow-up

The fixed 14-level contrast threshold remains authoritative whenever it yields
a valid solid/dashed result. Only an otherwise-unknown frame enters a bounded
adaptive path: its threshold is selected between 6 and 14 from the strip's
90th-percentile contrast, and the recovered line must have either a coherent
normal-offset trend or a smooth blurred normal profile. Adaptive evidence is
down-weighted by measured contrast before entering the existing temporal
dominance filter. Severe blur or unstructured evidence remains `unknown`; it is
never forced to a lane type.

Synthetic low-contrast solid and 3 m/6 m dashed fixtures remained correct
through Gaussian blur sigma 4 at 526-pixel reference width. Across 24
contrast/blur combinations, every result was the clear type or `unknown`; no
solid/dashed flip occurred. One hundred independent textured-noise frames never
produced a temporally confirmed marking.

On the synchronized 1928x1208 route with synthetic Gaussian blur sigma 6, the
original fixed path retained 40 of 158 clear known source-slot observations;
the adaptive path retained 76 of 158, with zero solid/dashed flips. Stable
dashed boundary observations increased from 52 to 133 while solid remained 15.
At sigma 12, the adaptive path still retained 40 known observations with zero
flips; erased evidence remained unknown. On the unblurred full-resolution
route, dashed observations increased from the fixed-path 198 to 229 while
solid stayed 15. Four clear 526x330 tici routes retained their prior results,
apart from three additional dashed observations and no lost solid result.

## Low-resolution recall and frame-rate follow-up

The four original tici qcamera segments remain the primary recognition gate.
Each contains 1,200 synchronized 526x330 frames at 20 Hz; 1928x1208 data is
used only for timing and resolution comparison. Production image
classification now runs at 10 Hz (`IMAGE_CLASSIFIER_DIVISOR = 2`) while
geometry remains at 20 Hz. A complete two-boundary 1928x1208 bridge benchmark
on the C3XL measured mean 14.180 ms, p95 15.329 ms, p99 16.515 ms, and maximum
18.284 ms, leaving substantial margin in the 100 ms classifier period.

The model-line enter threshold remains 0.50; only the already-confirmed-line
exit threshold changed from 0.25 to 0.20. On the recorded route this raised the
approximate simultaneous inner-line visibility from 47.4% to 48.3% while
reducing visibility transitions from 133 to 121. More aggressive 0.35/0.15
thresholds were rejected because the earlier overlays showed intersection-line
retention.

Low-resolution compression often leaves only two visible dash runs in the
8-35 m metric window. Such a frame may now contribute bounded partial-dash
evidence only when it still contains a physical internal gap and passes the
existing coherent-offset or smooth-profile structure test. Its confidence is
capped at 0.45; it is not a single-frame control result. Partial evidence may
acquire `dashed` from `unknown`, but can never replace a previously confirmed
`solid`. A transition away from confirmed solid still requires the original
complete dashed evidence (at least three lit runs, two complete gaps, and five
transitions).

At the old 4 Hz configuration, stable known source-slot observations covered
725 of 924 source slots with valid metric samples (78.5%). The final 10 Hz
configuration covered 2,078 of 2,320 eligible source slots (89.6%). A
same-frame 10 Hz differential against the old classifier increased stable
known source slots from 1,870 to 2,078 (+11.1%): 211 observations were added,
three were lost, and there were zero solid/dashed flips. Manual inspection of
added 526x330 frames showed visible dashed markings. With synthetic Gaussian
blur sigma 4 applied to all four qcamera routes, 1,414 of 2,078 clear known
slots retained the same type and there were zero solid/dashed flips.

Using the Snapdragon 845 GPU beside the external Chestnut GPU is
computationally plausible but is not yet a production source. A random-weight
1x1x32x256 three-layer ROI CNN on tinygrad QCOM measured mean 8.158 ms, p95
8.797 ms, and p99 11.196 ms. Existing YOLOP and UFLD assets do not publish
marking type; the YOLOP lane-only ONNX also failed current QCOM code generation
with a UOp verification error. A future QCOM ROI classifier therefore requires
a specifically trained `solid/dashed/unknown` artifact, independent manual
labels, and an onroad contention test with the QCOM warp. No untrained or
geometry-only neural candidate is shipped in this change.

## Release cleanup

The failed neural candidates remain documented by their bound hashes, device reports, and the table above, but their implementation was removed before release. Deleted code includes YOLOP, UFLDv1, UFLDv2, the original image-row classifier, the abandoned auxiliary runner/scheduler, their benchmark CLIs, and their dedicated tests. The release package retains only the primary-model geometry, ego-boundary selection, metric/temporal marking classifier, UI bridge, real-route replay tool, primary CPU benchmark, and core regression tests. No rejected candidate can be imported or accidentally activated at runtime.
