# Tesla 自动设定速度（“自动加减速”）分析

## 1. 范围、快照与功能名纠正

本报告只做分析，不修改控制、UI、Params、Panda safety 或车辆接口。

- 来源基线：`sp/dev-new@d2842c7525ab15955b72ac5368cb163b6fe4e5c6`。
- 来源本地 `dev-new` 在分析期间外部推进到 `1a623470107b758086ff57d7615ca6ae6ec16cac`，差异仅为 Panda gitlink；本功能相关文件没有变化。
- 来源 opendbc：`85a463402b4db53aeca79dcca1bc754286adfbba`。
- 目标基线：`cpv9-mads-ars408-motion-track-20260810@0c39cc20bec3d8e1a8a5db8b7850df31a869168c`。
- 用户给定的目标前提：bus 1 默认通过安全网关接入车辆侧，可双向收发拨轮 `0x3C2` 和转向 `0x3E9`。本报告据此分析，不把网关或物理可达性列为阻断项。

### 必须先纠正的前提

来源功能的代码名是 `TeslaAutoSpeedLimit`，UI 名是 **Automatic Tesla Set Speed**。它不是直接向 `actuators.accel` 写加速度，也不是一套新的 `longcontrol`：

- 克隆 Tesla 原车 `0x3C2 VCLEFT_switchStatus` 空闲帧。
- 在来源 bus 1 模拟右滚轮每次 `+1` 或 `-1` 个显示单位。
- 逐步让 Tesla 的巡航设定速度追到 SP 解析出的“道路限速 + offset”。
- 原车 ACC 或 openpilot longitudinal 再根据新的设定速度产生实际加速/减速。

因此本文把它称为**自动设定速度**。把它称为“自动加减速”只描述最终车辆效果，容易与目标已有 Carrot 自动速度、MPC/longcontrol 直接加速度控制混淆。

## 2. 结论先行

1. **来源自动加速逻辑：** 当目标显示速度高于 Tesla 当前设定速度时，每次发一个 `+1` 右滚轮 tick，等车辆反馈后继续。
2. **来源自动减速逻辑：** 当目标显示速度低于当前设定速度时，每次发一个 `-1` tick，流程相同。
3. **不修改 `longcontrol.py`：** 功能控制器位于 Tesla car 层；planner 只提供限速目标。
4. **目标已经有不同语义的自动速度：** `VCruiseCarrot._auto_speed_up()` 修改 openpilot 内部 `vCruise`，会考虑道路限速和 ARS408 lead，但不发 `0x3C2`。
5. **bus 1 可直接作为迁移目标：** 按用户给定前提，`0x3C2` 可双向收发；目标当前缺少的是 parser/card/controller/Panda safety 软件链，而不是物理路由。
6. **不能直接把 `carrotMan.desiredSpeed` 接给滚轮控制器：** 它包含弯道、摄像头、减速带、导航转向等短时综合目标；让 Tesla 物理设定速度追逐这些瞬态值会造成反复滚轮动作和 owner 竞争。

## 3. 来源文件列表

