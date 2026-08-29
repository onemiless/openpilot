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

This branch remains shadow-only. It does not modify cereal schemas, process configuration, `modeld`, planner, controls, Panda, UI, Params, or UT3G firmware. A production/UI hook should only be added after an onroad replay validates accuracy and image synchronization.
