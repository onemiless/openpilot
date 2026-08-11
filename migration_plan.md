# `dev-new` → `cpv9-mads-ars408-motion-track` 第一阶段迁移计划

## 1. 本阶段边界

本文件只记录架构差异、目标接缝、不可直接迁移项、风险和后续实施顺序。本阶段没有修改功能代码、Panda safety、配置、子仓指针或分支。

用户已明确给定：目标 bus 1 默认通过安全网关接入车辆侧，可双向收发 Tesla 拨轮 `0x3C2` 和转向 `0x3E9`。迁移计划直接采用该前提，不把物理路由或网关设计列为阻断项。

## 2. 仓库与分支核对

### 2.1 目标仓库

执行位置：`/Users/mile/Desktop/cp/cpv9-mads-worktree`

`git branch`：

```text
  cpv9
+ cpv9-device-20260809
* cpv9-mads-ars408-motion-track-20260810
  cpv9-mads-coop-20260809
```

`git log --oneline -10`：

```text
0c39cc20b fix(tesla): retain distant static radar candidates
721ed66f7 fix(tesla): apply radar motion toggle before each send
96a0c5d3d feat(tesla): permit live ARS408 reconfiguration
ecb88bd55 feat(tesla): allow manual moving radar filter tests
11d7d4d5b fix(tesla): stage ARS408 object limit updates
ac7b1a358 fix(tesla): retain distant ARS408 tracks
594d48c0a fix(tesla): harden ARS408 configuration workflow
b3b3b3bc5 fix(tesla): refine ARS408 diagnostics and logging
94544ff74 feat(tesla): add runtime ARS408 configuration
476b44751 fix(tesla): isolate MADS from radar faults
```

- 完整 SHA：`0c39cc20bec3d8e1a8a5db8b7850df31a869168c`。
- 状态：相对 `origin/cpv9-mads-ars408-motion-track-20260810` ahead 9；分析开始时工作树干净。
- 前提纠正：用户目标名称没有日期后缀，但本地实际 checkout 是 `cpv9-mads-ars408-motion-track-20260810`。本报告以实际 checkout 为准。

### 2.2 来源仓库

执行位置：`/Users/mile/Desktop/mo-op`

分析开始时 `git branch` 的相关部分：

```text
+ codex/fix-always-on-power
  codex/offline-auto-wake
  codex/offline-auto-wake-dev0625
+ codex/sync-sp260728xl-tici
  dev
* dev-new
  dev0428
  dev0617
  dev0624
  dev0625
  dev260426XL-tici
  dev260428XL-tici
+ new-dev-yolo
```

分析开始时 `git log --oneline -10`：

```text
d2842c7525 Update Panda offline wake diagnostics
7f8f628345 Update Panda offline wake diagnostics
980ed62e33 Resync Panda wake session before prepare
993a330f59 Make offline wake shutdown fail safe
101eb170eb Gate shutdown on a proven Panda wake monitor
b9074b0ed7 Update Panda offline wake teardown
3571265f54 Update Panda raw bus 1 offline wake
384f5e5d26 Update Panda physical bus 1 offline wake
169f1178d3 Update Panda offline wake monitor
500d687a27 fix(tres): finalize offline wake diagnostics
```

快照说明：

- `sp/dev-new` 当前指向 `d2842c7525ab15955b72ac5368cb163b6fe4e5c6`；它是本报告的来源基线。
- 分析期间另一个本地任务在 2026-08-11 13:19:27 +0800 将本地 `dev-new` 推进到 `1a623470107b758086ff57d7615ca6ae6ec16cac`，当前相对 `sp/dev-new` ahead 1。
- 新提交 `1a62347010 Update Panda offline wake firmware` 只更新 `panda` gitlink；`git diff sp/dev-new..dev-new -- openpilot/selfdrive openpilot/common opendbc_repo` 无差异，因此不改变本报告两项功能的结论。
- 当前来源 opendbc gitlink/HEAD：`85a463402b4db53aeca79dcca1bc754286adfbba`，分支 `dev-new`，clean。
- 当前来源 Panda gitlink/HEAD：`470a22ed23691cdbc8e48e3ab671b27fa3933139`，分支 `dev-new`，clean。
- 来源主仓已有未跟踪内容 `docs/TESLA_VISION_OBJECT_DETECTION_PLAN.md`、`logs/`、`tools/tesla_party_can_ble/`，本分析未触碰。

## 3. 搜索范围

已在两仓对以下关键词做递归代码搜索，并进一步按符号/调用点收窄：