| 文件 | 关键位置 | 作用 |
|---|---:|---|
| `openpilot/common/params_keys.h` | 229 | `TeslaAutoSpeedLimit`，persistent+backup bool，默认 `0` |
| `openpilot/sunnypilot/selfdrive/car/interfaces.py` | 109-137 | 启动时将该参数纳入接口参数快照 |
| `opendbc_repo/opendbc/sunnypilot/car/interfaces.py` | 169-174 | Tesla + OP long + vehicle bus + 参数开启时设置 feature/safety flag |
| `opendbc_repo/opendbc/sunnypilot/car/tesla/values.py` | 11, 26, 44 | `HAS_VEHICLE_BUS`、`AUTO_SPEED_LIMIT` 和 safety SP flag |
| `opendbc_repo/opendbc/car/tesla/interface.py` | 39-42, 53-65 | OP long 能力及 bus 1 `0x3DF` vehicle-bus 检测 |
| `openpilot/sunnypilot/selfdrive/controls/lib/speed_limit/speed_limit_resolver.py` | 24-195 | car/map 限速来源、policy、固定/百分比 offset、last-valid |
| `openpilot/sunnypilot/selfdrive/controls/lib/longitudinal_planner.py` | 46-74, 81-141 | 更新 resolver/SLA，发布 `longitudinalPlanSP.speedLimit.resolver` |
| `openpilot/selfdrive/car/card.py` | 35, 64-73, 258-264, 291-298 | 0.2 s plan freshness、目标提取、raw `0x3C2` 模板捕获、写入 Tesla state |
| `opendbc_repo/opendbc/sunnypilot/car/tesla/carstate_ext.py` | 65-124 | 保存模板、时间、单位、目标、手动动作和恢复手势计数 |
| `opendbc_repo/opendbc/car/tesla/carstate.py` | 88-107, 170-173 | Tesla 单位/当前设定速度及 AP 状态 |
| `opendbc_repo/opendbc/sunnypilot/car/tesla/speed_limit_controller.py` | 6-24, 27-182 | 自动设定速度完整状态机和 `0x3C2` 生成 |
| `opendbc_repo/opendbc/car/tesla/carcontroller.py` | 25-60 | 构造控制器，每周期调用并把 CAN 结果并入发送集合 |
| `openpilot/selfdrive/ui/sunnypilot/layouts/settings/vehicle/brands/tesla.py` | 281-288, 346-363 | 原生 Tesla UI 开关、可见性、offroad/restart 约束 |
| `openpilot/selfdrive/debug/device_settings.py` | 119 | Web/debug 设置中的同一参数，但错误地标成 onroad 可改 |
| `opendbc_repo/opendbc/safety/modes/tesla.h` | 247-257, 418-442, 560-617, 643-679 | `0x3C2` OEM 模板、字段/频率/controls_allowed 校验、flags |
| `opendbc_repo/opendbc/car/tesla/tests/test_speed_limit_controller.py` | 33-218 | 状态机、单位、反馈、手动覆盖、AP、模板等测试 |
| `opendbc_repo/opendbc/safety/tests/test_tesla.py` | 274-312 | speed-button 和 auto-mode Panda safety 测试 |

## 4. 来源完整调用流程

```text
carStateSP.speedLimit / liveMapDataSP
  ↓ SpeedLimitPolicy + fixed/percentage offset
SpeedLimitResolver
  ↓
LongitudinalPlannerSP
  ↓ longitudinalPlanSP.speedLimit.resolver.speedLimitFinalLast
card.get_tesla_speed_limit_context()（plan 必须 fresh ≤ 0.2 s）
  ↓ update_speed_limit_target(target, valid)
Tesla CarState extension
  ↑ 同时从 raw CAN 接收 OEM idle 0x3C2 bus 1 模板
  ↓
Tesla CarController
  ↓ TeslaSpeedLimitController.update()
比较 Tesla 当前显示设定速度与目标显示速度
  ↓ 目标高：+1 tick；目标低：-1 tick
CanData(address=0x3C2, bus=1)
  ↓ sendcan
Panda Tesla safety
  ↓ fresh template / 只改 tick / rate / flag / controls_allowed
Tesla vehicle CAN
  ↓
Tesla 更新巡航设定速度并反馈新的 0x3C2/DI 状态
  ↓
下一 tick 或完成
```

来源的 PCM cruise 分支还会把 `CS.cruiseState.speed/speedCluster` 回写为 `vCruise`（`openpilot/selfdrive/car/cruise.py:53-67`，随后由 `card.py:309-317` 发布）。所以物理滚轮变化会进入后续规划，但仍不是 controller 直接发 accel。

## 5. 自动加速、自动减速与节拍

### 5.1 帧构造

`speed_limit_controller.py:16-24` 要求：

