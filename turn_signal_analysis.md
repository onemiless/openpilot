# 网页转向灯测试功能分析

## 1. 范围与快照

本报告只做代码与架构分析，不包含功能代码、配置、Panda safety 或分支修改。

- 来源基线：`/Users/mile/Desktop/mo-op` 的远端跟踪分支 `sp/dev-new`，提交 `d2842c7525ab15955b72ac5368cb163b6fe4e5c6`。
- 来源本地 `dev-new` 在分析期间被外部任务推进到 `1a623470107b758086ff57d7615ca6ae6ec16cac`；两者之间只改变 `panda` gitlink，`openpilot/selfdrive`、`openpilot/common` 和 `opendbc_repo` 的本功能文件没有差异。
- 来源 opendbc gitlink：`85a463402b4db53aeca79dcca1bc754286adfbba`。
- 目标基线：`/Users/mile/Desktop/cp/cpv9-mads-worktree` 的实际分支 `cpv9-mads-ars408-motion-track-20260810`，提交 `0c39cc20bec3d8e1a8a5db8b7850df31a869168c`。
- 用户给定的目标前提：bus 1 默认通过安全网关接入车辆侧，可双向收发转向 `0x3E9` 和拨轮 `0x3C2`。本报告据此分析，不把物理路由作为阻断项。

文中标记：

- **事实**：由当前本地代码直接确认。
- **待验证**：代码表达了假设，但仍需要实车接线或 CAN 抓包证明。
- **建议**：下一阶段设计选择，不代表已经实现。

## 2. 结论先行

1. **事实：网页入口不是 WebSocket。** 来源使用独立的 `ThreadingHTTPServer`，监听 `0.0.0.0:8088`，在 `do_GET()` / `do_POST()` 中手写 REST 路由。
2. **事实：这不是仅 UI 的灯光演示。** 网页写入 Params 后，`card` 的 100 Hz 实时线程会克隆原车新鲜 `0x3E9 DAS_bodyControls`，通过 `sendcan` 和 Panda safety 向车辆 CAN 发帧。
3. **给定前提：目标继续使用 bus 1。** 安全网关默认可双向收发 `0x3E9`；不需要另行设计物理通道。
4. **事实：目标 Tesla/Panda 接口必须改造。** 目标没有 `0x3E9` OEM 模板接收链、功能 flag、细粒度 safety 状态机或对应 card session 服务。
5. **事实：当前代码注释落后于目标拓扑。** `ars408_can.py` 仍把 bus 1 描述为 ARS408 专用、非转发；迁移实现时需按用户确认的共享/网关拓扑统一注释、parser 和 safety 语义。

因此，这项工作只能规划为**目标架构上的语义重写**，不能文件复制、整提交 cherry-pick，或只加 `0x3E9` whitelist。

## 3. 文件列表

### 3.1 来源功能文件

| 文件 | 关键位置 | 作用 |
|---|---:|---|
| `openpilot/system/manager/process_config.py` | 137 | 将 `tesla_turn_signal_web` 注册为 device-only、`always_run`、崩溃重启进程 |
| `openpilot/selfdrive/debug/tesla_turn_signal_web.py` | 21-26, 37-76, 239-270, 282-436 | 网页、REST API、session 锁、200 ms 状态轮询、8088 HTTP 服务 |
| `openpilot/selfdrive/debug/tesla_turn_signal_test.py` | 17-46 | 校验方向/开关，创建 test id，通过四个 Params 键提交、查询、取消 |
| `openpilot/selfdrive/debug/device_settings.py` | 126 | Web 设置中的 `TeslaTurnSignalValidation` 开关，标记为 offroad-only |
| `openpilot/common/params_keys.h` | 235-239 | 四个瞬时 JSON 键及持久化 enable 键；来源 enable 默认值为 `1` |
| `openpilot/common/params_pyx.pyx` | 24-31, 49-67, 115-158 | typed Params；`dict/list` 与 JSON 自动互转 |
| `openpilot/selfdrive/car/tesla_turn_signal_controller.py` | 12-38, 52-90, 128-486 | OEM 模板克隆、session、车辆反馈、超时、取消、CAN 发送、状态回写 |
| `openpilot/selfdrive/car/card.py` | 167-183, 255-275, 396-410, 428-439 | 实时控制器实例、raw CAN 观察、变道上下文、sendcan、Params 服务 |
| `openpilot/sunnypilot/selfdrive/car/interfaces.py` | 109-137 | 启动时读取 Tesla 扩展参数 |
| `opendbc_repo/opendbc/sunnypilot/car/interfaces.py` | 153-159 | `HAS_VEHICLE_BUS`、用户开关到 CP_SP/safety flag 的初始化 |
| `opendbc_repo/opendbc/sunnypilot/car/tesla/values.py` | 10-26, 35-44 | Tesla feature flag 与 Panda safety SP flag |
| `opendbc_repo/opendbc/car/tesla/interface.py` | 53-65 | bus 1 指纹中存在 `0x3DF` 才声明 `HAS_VEHICLE_BUS` |
| `opendbc_repo/opendbc/car/tesla/values.py` | 98-101 | 来源 bus 映射：party=0、vehicle=1、autopilot_party=2 |
| `opendbc_repo/opendbc/safety/modes/tesla.h` | 247-266, 444-494, 560-617, 643-679 | OEM 模板缓存、字段/计数/checksum/session 校验、TX/RX 集合、flag 初始化 |
| `openpilot/selfdrive/car/tests/test_tesla_turn_signal_web.py` | 9-105 | 网页/API 单元测试 |
| `opendbc_repo/opendbc/safety/tests/test_tesla.py` | 190-272 | `0x3E9` flag、模板、超时、字段、方向、帧数和 controls-allowed 测试 |