- 转向：`turn`、`blink`、`signal`、`indicator`。
- 自动速度：`speed`、`accel`、`decel`、`v_cruise`、`target_speed`、`planner`、`longcontrol`。
- 重点目录：两仓的 `selfdrive/ui`、`selfdrive/controls`、`selfdrive/car`、Tesla car、Params、Panda safety、manager/web 进程。

宽关键词会命中大量通用车辆、翻译、测试和第三方代码；文件矩阵只保留经调用链确认的功能相关结果。

## 4. 两个功能的准确边界

### 4.1 网页转向灯测试

不是 UI-only，也不是 WebSocket：

```text
浏览器 POST /api/turn/{left|right}
  ↓
typed JSON Params request
  ↓
card 100 Hz TeslaTurnSignalRealtimeController
  ↓
克隆 OEM idle 0x3E9 / bus 1
  ↓
sendcan → Panda safety → Tesla vehicle CAN
  ↓
0x311 / 0x3F5 反馈 → Params status/result → 网页轮询
```

### 4.2 “自动加减速”

准确功能是 Tesla 自动设定速度，不是直接 accel：

```text
SP SpeedLimitResolver（道路限速 + offset）
  ↓ longitudinalPlanSP.speedLimit.resolver
card / Tesla state
  ↓
TeslaSpeedLimitController
  ↓
克隆 OEM idle 0x3C2 / bus 1，每次右滚轮 ±1
  ↓
Panda safety → Tesla PCM set speed
  ↓
OEM ACC 或 OP longitudinal 产生实际加/减速
```

目标已经有 `VCruiseCarrot._auto_speed_up()`，但它改内部 `vCruise`，不是 `0x3C2` 物理设速同步。迁移时不能把两者当作同一实现。

## 5. 总体架构差异

| 维度 | 来源 `mo-op/sp dev-new` | 目标 `cpv9-mads-worktree` | 迁移影响 |
|---|---|---|---|
| 目录根 | 实码位于 `openpilot/selfdrive`、`openpilot/common`、`openpilot/cereal` | 实码位于根目录 `selfdrive`、`common`、`cereal`；部分 `openpilot/*` 是 symlink | import 和路径必须按目标重写 |
| opendbc/Panda | `opendbc_repo`、`panda` 是 mode 160000 submodule | 两者 vendored 在主仓 | 不能照搬 gitlink/子仓提交方式 |
| Tesla 扩展位置 | `opendbc/sunnypilot/car/tesla/*` + upstream Tesla 文件 | 定制直接位于 `opendbc_repo/opendbc/car/tesla/*` | 新组件必须放入目标现有 Tesla 包 |
| card API | `CI.apply(CC, CC_SP, now)`，有 CP_SP/CS_SP | `CI.apply(CC, now)`，无 CP_SP/CS_SP | 不能复制 source card 集成代码 |
| Params | typed schema，自动 JSON/dict | 旧 bytes API，default 在 manager 另维护 | 请求协议、序列化、生命周期需重写 |
| Cap'n Proto | 有 `CarParamsSP`、`CarStateSP`、`selfdriveStateSP`、`LongitudinalPlanSP` | 无上述 SP schema；有 Carrot/MADS schema | 不能复制 source message 字段 |
| Safety flag transport | `CarParamsSP.safetyParamSP` 经 pandad/Panda 扩展传输 | 标准 `CarParams.safetyParam` + alternativeExperience | 必须分配目标原生 bit |
| Tesla safety 文件 | `opendbc/safety/modes/tesla.h` 新 API | `opendbc/safety/safety/safety_tesla.h` 旧 API | 只移植安全语义，不能替换文件 |
| UI | Python sunnypilot layout | C++ Qt settings | UI 控件需目标原生实现 |
| Web | 独立 `ThreadingHTTPServer`，8088 | Carrot `HTTPServer` 已占 8088 | 不能新增来源进程；需接入现有 server |
| bus 1 | 来源 Tesla vehicle bus | 用户确认：安全网关下车辆 CAN + ARS408；当前注释仍写 ARS 专用 | bus 号可沿用，软件 parser/safety/注释需统一 |
| 自动速度目标 | `LongitudinalPlanSP.SpeedLimitResolver` | Carrot composite speed + 内部 vCruise | 必须定义独立 road-limit target provider |
| longitudinal | source Tesla 有多套 dynamic stock/AP 扩展 | 目标有现有 `0x2B9` OP long + Carrot longcontrol | 不能覆盖目标 CarController/longcontrol |
| MADS | source SP state/schema/safety | 目标独立 MADS state machine、heartbeat、Panda lateral permission | 所有 gate 按目标 MADS 语义重写 |
| Radar | 来源功能不含目标 ARS408 集成 | 目标已配置/跟踪/20 Hz motion | 所有改动必须做 ARS 回归 |

