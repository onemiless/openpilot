# Sync 评估：dev vs moumou758/sp260728XL-tici（上游同步可行性）

> 生成日期：2026-08-03。基线：`46b9253729`（两分支共同基点）。
> dev 相对基点新增 478 提交；target 相对基点新增 225 提交，其中 dev 未含 229 个。

## 一、结论（先看这里）

**不建议直接在 dev 上全量 merge target 分支。** 两分支的真正差距不是"少量功能缺失"，而是**上游基线差了约 200 个提交 + 一次全仓库目录重构**。正确做法是在新上游基线上重建分支，再把 dev 的 Tesla 定制按功能组重新应用。小修复（如 lagd、SCC-M、MADS）可以随时 cherry-pick，本文评估针对的是"完整同步"。

## 二、上游增量构成（229 个 dev 未含的 target 提交）

| 主题 | 数量 | 代表性提交 | 对 dev 的影响 |
|---|---|---|---|
| 结构/依赖/CI | ~37 | 目录重构 `openpilot/`（#38219/#38220/#38223）、"the one true car.capnp"（#38221）、uv 打包、子模块即依赖（#38300/#38314）、cabana 去 Qt、webrtc 去 av | **最大**：全仓库路径/构建/依赖体系变化 |
| 模型/modeld | ~24 | 单模型 ONNX（#38173）、enqueue in policy、usbgpu、lebowski 模型、modeld_v2 安全校验（#1855）、drivingModelData 压缩（#38165） | 中：与 dev 的 modeld_v2 Tesla 定制相邻 |
| 相机/webrtc/athena | ~25 | 直播、clip 宽幅、teleop、编码器关键帧、libdatachannel | 中：dev 未跟进，属新功能 |
| 控制/纵向 | ~15 | longcontrol 简化（#38337）、删除 per-car stopping 调参（#38394）、lateral maneuvers（#38159）、lane change 简化（#38229）、latcontrol curvature（#38141） | 中：会与 dev 的 Tesla 纵向/变道定制冲突 |
| DM | ~5 | lockout 渐进（#38358）、escalation 规格（#38244） | 中：dev 的 policy.py 是旧结构 |
| XL/MADS/Tesla | ~17 | XL change 系列（dev 已含等价）、MADS 屏幕激活（#1808，逻辑已核对）、相机偏移 UI（已移植）、lagd（已移植） | 低：多数已核对 |
| 其余 | 同步合并、小修复、日志 | — | — |

## 三、结构性差异（决定同步方式）

1. **目录布局**：上游把全部代码移入嵌套 `openpilot/`（`5edc0bd89d`、`37eda06c95`、`20e0f21b58`）。dev 是根目录布局。跟随上游 = 全仓库导入路径改写；不跟随 = 每次 sync 都要做路径映射，长期持续冲突。
2. **cereal/car.capnp 统一**（`df1663c58d`）+ `LeadData.status → present` 等 schema 改名，波及所有消费方。
3. **构建/依赖**：uv 打包与子模块声明、删除 av/libyuv/libjpeg/pyserial/opencv 等、webrtc 换 libdatachannel。
4. **子模块**：opendbc 上游新增 VW MEB（ID.4）等新平台；panda 上游对应 target 的 "xl test" hack（不可用）。

## 四、与 dev Tesla 定制的冲突面（核心风险）

dev 的核心 Tesla 文件在 target 独有提交中均被触碰：

| 文件 | 触碰提交数 | 冲突内容 |
|---|---|---|
| `system/hardware/hardwared.py` | 6 | 上游硬件清理 vs dev 离线唤醒关机流程（`request_panda_deepsleep`、`CanShutdownGate`、bus1 静默门控） |
| `system/hardware/power_monitoring.py` | 3 | 上游 `should_shutdown` vs dev 完整关机逻辑 |
| `common/params_keys.h` | 5 | 上游增删参数 vs dev 约 28 个 Tesla/MPC/离线唤醒参数 |
| `selfdrive/selfdrived/selfdrived.py` | 6 | 上游状态机/事件 vs dev Tesla split-control、AP Hybrid、`AP_HYBRID_ACTIVE` |
| `selfdrive/selfdrived/state.py` | 3 | 上游 disable 优先级 vs dev MADS 联动 |
| `sunnypilot/mads/mads.py` | 2 | MADS 上游改动（dev 已含等价修复） |
| `selfdrive/car/car_specific.py` | 3 | 上游事件 vs dev Tesla 事件过滤 |

另外 dev 独有、上游不会触碰但 sync 时必须逐项验证的文件：`opendbc_repo` 的 Tesla 定制（carstate_ext、coop_steering、转向灯/限速/动态 ACC）、`selfdrive/debug/tesla_*`（CAN 可视化 web）、参数键注册。

## 五、推荐路径（分三步）

1. **短期（已完成）**：小修复 cherry-pick —— lagd MAX_LAG（#38307）、SCC-M 二次根（#1816）、cruise fault 优先级（#37557）、MADS Pause（#1871）均已核对/移植；相机偏移 UI（#1813）已移植。
2. **中期（正式 sync）**：不要在 dev 上 merge。建议：
   - 以 target 基线（嵌套 `openpilot/` + 2026-07 上游）建新分支；
   - 把 dev 的 Tesla 定制按功能组"重新应用"过去：离线唤醒（panda + 硬件）、AP 混合/协作转向、限速/转向灯/动态 ACC、CAN 可视化 web、参数键；
   - 4 个核心冲突文件优先解决，**保留 dev 版本语义**；
   - opendbc/panda 子模块升到新基线的同时重新应用 dev 定制（stopping 调参、bootkick/wake_monitor、Tesla 安全参数）。
3. **长期**：与上游保持周期性 sync，避免再次积累 200+ 提交差距。

## 六、明确不建议

- 在 dev 上直接 merge target（目录重构 + 200 提交，冲突面大，会把 Tesla 定制卷入大合并）；
- 同步 target 的 panda "xl test"（伪装 Tres 的 hack，破坏 dev 设备/唤醒逻辑）；
- 一次性搬入全部上游重构（webrtc/athena/modeld/cabana），除非确实需要这些功能。

## 七、下一步需要确认的问题

1. 是否接受上游嵌套 `openpilot/` 目录布局（跟随上游）？——这决定 sync 是一次性大改还是持续路径映射。
2. sync 范围：只追 sunnypilot 上游，还是连同 commaai/openpilot 全部重构一起？
3. 时间窗：建议在"无重大 Tesla 功能开发中"的窗口做，冲突文件需人工 review。