- 地址 `0x3C2`，来源/发送 bus 1。
- 8-byte、mux 1、右滚轮 tick 当前为空闲 `0`。
- 只修改 byte 3 的低 6 bit。
- tick 只能是 `+1` 或 `-1`。

### 5.2 自动加速

```text
target_display - current_display > 0
  ↓
direction = +1
  ↓
模拟右滚轮上调一个 Tesla 显示单位
```

### 5.3 自动减速

```text
target_display - current_display < 0
  ↓
direction = -1
  ↓
模拟右滚轮下调一个 Tesla 显示单位
```

两者共用相同状态机：

- 新目标先稳定 0.5 s。
- 应用层 TX 间隔至少 0.5 s，即名义最大 2 个显示单位/秒。
- 每个 tick 后等待 Tesla 当前设定速度变化作为反馈。
- 1.2 s 内没有反馈则阻断当前 `(target,current)` signature，不无限重试。
- OEM idle 模板最大年龄 1.5 s。
- KPH/MPH 分别换算并四舍五入到显示整数。

Panda safety 的最低 TX 间隔是 250 ms，比应用层更宽松；实际正常路径仍由 500 ms 应用限制控制。

## 6. 触发条件

只有下列条件全部满足才可能发送：

| 条件 | 来源证据 | 不满足时行为 |
|---|---|---|
| 启动时已配置 `TeslaAutoSpeedLimit` | controller 29；interface 169-174 | reset，不发送 |
| Tesla 且 `CP.openpilotLongitudinalControl` | interface 171 | 不设置 feature/safety flag |
| 已检测 `HAS_VEHICLE_BUS` | interface 172；Tesla interface 62-64 | 不配置 |
| `CC.enabled` | controller 93 | reset；MADS-only 不应触发 |
| 未发 cancel | controller 93 | reset |
| Tesla cruise enabled | controller 93 | reset并解除手动 override |
| brake 未按下 | controller 96 | reset pending，不发送 |
| plan/limit target 有效 | card 64-73；controller 96 | 不发送 |
| Tesla AP 未激活 | controller 87-92 | reset，不发送，以免中止 OEM AP/ACC session |
| 目标稳定至少 0.5 s | controller 109-119, 143-147 | 等待 |
| 无手动设速 override | controller 121-141 | 暂停；相反滚轮手势可恢复 |
| 上一 tick 已反馈或超时状态已处理 | controller 149-163 | 等待或阻断重复重试 |
| OEM idle 模板新鲜 | controller 171-174 | 不发送 |
| Panda `controls_allowed` | safety 432-435 | auto mode 拒绝 TX |

注意：来源 resolver 只要求 `speedLimitValid` 或 `speedLimitLastValid`，控制器没有检查 Speed Limit Assist 当前是否 enabled/active、也没有用户确认 gate。`lastValid` 可继续保留最近限速，而 card 只检查 plan 消息本身 0.2 s 内新鲜。迁移时必须明确是否保留这个产品语义。

## 7. 参数系统

### 7.1 功能开关

- `TeslaAutoSpeedLimit`：persistent+backup BOOL，默认关闭。
- 只在启动初始化阶段进入 CP_SP/safety flag，因此修改后需要重启。

### 7.2 目标生成参数

来源 `SpeedLimitResolver` 使用：

- `SpeedLimitPolicy`
- `IsMetric`
- `SpeedLimitOffsetType`
- `SpeedLimitValueOffset`
- `SpeedLimitOffsetMaxSpeed`

限速来源为 `carStateSP.speedLimit` 与 `liveMapDataSP`，policy 可以只选 car、只选 map、优先级或 combined（combined 取较低的正值）。最终目标为限速加固定或百分比 offset，并受 offset max speed 约束。

### 7.3 目标 Params 不兼容点

目标没有 source typed Params、CP_SP 或上述 `LongitudinalPlanSP` resolver schema。目标已经有另一套：

- `AutoCruiseControl`
- `AutoSpeedUptoRoadSpeedLimit`
- `AutoRoadSpeedAdjust`
- `AutoRoadSpeedLimitOffset`
- `AutoNaviSpeedSafetyFactor`
- `SpeedFromPCM`

