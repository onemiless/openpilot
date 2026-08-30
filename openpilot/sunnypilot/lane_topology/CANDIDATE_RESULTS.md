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

The initial image-row continuity rule did **not** pass: low-resolution compression and shadows produced false solid/dashed results. It was replaced with a metric and temporal classifier. The final classifier interpolates each model lane every 0.5 metres from 5–50 m, projects those samples into the synchronized camera Y plane, measures line contrast normal to the projected curve, and reasons about physical lit/dark run lengths. A dashed result requires at least three lit runs, two complete internal gaps, bounded run-length variation, and repeated dominant evidence over multiple frames. A solid result requires high coverage with no internal dark gap longer than 1.5 m. Irregular occlusion remains `unknown`.

The final real-time-equivalent replay is intentionally conservative. On the 1928x1208 public segment it retained 199 unknown boundary observations out of 737 tracked observations; manual overlays show stable inner dashed lines and continuous boundaries correctly, while an occluded or one-sided result remains hidden. The live HUD is shown only when both boundaries of the ego lane have stable non-unknown types. Its compact label is `L:DASHED|SOLID · LANE current/total · R:DASHED|SOLID`.

`LaneTopologyUIBridge` reads the already-subscribed modelV2 at approximately 4 Hz. `AugmentedRoadView` reuses its existing camerad `VisionBuf`, exposes only the zero-copy Y plane, and updates image evidence when camera/model frame IDs differ by no more than three. It does not add a camera client, service, schema field, parameter, process, GPU call, modeld hook, planner input, or control dependency. Offroad transition resets geometry and temporal marking state.
