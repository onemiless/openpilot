# Tesla SP 功能迁移实施报告

## 结果

已在 `codex/tesla-tools-migration-20260811` 上按 CPV9 现有架构重新实现两项功能，没有 cherry-pick 来源提交，也没有替换 `card.py`、Tesla CarController、Tesla safety 或 `longcontrol.py`。

实施基线为 `0c39cc20bec3d8e1a8a5db8b7850df31a869168c`。来源行为参考 `dev-new@1a623470107b758086ff57d7615ca6ae6ec16cac`；分析期间来源只发生 Panda gitlink 更新，两项功能代码未变。

## 最终行为契约

### 网页转向灯测试

- `EnableTeslaTools=0` 为默认状态；关闭时 8090 进程不启动，Panda turn-test flag 也不启用。
- 开启并重启后，访问 `http://设备IP:8090`，可发起左/右测试、取消并查看状态。
- 网页请求不能独立强制点灯：Card 必须持续收到新鲜 `modelV2` 变道上下文，`CC.latActive` 必须为真，方向必须匹配。按用户最终确认，`laneChangeFinishing` 阶段继续保持转向请求，只有本次变道状态回到 `off` 后才以 `lane_change_complete` 进入取消流程；制动、横向失活、上下文过期或超时仍会提前取消。
- `0x3E9` 只从 bus 1 的新鲜 OEM idle 帧重建；更新 request/reason/counter/checksum，其余字段必须与模板一致。
- Panda safety 使用独立 flag、1.5 秒模板有效期、12 秒/64 帧 session 限制、方向连续性和显式 cancel 规则。没有扩大现有 ARS408、MADS、转向角或纵向帧权限。
- 按用户当前测试要求，8090 暂无认证。服务没有 CORS 通配、没有通用 Params 写接口，限制 4 KiB 请求体和单客户端每秒 5 次动作请求。网页显著提示测试结束后关闭参数并重启。

调用链：

```text
Browser :8090
  -> Tesla Web narrow REST API
  -> JSON Params request (5 s TTL)
  -> Card request/context service
  -> TurnSignalController
  -> Tesla CarController incremental CAN list
  -> Panda Tesla safety
  -> bus 1 / 0x3E9
```

### Tesla 原车巡航速度同步

- `TeslaSpeedSyncEnabled=0` 为默认状态。
- 只在 Tesla openpilot longitudinal、`SpeedFromPCM=1`、功能开关均在启动时成立后配置 Python/Panda 两层 flag。
- 唯一目标为新鲜且 active 的 `carrotMan.nRoadLimitSpeed + AutoRoadSpeedLimitOffset`；不读取 `desiredSpeed`、`cruiseTarget`，也不使用 `CarState.speedLimit` 后备路径。
- 不修改油门、刹车、MPC 或 `longcontrol.py`。控制器从 bus 1 新鲜 idle `0x3C2` 克隆帧，每次只模拟右滚轮 `+1/-1` 显示单位。
- 运行时要求 `CC.enabled && CC.longActive`、Tesla cruise enabled、未制动、未 cancel、非 Tesla AP、目标有效。
- 目标稳定 0.5 秒后才执行；应用层最短发送间隔 0.5 秒，每个 tick 等待 Tesla 设速反馈，1.2 秒无反馈后对同一签名停止重试。
- 任意手动非零拨轮动作暂停自动同步。上下或下上在不超过 1 秒内连续出现时恢复；超过 1 秒继续保持手动暂停。
- Panda safety 另设 0.25 秒硬下限、1.5 秒 OEM 模板有效期、仅允许 `+1/-1` 且要求 `controls_allowed`。

调用链：

```text
carrotMan.nRoadLimitSpeed + AutoRoadSpeedLimitOffset
  -> TeslaSpeedTargetProvider (1 s freshness)
  -> Card
  -> SpeedSyncController
  -> Tesla CarController incremental CAN list
  -> Panda Tesla safety
  -> bus 1 / 0x3C2
  -> Tesla PCM set speed feedback
```

## 现有功能保护

- ARS408：保留 Sensor ID、配置/过滤/NVM 请求、14 Hz radar 更新、`0x300/0x301` 20 Hz motion 发送和原 safety 字段限制；只将注释更新为 bus 1 由安全网关管理。
- MADS：未改状态机或 `selfdrived`；Speed Sync 以 `longActive` 而不是 MADS/`latActive` 为触发条件，MADS-only 不会启动速度同步。
- Cooperative steering：未改控制器与 Panda 横向权限逻辑。
- Tesla longitudinal：保留原 `0x2B9` 路径、stock AEB passthrough 和 LONG_CONTROL bit；Speed Sync 使用独立 bit。
- `longcontrol.py`：零改动。

## 尚未完成的物理验证

本报告只证明代码、单元测试、Safety 仿真和本机编译结果，不等同于 Panda 实机或车辆验证。仍需按顺序完成：Panda 刷写后的 accept/reject 抓包、静止车辆左/右/取消、巡航 70→80 与 80→70、手动拨轮暂停/1 秒反向恢复，以及 MADS + ARS408 + Tesla longitudinal 联合道路验证。

---

# 历史快照：Tesla ARS408 Migration Report（2026-08-09）

以下内容保留仓库原有报告的关键事实用于追溯；其中 motion TX 禁用等状态已被后续 ARS408 分支演进取代，不能代表本分支当前状态。

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

## CAN 安全边界（历史状态）

当时 ARS408 与 Tesla vehicle CAN 共线且尚无隔离/抓包证明，因此实现保留 frame 构造和接口，同时以 `ARS408_MOTION_INPUT_ENABLED=False` 与 Panda allowlist 双层阻断 `0x300/0x301`。该结论只描述 2026-08-09 快照。

## Bug 修复记录

两轮审计修复了构建、Radar Monitor 隔离、通用接口签名、测试 mock/API、跨平台共享内存路径、Hyundai 空指纹初始化、Fleet Manager 地址搜索和 Carrot Radar 异常处理问题。第二轮还撤回了缺少 tici 验证的不必要 FFmpeg/OpenMAX 源码改写。详情见 `modified_files.md` 和 `bug_audit_report.md`。

## 当时未验证项

- 无可用 Tesla ARS408 route，未执行 Replay 的 `RadarState/CarState/ControlsState/LongitudinalPlan` 时序验证。
- 未连接 C3/C3X/Panda/ARS408，未完成 Monitor、Fusion、高速 ACC 三阶段实车验证。
- macOS 构建只证明 UI 可编译链接。