这些参数的语义不能直接映射到 `TeslaAutoSpeedLimit`。尤其 `SpeedFromPCM` 的目标默认值实际是 `2`（`system/manager/manager.py:175`），而 `VCruiseCarrot` 只有值为 `1` 时才采用 PCM 设定速度（`selfdrive/car/cruise.py:331-344`）。所以默认配置下，即使未来滚轮改变 Tesla PCM set speed，目标内部 `vCruise` 也不会自动跟随，可能形成两个设定速度 owner。

## 8. UI 开关

### 来源原生 UI

`openpilot/selfdrive/ui/sunnypilot/layouts/settings/vehicle/brands/tesla.py:281-288`：

- 名称 `Automatic Tesla Set Speed`。
- 参数 `TeslaAutoSpeedLimit`。
- 描述明确是每次一个 wheel tick，追踪 resolved Speed Limit + offset。
- 只允许 offroad 修改，并提示重启。
- 只在 vehicle bus 可用时显示，并要求 OP longitudinal（346-363 行）。

### 来源 Web/debug UI 不一致

`openpilot/selfdrive/debug/device_settings.py:119` 将同一参数标为 `offroad_only=False`。但 runtime feature/safety flag 只在启动时初始化，所以行驶中修改既不会即时完成配置，也造成 UI 预期错误。

### 目标 UI

目标是 C++ Qt：`selfdrive/ui/qt/offroad/settings.cc` 已有 Carrot 自动巡航/自动速度/MADS 设置，但没有 `TeslaAutoSpeedLimit`。若后续实现，应新增独立、默认关闭、offroad-only、restart-required 的 Tesla 设置，而不是复用 `AutoSpeedUptoRoadSpeedLimit` 造成语义混淆。

## 9. 是否修改 longcontrol？

**结论：不应修改。**

- 来源 `TeslaSpeedLimitController` 挂在 Tesla CarController，不在 `selfdrive/controls/lib/longcontrol.py`。
- planner/resolver 只提供目标；控制器不写 MPC accel trajectory。
- `longcontrol` 仍根据 planner 的 `a_target` 和车辆状态执行普通 PID/stop 状态机。
- 目标 `longcontrol.py:90-228` 已有 Carrot/radar 停车平滑定制；为滚轮设速修改它既无必要，也会扩大 MADS、Tesla longitudinal 和 ARS408 回归面。

## 10. 目标已有自动速度与来源功能的差异

| 维度 | 来源 `TeslaAutoSpeedLimit` | 目标 `VCruiseCarrot._auto_speed_up()` |
|---|---|---|
| 控制对象 | Tesla 物理/PCM 设定速度 | openpilot 内部 `CarState.vCruise` |
| 动作方式 | `0x3C2` bus 1，右滚轮 ±1 | Python 内部数值更新，不发 `0x3C2` |
| 目标来源 | SP resolver 的道路限速 + offset | Carrot 道路限速、导航、参数及 lead context |
| lead 依赖 | 无 | `_auto_speed_up()` 使用 `v_lead_kph`、`d_rel` |
| 反馈 | 等 Tesla set speed 改变 | 直接更新内部 vCruise |
| 手动 override | 专门计数、暂停和恢复手势 | 使用目标现有 brake/gas/button/pause 逻辑 |
| safety | Panda 对 OEM 模板/字段/rate/controls 校验 | 最终 accel 走现有 Tesla longitudinal safety |

目标调用证据：

- `selfdrive/car/card.py:171,213-234` 用 `VCruiseCarrot` 产生 `CS.vCruise`。
- `selfdrive/car/cruise.py:243-310` 读 Params、Carrot road target 和 radar lead。
- `selfdrive/car/cruise.py:622-646` 根据近 lead、道路目标变化做上调/下调。
- `selfdrive/car/cruise.py:750-763` brake 暂停、gas 恢复后调用 `_auto_speed_up()`。
- `selfdrive/controls/lib/longitudinal_planner.py:216-281` 将该 vCruise 和 `radarState` 交给 MPC。