### 3.2 目标对应位置与现状

| 目标文件 | 当前事实 | 迁移含义 |
|---|---|---|
| `system/manager/process_config.py:142` | `carrot_man` 已 `always_run` | 不能再照搬一个来源 web 进程 |
| `selfdrive/carrot/carrot_man.py:202-205` | 已启动 `WebInterface(..., port=8088)` | 与来源 8088 必然端口冲突 |
| `selfdrive/carrot/web_interface.py:38-50,79-151,273-280` | 现有手写 HTTP router，使用单线程 `HTTPServer` | 应设计窄化的目标原生 route/handler，而非复制来源混合大页面 |
| `common/params_keys.h:6-32` | 只有生命周期 flag，没有 typed JSON/default schema | 四个 JSON key 不能原样定义 |
| `common/params_pyx.pyx:68-115` | `get()` 返回 bytes；`put()` 只处理 str/bytes | 来源 `Params.put(dict)` 会类型失败 |
| `selfdrive/car/card.py:68-70,182-237,269-304` | 无 CP_SP、无 turn session/raw-template 服务 | 需要按目标 `CI.apply(CC, now)`/callback 结构重写接缝 |
| `selfdrive/controls/controlsd.py:146-179` | MADS 权限独立；模型变道时只设置 `CC.leftBlinker/rightBlinker` | Tesla CarController 当前不消费这两个字段生成 `0x3E9` |
| `opendbc_repo/opendbc/car/tesla/carstate.py:106-108,130-135` | 从 bus 0 `0x311` 读取灯态；parser 只有 bus 0/2 | 没有 vehicle-bus `0x3E9/0x3F5` 模板/反馈 parser |
| `opendbc_repo/opendbc/car/tesla/ars408_can.py:4-14` | 当前仍写 bus 1 为 ARS408 专用、非转发；motion input 已启用 | 与用户确认的后续共享/网关拓扑不一致，迁移时需统一软件语义 |
| `opendbc_repo/opendbc/car/tesla/carcontroller.py:295-355` | 已包含 ARS408、协作转向、MADS、Tesla longitudinal | 不能替换整个 CarController |
| `opendbc_repo/opendbc/safety/safety/safety_tesla.h:217-260,297-332` | 旧 safety API；白名单无 `0x3E9`，bus 1 规则属于 ARS408 | 必须增量重写细粒度校验，并保留现有 MADS/ARS/Tesla 规则 |
| `selfdrive/ui/qt/offroad/settings.cc:1112-1113` | 有 `StockBlinkerCtrl`、`ExtBlinkerCtrlTest` 设置项 | 名称相似，但不是来源 CAN 测试链 |

## 4. 来源调用流程

```text
网页：0.0.0.0:8088 的转向测试页签
  ↓
接口层：POST /api/turn/{left|right} → TurnSignalHandler.do_POST()
  ↓ start_validation_session()
TeslaTurnSignalTestRequest（typed JSON Params）
  ↓ card.params_thread() / service_params()
控制层：TeslaTurnSignalRealtimeController.submit_request()
  ↓ card 100 Hz 控制循环 + modelV2 lane-change 上下文
克隆刚收到的 OEM idle 0x3E9，只改 request/reason/counter/checksum
  ↓ CanData(address=0x3E9, bus=1)
sendcan
  ↓
Panda Tesla safety：fresh template + 字段一致性 + checksum + session/帧数限制
  ↓
车辆 CAN：Tesla DAS_bodyControls
  ↓
0x311 UI_warning（bus 0）及 0x3F5 front lighting（bus 1）反馈
  ↓
TeslaTurnSignalTestStatus / Result Params
  ↓ GET /api/status/{test_id}（网页每 200 ms 轮询）
网页显示进行中、成功、失败或取消
```