## 6. 迁移文件矩阵

### 6.1 网页转向灯

| 来源文件/功能 | 目标对应接缝 | 需要重构 | 不能直接迁移 |
|---|---|---|---|
| `openpilot/selfdrive/debug/tesla_turn_signal_web.py` | `selfdrive/carrot/web_interface.py`，建议拆独立 turn page/handler 模块再注册 | 专用 REST、单 session、TTL、状态码、默认关闭 | 整个混合网页；独立 8088 process |
| `openpilot/selfdrive/debug/tesla_turn_signal_test.py` | 目标 main-repo 的 request adapter | 显式 JSON encode/decode 或正式 cereal IPC | `Params.put(dict)` |
| 四个 `TeslaTurnSignalTest*` JSON Params | `common/params_keys.h` + `system/manager/manager.py` | 定义 clear-on-manager/offroad 生命周期和默认值 | source typed ParamKeyAttributes |
| `selfdrive/car/tesla_turn_signal_controller.py` | 目标 `selfdrive/car/` 新的小型 controller + `card.py` raw CAN/service 接缝 | 保留 OEM-template、session、反馈、取消安全不变量 | source CP_SP/custom message/import |
| source `card.py` observer/cancel | target `selfdrive/car/card.py` | 按目标 callback、`CI.apply(CC, now)`、MADS context 重写 | 替换整个 card |
| source `HAS_VEHICLE_BUS` / CP_SP flags | target Tesla `interface.py`/`values.py` | 目标原生 feature/safety bit；bus 1 能力按给定架构配置 | `CarParamsSP`/`safetyParamSP` |
| source `modes/tesla.h` 0x3E9 rules | target `safety/safety_tesla.h` | 旧 API 下实现 fresh template、字段、counter、checksum、session | 整文件替换或只加 whitelist |
| source Python setting | `selfdrive/ui/qt/offroad/settings.cc` | 默认 off、offroad-only、restart-required | Python sunnypilot layout |
| source web/safety tests | 目标现有 Tesla car/safety tests | 扩展目标测试并保留 ARS/MADS cases | 覆盖目标测试文件 |

### 6.2 Tesla 自动设定速度

| 来源文件/功能 | 目标对应接缝 | 需要重构 | 不能直接迁移 |
|---|---|---|---|
| `speed_limit_resolver.py` + `LongitudinalPlanSP` | 目标新 road-limit target provider | 明确来源、单位、valid、timestamp、offset、稳定性 | 直接用 `carrotMan.desiredSpeed`/`cruiseTarget` |
| source `card.get_tesla_speed_limit_context()` | target `card.py`/新 provider adapter | 使用目标消息、freshness 和 enable 语义 | source `longitudinalPlanSP` schema |
| source `carstate_ext.py` 0x3C2 state | target Tesla `carstate.py` 或小型 extension + card raw observer | 保存 idle template、单位、manual/resume counter、target | 整个 source extension，包含无关 AP/dynamic ACC |
| `speed_limit_controller.py` | `opendbc_repo/opendbc/car/tesla/` 新 target-native controller | 手工重写逐 tick、稳定、反馈、override、AP gate | 直接复制 source module/import/CP_SP |
| source Tesla CarController 集成 | target `carcontroller.py` | 增量 append `0x3C2`，保留 ARS/coop/MADS/`0x2B9` | 替换整个 CarController |
| source auto-speed flags | target `values.py`/`interface.py` 的标准 safetyParam | 独立 bit，默认关闭 | source CP_SP flag transport |
| source `modes/tesla.h` 0x3C2 rules | target `safety_tesla.h` | OEM template、只改 tick、rate、controls_allowed | 简单 allowlist 或整 safety 文件 |
| source Python UI toggle | target C++ Qt Tesla 设置 | offroad-only、restart；与 Carrot 自动速度区分命名 | source Python widget |
| controller/safety tests | target Tesla car/safety tests | 加/减、KPH/MPH、feedback、manual、AP、MADS、ARS 回归 | 用 source tests 代替目标集成测试 |

## 7. 需要重构的核心设计

### 7.1 共用 bus 1 接收层

按用户给定前提，两个功能都使用 bus 1：