所以“目标没有自动加减速”也是一个不完整前提。真正待迁移的是**Tesla PCM set-speed 同步能力**，不是通用自动速度规划。

## 11. 目标数据源不能直接映射

来源有明确的 `LongitudinalPlanSP.speedLimit.resolver.speedLimitFinalLast`。目标没有 `longitudinalPlanSP`、`CarStateSP` 或 `SpeedLimitResolver`。

目标可见的候选值包括：

- `carrotMan.nRoadLimitSpeed`
- `carrotMan.desiredSpeed`
- `longitudinalPlan.cruiseTarget`
- `CarState.speedLimit`

其中 `desiredSpeed`/`cruiseTarget` 是复合速度，会受弯道、摄像头、减速带、导航转向、停车和其他 Carrot 逻辑影响。若直接映射到物理滚轮，Tesla set speed 可能频繁下降再回升，且与现有 `_auto_speed_up()` 形成双控制器竞争。

**建议：** 若产品需求仍是“道路限速同步”，应建立独立 target-provider，至少携带：

- 目标值及单位。
- 来源枚举（车端、地图、导航等）。
- valid、timestamp、age/TTL。
- offset 后值与用户 policy。
- 稳定时间和是否允许物理 set-speed 同步。

不能在没有产品定义的情况下用一个看似相近的现有字段替代。

## 12. 对 Tesla longitudinal 的影响

- 来源要求初始化时 `CP.openpilotLongitudinalControl=True`。
- 运行 gate 是 `CC.enabled` 和 Tesla cruise enabled；它独立于直接 `0x2B9` accel 发送。
- 在来源 dynamic handoff 到 stock-long 时，测试允许控制器继续工作；因此同一个物理 set speed 可能同时影响 OEM ACC 和 OP-long 的 vCruise 反馈。
- 目标必须决定谁是唯一速度 owner：Carrot 内部 vCruise、Tesla PCM，或一种明确的同步关系。
- 不应暗中把 `SpeedFromPCM` 改为 1；这会改变全局 cruise 行为，属于独立产品决策。
- 必须保留目标当前 `carcontroller.py:343-355` 的 `0x2B9` direct longitudinal/cancel 行为。

## 13. 对 MADS 的影响

目标 `controlsd.py:141-171` 中：

- `CC.enabled` 来自 selfdrive enabled。
- MADS 可独立保持横向 `CC.latActive`。
- `CC.longActive` 还要求 OP longitudinal 和没有 longitudinal override。

因此：

- MADS-only 不能因为 `latActive` 或 `madsState.active` 而触发自动滚轮。
- 至少应保留 `CC.enabled` gate，并明确是否还要求 `CC.longActive`；两者在 stock ACC/dynamic handoff 下语义不同，需要产品决定。
- brake、cancel、AP active 和失效状态必须立即禁止新 tick。
- 不得绕过 `invalidLkasSetting`、MADS fail-safe 或 Panda 现有权限分离。

## 14. 对 ARS408 与 bus 1 共享的影响

### 14.1 用户给定前提

bus 1 默认通过安全网关接入车辆侧，并可双向收发 `0x3C2`/`0x3E9`。本迁移直接采用该前提，不再展开网关规则或物理通道设计。

### 14.2 当前 checkout 的软件事实

`opendbc_repo/opendbc/car/tesla/ars408_can.py:4-14` 当前仍声明：

- bus 1 直连 ARS408、专用且不转发。
- ARS408 motion input 已启用。
- `0x300` speed 与 `0x301` yaw-rate 走 bus 1。

目标 Tesla CarState 只解析 bus 0/2；当前没有 `0x3C2` template observer/controller，Panda safety 也没有 `0x3C2` 规则。因此迁移要补的是：