取消链还有一条独立 fail-safe：`card.state_update()` 可以直接用 CAN callback 发 cancel，而不依赖正常 `controls_update()`/`carControl` 继续存活（来源 `card.py:268-275`）。这是需要保留的安全意图，但必须按目标 card 架构重写。

## 5. 网页入口、API 与 router

### 5.1 网页功能入口在哪里？

**事实：**

- manager 入口：`openpilot/system/manager/process_config.py:137`。
- 服务入口：`openpilot/selfdrive/debug/tesla_turn_signal_web.py:434-436`。
- 页面入口：同文件 `render_page()`；转向页签/按钮位于约 68-75 行。
- 浏览器动作：`run(direction)` 在 239-250 行发起 POST；状态每 200 ms 轮询（252-265 行）。
- 它不是仅供手动运行的 debug script：manager 会在设备上常驻启动。

### 5.2 WebSocket/API/router 在哪里？

**事实：没有 WebSocket。**

- `POST /api/turn/left`
- `POST /api/turn/right`
- `GET /api/status/{test_id}`
- `POST /api/cancel/{test_id}`

路由全部在 `TurnSignalHandler.do_GET()` / `do_POST()` 中。来源没有 Flask、FastAPI 或独立 router 模块。

目标同样没有 WebSocket；其现有 route 在 `selfdrive/carrot/web_interface.py`。来源使用 `ThreadingHTTPServer`，目标使用单线程 `HTTPServer`，并发轮询/session 行为不能假定等价。

## 6. 是否只是 UI 测试、是否调用车辆 CAN？

### 6.1 不是 UI-only

网页自身只负责提交请求和展示状态，但完整功能会执行实际 CAN：

- 动作帧：`0x3E9 DAS_bodyControls`，来源 bus 1。
- 灯态反馈：`0x311 UI_warning`，来源 bus 0。
- 前灯物理状态反馈：`0x3F5`，来源 bus 1。
- 输出路径：`card` → `sendcan` → Panda safety → 车辆总线。

### 6.2 Python 控制器的约束

来源 `tesla_turn_signal_controller.py` 只允许：

- 请求 `left` 或 `right`；取消使用专门的 request/reason。
- 原车模板必须为 bus 1 的 8-byte `0x3E9`、checksum 正确、turn request idle。
- 模板年龄不超过 1.5 s，而且每次 TX 消耗一个新模板。
- brake、`CC.latActive` 失效、lane-change context 陈旧、方向不一致、finishing/off 都请求取消。
- 观察 Panda `txEcho` / `rejected`，并用车辆灯态反馈确认动作与取消。

实施决策补充（2026-08-11）：以上是来源快照事实。目标实现按用户后续确认调整关闭时机：`laneChangeFinishing` 继续保持，实际状态回到 `off`、确认本次变道完成后才发送取消。

### 6.3 Panda safety 的约束

来源 safety 不是简单 whitelist：

- 未修改字段必须与刚收到的 OEM 模板一致。
- counter 必须是 OEM counter + 1，checksum 必须正确。
- 模板必须新鲜；session 最多 12 s、同方向动作最多 64 帧。
- 必须同时具有 `HAS_VEHICLE_BUS` 和 `TURN_SIGNAL_VALIDATION` safety flag。
- 每次成功 TX 后立即使模板失效，下一帧必须等新的真实 OEM idle 帧。

来源 safety 测试还明确覆盖了 `controls_allowed=True` 时仍允许转向测试（`test_tesla.py:268-272`）。因此它可能在控制已激活时执行，不能用“测试”二字将其视为无车辆风险。

## 7. 目标中的相似项为何不是同一功能

### `ExtBlinkerCtrlTest`

精确搜索只找到 Params 默认、Carrot 配置、网页配置和 Qt 设置；没有运行时读取者，也没有 CAN 生成路径。它是配置/UI 残留，不是来源的 `TeslaTurnSignalValidation`。

### `StockBlinkerCtrl`

它会影响 Carrot/DesireHelper 的 lane-change/外接状态逻辑，但：

- 目标 `controlsd` 设置的 `CC.leftBlinker/rightBlinker` 只表达计划方向。
- 目标 Tesla CarController 没有读取这两个字段并生成 `0x3E9`。
- 全目标 Tesla 控制/safety 路径没有 `0x3E9` 发送实现。

### DBC 中存在 `DAS_bodyControls`

目标 `tesla_model3_vehicle.dbc` 中已有报文定义；按用户给定前提，bus 1 可达性成立。但 DBC 存在仍不等于目标 parser、controller 和 Panda safety 已接通，这三层依然需要实现。