- 接收 OEM idle `0x3E9` 和 `0x3C2`。
- 区分真实 RX、Panda txEcho 和 rejected。
- 只允许控制器消费新鲜真实 OEM 模板。
- 与现有 ARS408 parser/`0x200/0x202/0x300/0x301` 并存。

目标当前 `card.py` 没有 source 的 raw-template observer，需要建立一个小而明确的接收接缝，不能把 source card 全部搬入。

### 7.2 目标原生安全能力

建议在目标 `TeslaSafetyFlags`/标准 `CarParams.safetyParam` 中分配彼此独立的两个能力位：

- turn-signal test。
- automatic Tesla set speed。

Panda safety 应先于 UI 接入完成，且保持默认拒绝。来源的安全不变量需要语义移植：

- 正确 bus/DLC/ID。
- fresh OEM idle template。
- 只修改允许字段。
- checksum/counter（`0x3E9`）。
- tick ±1、rate、`controls_allowed`（`0x3C2`）。
- session、超时、取消和状态复位。

### 7.3 自动速度唯一 owner

目标已有内部 `VCruiseCarrot` 自动速度，而来源新增 Tesla PCM 设速。实施前必须明确：

- 来源功能只跟踪“道路限速 + offset”，还是跟踪 Carrot composite speed。
- `SpeedFromPCM` 是否继续保持默认 `2`；目标只有值为 `1` 时才采用 PCM set speed。
- 是否与 `AutoSpeedUptoRoadSpeedLimit`/`AutoRoadSpeedAdjust` 互斥。
- `CC.enabled`、`CC.longActive`、stock ACC/dynamic handoff 的准确 gate。

推荐维持来源产品语义：只使用独立 road-limit provider，不让物理滚轮追逐弯道/减速带/停车等短时目标。

### 7.4 Web/Params 边界

- 8088 已由 Carrot 占用，转向页/API 应注册到目标现有服务，不能新增来源 process。
- 动作 API 不能复用泛化 `/save_params`。
- 目标 Params 为 bytes API；若继续使用 Params 做 request/result，必须显式 JSON、长度/字段校验、TTL、单 session 和清理策略。
- 来源 `TeslaTurnSignalValidation` 默认 `1` 不应沿用；目标默认必须为 off。
- `TeslaAutoSpeedLimit` 也应默认 off，且两个功能开关统一为 offroad-only + restart。

## 8. 明确不能直接迁移的内容

1. 不能复制整个 `tesla_turn_signal_web.py`：包含设置、热点、终端、驾驶可视化等无关功能，并与目标 8088 冲突。
2. 不能复制 source `card.py`：消息/schema、CI API、CP_SP 和 target Carrot/MADS 均不同。
3. 不能复制 source Tesla `carcontroller.py` 或 `carstate_ext.py`：会带入大量 dynamic ACC/AP 逻辑并覆盖 ARS408/协作转向/现有 longitudinal。
4. 不能复制 `opendbc/safety/modes/tesla.h`：目标使用旧 API，且已有 MADS、driver override、ARS408 规则。
5. 不能只在 safety whitelist 加 `0x3E9`/`0x3C2`：会丢失 OEM-template、字段、rate、session 和 controls gate。
6. 不能复制 source `LongitudinalPlanSP` 全套 schema/planner：目标 Carrot 架构不同，迁移面远大于需求。
7. 不能把 `carrotMan.desiredSpeed` 当 source resolver 的等价字段。
8. 不能把 `ExtBlinkerCtrlTest`/`StockBlinkerCtrl` 当成已存在的 Tesla `0x3E9` 实现。
9. 不能修改 target `longcontrol.py` 来实现滚轮设速；该功能属于 Tesla car/controller/safety 辅助路径。
10. 不建议 cherry-pick 来源大提交。历史线索 `cd249b4d49`、`c6f5dbaaaf`、`793327a5ad`、`0374e4321c`、`2263b654f8` 及 opendbc `e0b51361`、`d869f9da` 混有大量无关 web/Tesla/AP 变更；应以当前冻结行为为规范手工重构。

## 9. 风险点

