# Tesla ARS408 Migration Report

## 结果

已在最新 `onemiless/cpv9-dev-tsl` 上创建交付分支 `cp0809`，采用函数级迁移，没有 merge Reference，也没有批量 cherry-pick。原有 steering、brake、ACC 核心逻辑和 model 输入/输出均未修改。

## Task 0-9

| Task | 状态 | 结论 |
|---|---|---|
| 0 基线分析 | 完成 | 见 `baseline_report.md`；Base 比 mooo 多 2 个提交，与 juyun 已明显分叉 |
| 1 Radar Interface | 完成（软件） | 增加 track grace、拒绝原因、缺帧签名、状态元数据和模式语义 |
| 2 ARS408 CAN | 部分完成（安全约束） | startup/event 配置和 motion 编码完成；共享 Tesla CAN 上 motion TX 保持硬关闭 |
| 3 CarController | 部分完成（安全约束） | `send_radar_motion()` 已实现，但 `ARS408_MOTION_INPUT_ENABLED=False`，不修改现有控制路径 |
| 4 Interface/Params | 完成 | 0 OFF、1 Monitor、2 Fusion、3 Debug；本架构 Params registry 位于 `common/params_keys.h` |
| 5 Controls 审核 | 完成 | `liveTracks -> radard -> radarState -> longitudinal_planner/longcontrol` 调用链存在且未改核心逻辑 |
| 6 Model 检查 | 完成 | `selfdrive/modeld` 无迁移差异，本次也没有 model/schema 输入变更 |
| 7 UI | 完成（构建） | Tesla HUD 显示 mode、online、object、lead source、CAN；设备目视检查待做 |
| 8 Safety | 完成 | 未扩大 allowlist；配置帧维持严格 bus/DLC 限制；`0x300/0x301` 明确测试为阻断 |
| 9 测试 | 软件完成 | 单测、lint、compileall、完整 SCons 通过；replay 与三阶段实车测试待硬件执行 |

## Controls 与 Model 审核

- `selfdrive/controls/radard.py` 消费 `liveTracks` 并发布 `radarState`，lead fusion 保持原实现。
- `selfdrive/controls/lib/longitudinal_planner.py` 将 `radarState` 传入 MPC，并发布 `hasLead`。
- `selfdrive/controls/lib/longcontrol.py` 在停止/平滑停止判断中读取 `radarState.leadOne`。
- 没有改动上述三个文件；没有改动 `selfdrive/modeld` 或模型输入结构。

## CAN 安全边界

文档要求运行期周期发送 speed/yaw，但当前 ARS408 与 Tesla vehicle CAN 共线，`0x300/0x301` 尚无隔离总线或实车抓包证明不会与原车报文冲突。因此实现保留 frame 构造和调用接口，同时由两个独立层阻断发送：

1. `ARS408_MOTION_INPUT_ENABLED=False` 使控制器不产生 motion TX。
2. Panda safety 测试确认 bus 1、DLC 2 的 `0x300/0x301` 均不在 allowlist。

这是一项有意的安全偏差，不应被描述为已经完成实车 motion input。只有在物理隔离或完成 CAN conflict capture、安全审查和 Panda allowlist 定向测试后，才能启用。

## Bug 修复记录

两轮审计修复了构建、Radar Monitor 隔离、通用接口签名、测试 mock/API、跨平台共享内存路径、Hyundai 空指纹初始化、Fleet Manager 地址搜索和 Carrot Radar 异常处理问题。第二轮还撤回了缺少 tici 验证的不必要 FFmpeg/OpenMAX 源码改写。详情见 `modified_files.md` 和 `bug_audit_report.md`。

## 未验证项

- 无可用 Tesla ARS408 route，未执行 Replay 的 `RadarState/CarState/ControlsState/LongitudinalPlan` 时序验证。
- 未连接 C3/C3X/Panda/ARS408，未完成 Monitor、Fusion、高速 ACC 三阶段实车验证。
- macOS 构建证明 UI 可编译链接，不证明设备屏幕布局、雷达物理在线或控制效果。