1. card/CarState 接收 bus 1 OEM idle `0x3C2`。
2. Tesla controller 生成 bus 1 `0x3C2` ±1 tick。
3. Panda safety 对 fresh template、字段、频率和 `controls_allowed` 做校验。
4. 保持 ARS408 `0x200/0x202/0x300/0x301`、14 Hz object cycle 和 20 Hz motion 行为不回归。

## 15. 目标 Panda safety 缺口

目标 `opendbc_repo/opendbc/safety/safety/safety_tesla.h`：

- 只有现有 Tesla `0x488/0x2B9/0x27D` 和 ARS408 `0x200/0x202/0x300/0x301` TX 项。
- 无 `0x3C2` RX 模板或 TX 细粒度规则。
- 使用旧目录/API，不存在来源 `current_safety_param_sp`。
- 目标 pandad 只传标准 `CarParams.safetyParam`，不能直接使用来源 CP_SP flag。

后续必须把来源的**安全语义**手工重写到目标旧 API：

- 独立 feature bit，默认关闭。
- 正确 bus、DLC、mux、tick ±1。
- 除 tick 外所有字段与 fresh OEM 模板一致。
- 模板年龄、TX rate、`controls_allowed`、AP/模式 gate。
- 状态在 safety init/disengage/超时场景正确复位。
- 保留所有现有 MADS、Tesla longitudinal 和 ARS408 safety 测试。

只把 `0x3C2` 加入 allowlist 不符合来源安全边界。

## 16. 不能直接迁移的部分

1. 来源 `LongitudinalPlanSP` resolver：目标没有对应 schema，且 Carrot composite target 不等价。
2. 来源 `CarParamsSP/safetyParamSP`：目标 transport 和 Panda API 不支持。
3. 来源 `carstate_ext.py`：目标 Tesla state/API/字段不同。
4. 来源整个 Tesla CarController：会覆盖目标 ARS408、协作转向、MADS 和 longitudinal。
5. 来源整个 `modes/tesla.h`：目标 safety 布局/API和已有规则不同。
6. 来源 Python UI：目标设置是 C++ Qt。
7. 来源的 bus 1 数值可以保留，但能力开关、parser 和 safety flag 必须按目标架构重写。

## 17. 风险与待决策

| 风险/缺口 | 影响 | 下一阶段必须决定或证明 |
|---|---|---|
| 两套自动速度 owner | 内部 vCruise 与 Tesla set speed 竞争/分叉 | 单一 owner 与 `SpeedFromPCM` 策略 |
| 错用 composite `desiredSpeed` | 物理 set speed 追逐弯道/减速带/导航瞬态 | 独立 road-limit provider |
| 单位和 rounding | KPH/MPH 或 m/s 接错，目标偏差 | schema 单位、转换和显示反馈测试 |
| resolver last-valid/SLA 状态 | SLA 关闭时仍可能同步历史限速 | 明确 enable/active/confirm 语义 |
| AP gate 缺失 | synthetic tick 可能中止 OEM AP/ACC | 可靠 AP 状态与 fail-closed |
| manual override/txEcho | 误把自己 TX 当驾驶员动作或反之 | RX/txEcho/rejected 分类抓包 |
| bus 1 新增车辆帧 | ARS radar cycle/lead continuity 可能回归 | 集成测试中检查 14 Hz cycle、20 Hz motion 和 radarState 连续性 |
| 只过软件测试 | 无法证明实际车辆动作 | 台架、静止实车、封闭道路分层验证 |

## 18. 分析结论

来源功能可以迁移的只有**行为与安全不变量**：resolved road limit、逐 tick、稳定/反馈/手动覆盖、fresh OEM template 和 Panda 双层约束。具体代码、schema、bus 能力和 UI 都必须按目标重写。

按用户给定前提，bus 1 的 `0x3C2` 双向可达性成立。下一阶段应先确定唯一速度 owner和目标 provider，再按目标架构实现 Panda safety、纯 controller、card/CarController 集成，最后接 UI。`longcontrol` 不需要修改。

本阶段未修改任何功能代码。