## 8. Tesla 接口是否需要改造？

**需要，且范围超过 Tesla CarController。**

至少需要重新设计：

1. bus 能力：按给定前提使用 bus 1，接收 OEM idle `0x3E9` 并向同一车辆侧路径发送受控 `0x3E9`。
2. 能力检测：不能直接沿用来源“bus 1 出现 `0x3DF`”的 `HAS_VEHICLE_BUS` 判定。
3. raw CAN / parser：为模板、反馈、txEcho/rejected 提供目标兼容的数据入口。
4. Params 或正式 IPC：目标需显式 JSON 编解码、TTL、唯一 session、幂等取消和清理策略。
5. card 实时状态机：接入目标 MADS/lane-change 权限，并保留 controlsd 失效时的取消路径。
6. safety flag：来源使用 `CarParamsSP.safetyParamSP`；目标没有这套传输，需要在目标原生 `CarParams.safetyParam`/旧 API 中分配独立能力位。
7. Panda safety：按目标旧布局增量实现模板、字段、checksum、计数、超时和 session 校验，不能只开放 ID。
8. UI：目标是 C++ Qt + Carrot web，不能复制来源 Python UI 布局。

## 9. 用户确认的 bus 1 前提与当前软件差距

**用户给定前提：** bus 1 默认通过安全网关接入车辆侧，并可双向收发 `0x3E9`/`0x3C2`。因此物理可达性不列为迁移阻断。

**当前代码事实：** `opendbc_repo/opendbc/car/tesla/ars408_can.py:4-14` 仍写明：

- Panda bus 1 专用于直连 ARS408。
- Tesla 流量仍在 bus 0/2。
- bus 1 不转发。
- ARS408 motion input 当前为启用状态，`0x300/0x301` 走 bus 1。

**当前软件缺口：**

- Tesla CarState/card 尚未监听 bus 1 的真实 `0x3E9` 模板。
- Tesla controller 尚未生成 bus 1 `0x3E9`。
- 目标 safety 白名单目前只有 Tesla `0x488/0x2B9/0x27D` 和 ARS408 `0x200/0x202/0x300/0x301`，`0x3E9` 会被拒绝。

迁移重点因此是补齐 target-native parser/card/controller/safety，并把“专用、非转发”的旧注释和相关假设更新为用户确认的网关拓扑；不需要再讨论换 bus 或新增物理通道。

## 10. MADS、Tesla longitudinal 与 ARS408 影响

- **MADS：** 目标横向权限可独立于 `CC.enabled`。转向 session 必须绑定目标 `CC.latActive`/`madsState` 健康状态，并继续尊重 `invalidLkasSetting`、`steeringDisengage`、刹车策略和 Panda lateral permission。
- **Tesla longitudinal：** 本功能不改 `longcontrol`，但共享 `card`、`sendcan`、Tesla safety 和 Panda 固件；必须回归现有 `0x2B9` longitudinal 路径。
- **ARS408：** bus 1 将同时承载网关放行的车辆帧与 ARS408。迁移不得破坏现有 20 Hz motion、配置/NVM、radar parser 和 tracking 行为。
- **协作转向：** 目标 CarController 已有 cooperative steering，不能用来源整个 CarController 或 safety 文件覆盖。

## 11. 网络安全问题

来源 turn API：

- 监听 `0.0.0.0`。
- `/api/turn/*` 没有认证。
- 没有显式 `IsOffroad`/onroad 守卫；只检查持久 enable，而该 enable 在来源默认是 `1`。

目标现有 8088：

- 同样监听 `0.0.0.0`。
- CORS 为 `*`。
- `/save_params` 是泛化参数写入口。

**建议：** 不能把真实车辆动作直接挂到泛化 `/save_params`。下一阶段至少要设计默认关闭、offroad/restart 配置、专用白名单 API、认证/来源限制、请求 TTL、单 session、速率限制、审计和 fail-closed cancel。具体认证方案需要结合设备实际访问方式另行确定。

## 12. 分析结论与下一阶段硬闸

进入实现前必须先完成以下只读/实测前置：

1. 按 bus 1 可双向收发 `0x3E9` 的既定前提，先设计目标 safety 与 session/IPC 协议，再接 card/controller，网页最后接入。
2. 为 OEM idle 模板、动作帧、cancel 和车辆反馈补目标原生单元测试与 Panda safety 测试。
3. 保持 ARS408、MADS、协作转向和 Tesla longitudinal 的现有发送/权限集合不回归。
4. 软件单测、Panda safety 单测或 `sendcan` txEcho 仍不能称为实车灯光验证；最终需做静止实车点亮、取消、刹车、MADS-loss、controlsd-loss 和车辆反馈测试。

本阶段未修改任何功能代码。