| 优先级 | 风险 | 后果 | 控制方式 |
|---|---|---|---|
| R0 | 整文件/大提交迁移 | 覆盖目标 MADS、ARS408、协作转向、Tesla longitudinal | 只按目标接缝手工实现小组件 |
| R0 | 只改 Python、不改 Panda safety | 正常帧被拒；或为求通过而错误放宽车辆动作 | safety 语义和测试先行，默认拒绝 |
| R0 | 两套自动速度 owner | 内部 vCruise 与 Tesla PCM set speed 竞争/分叉 | 定义 road-limit provider、互斥和 `SpeedFromPCM` 策略 |
| R1 | 8088 动作接口无认证 | 局域网请求可触发实际车辆 CAN | 专用 API、默认关闭、session/TTL、访问控制 |
| R1 | Params 类型/生命周期照搬 | `put(dict)` 失败、旧请求跨启动残留 | 显式 JSON/IPC、clear policy、严格 schema |
| R1 | MADS gate 错用 | MADS-only 误发滚轮；转向失效时未取消 | 分别使用目标 `CC.enabled/longActive/latActive/madsState` 语义 |
| R1 | 来源 turn enable 默认 1 | 车辆动作功能默认暴露 | 目标默认 off、offroad-only、restart |
| R1 | bus 1 软件假设未统一 | parser/safety 仍按“ARS 专用”遗漏车辆帧 | 按用户确认拓扑统一注释、能力和测试 |
| R2 | ARS408 回归 | 14 Hz cycle、20 Hz motion、lead tracking 退化 | 保留发送集合并增加并发流量/连续性测试 |
| R2 | KPH/MPH/m/s 混用 | set speed 错误或方向错误 | 单位写入 schema，覆盖边界/rounding 测试 |
| R2 | AP/manual/feedback 分类错误 | OEM AP session 中止、反复 tick、忽略驾驶员 | AP fail-closed、txEcho/rejected、manual override 测试 |
| R2 | source/target 分支持续前进 | 实施基线与报告不一致 | 实施开始前重查 main/opendbc/Panda SHA |

## 10. 建议实施顺序

### P0：重新冻结基线与接口契约

- 重跑两仓 branch/log/status。
- 固定 source main/opendbc/Panda 和 target SHA。
- 确认 bus 1 作为 `0x3E9/0x3C2` 双向路径的既定配置。
- 决定自动速度唯一 owner、road-limit provider、`SpeedFromPCM`/Carrot 互斥语义。
- 定义两个 feature flag、Params/IPC schema、UI 默认值。

### P1：Panda safety 与测试

- 在目标旧 Tesla safety API 中增量加入 `0x3E9`、`0x3C2` 规则。
- 覆盖错 bus/DLC、无 flag、模板陈旧/篡改、counter/checksum、rate、session、controls/MADS/AP gate。
- 保留现有 MADS、driver override、Tesla long、ARS408 测试。

### P2：纯 frame/controller 组件

- 目标原生 turn controller。
- 目标原生 speed-wheel controller。
- 用目标结构重建 feedback、manual override、取消和超时测试。

### P3：card、CarState 与 CarController 集成

- raw bus 1 template observer。
- turn Params/IPC service 和 cancel fail-safe。
- road-limit target provider。
- 增量挂到现有 Tesla CarController，不覆盖 ARS408/coop/`0x2B9`。

### P4：UI 与 Web

- C++ Qt 中增加两个默认关闭、offroad-only、restart-required 设置。
- 在现有 Carrot 8088 server 注册独立 turn page/API。
- 增加认证/访问控制、session、TTL、cancel 和端口生命周期测试。

### P5：验证分层

1. 静态检查、Params/schema 测试。
2. controller 单测。
3. Panda safety 单测与现有 Tesla/MADS/ARS 回归。
4. web → request → card → sendcan 合成集成测试。
5. CAN replay，确认 RX/txEcho/rejected 分类。
6. Panda 台架抓包，确认实际放行/拒绝和 ARS408 连续性。
7. 静止实车：转向点亮/取消/反馈；`0x3C2` 单 tick 与 KPH/MPH 反馈。
8. 封闭道路：自动上调/下调、brake/cancel、manual override、AP、MADS、ARS lead continuity。

前四层只能称为软件/安全策略验证，不能称为完整车辆验证。

## 11. 第一阶段结论

- 两项功能均能在用户给定的 bus 1 双向 CAN 前提下规划迁移。
- 转向功能需要重写 Web/Params/card/controller/Panda safety 全链，不能视为 UI 测试。
- 自动速度功能不改 `longcontrol`；它是 Tesla PCM set-speed 同步。目标已经有另一套内部自动速度，必须先解决 owner/目标语义。
- 目标当前关键缺口是 `0x3E9/0x3C2` 的 target-native parser/controller/safety，而非物理网关设计。
- 实施时只能迁移行为和安全不变量，禁止直接复制代码或替换目标整文件。

本阶段到此停止，未实施功能代码。
