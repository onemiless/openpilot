# Tesla ARS408 Radar 迁移分析报告

## 1. 审计结论

Tesla Radar 可以从旧分支迁移到新分支，但不能只复制 `opendbc/car/tesla/*`。旧实现还依赖 ARS408 DBC 和 Tesla Panda safety 发送白名单；缺少任一项都会导致解析器无法初始化，或配置帧被 Panda 拒绝。

建议采用一组最小、雷达专用的补丁，不合并分支，不替换整个 Tesla 模块，也不修改 planner、model、UI 或通用 controls。

本轮仅完成分析并生成本报告，未修改运行代码。

## 2. 对比基线

| 角色 | 仓库/分支 | 审计提交 |
| --- | --- | --- |
| OLD | `onemiless/openpilot:cpv9` | `7b067e28828965f4553d27aa06b19ec12f7adc2c` |
| NEW | `mooo758/openpilot:cpv9-dev-tsl` | `053db6cfadc47eb840245afc70cf8f698287e5f0` |
| merge-base | 两分支共同祖先 | `5ba8b2a769e00ab0e9ea357b6d80b3fa5e09f6cb` |

当前项目的车辆代码布局与原方案假设不同：Tesla 代码位于 `opendbc_repo/opendbc/car/tesla/`，不是 `selfdrive/car/tesla/`。`opendbc_repo` 是当前主仓库中的普通目录，不是独立 git submodule。

## 3. Tesla Radar 差异摘要

NEW 相对 OLD 删除或回退了以下雷达能力：

| 文件 | 差异 | 作用 | 迁移建议 |
| --- | --- | --- | --- |
| `opendbc_repo/opendbc/car/tesla/ars408_can.py` | 删除 65 行 | 生成 ARS408 配置与目标数过滤帧；启动窗口重试及周期刷新 | 必须迁移 |
| `opendbc_repo/opendbc/car/tesla/radar_interface.py` | 删除 346 行 | 解析对象周期、构造 `RadarData/RadarPoint`、目标过滤、故障诊断 | 必须迁移 |
| `opendbc_repo/opendbc/car/tesla/interface.py` | 移除 RadarInterface，`radarUnavailable` 改为 `True` | 注册 Tesla 雷达并设定 14 Hz 周期 | 最小修改 |
| `opendbc_repo/opendbc/car/tesla/carcontroller.py` | 移除 16 行 | 定时发送雷达配置与过滤配置 | 最小修改 |
| `opendbc_repo/opendbc/dbc/ARS408.dbc` | 删除 | CANPacker/CANParser 的消息与信号定义 | 必须迁移 |
| `opendbc_repo/opendbc/safety/safety/safety_tesla.h` | 移除 2 项 TX 白名单 | 允许 bus 1 上发送 `0x200/8B` 和 `0x202/5B` | 必须迁移 |
| `opendbc_repo/opendbc/car/tesla/tests/test_ars408_can.py` | 删除 49 行 | 验证配置编码、bus、Sensor ID 和刷新时序 | 必须迁移 |
| `opendbc_repo/opendbc/car/tesla/tests/test_radar_interface.py` | 删除 120 行 | 验证对象过滤、丢帧容错和 track grace | 必须迁移 |
| `opendbc_repo/opendbc/safety/tests/test_tesla.py` | 移除雷达 TX 测试 | 验证白名单严格限制 bus 和 DLC | 必须最小恢复 |
| `opendbc_repo/opendbc/car/tesla/ars408_config.py` | 删除 172 行 | 依赖 `cantools` 和工作目录 DBC 的独立手工调试脚本 | 不迁移 |

Tesla 目录本身的有效差异合计为 7 个文件、约 772 行删除和 1 行新增。`carstate.py`、`values.py`、`teslacan.py`、`fingerprints.py` 不包含这套 ARS408 集成的必要差异，不应修改。

## 4. 旧实现的数据链路

1. `CarController` 在 frame `10, 50, 100, 200, 500, 1000` 发送配置，之后每 3000 frame 刷新。
2. `ars408_can.py` 使用 `ARS408.dbc` 生成：
   - `0x200` RadarConfiguration，bus 1，8 bytes；
   - `0x202` FilterCfg，bus 1，5 bytes。
3. 雷达配置为 Sensor ID 5、object list、Quality 开启、Extended 关闭、最大距离 300 m、最多 32 个对象。
4. Sensor ID 5 使接收地址在 DBC 基础地址上偏移 `5 << 4`：
   - Status `0x65A`；
   - General `0x65B`；
   - Quality `0x65C`；
   - Extended `0x65D`；
   - RadarState `0x251`。
5. `radar_interface.py` 校验真实地址、bus 和 DLC，再把地址映射回 DBC 的 Sensor ID 0 地址解码。
6. General 与 Quality 按 Obj_ID 配对形成 `RadarPoint`；Extended 可缺失，缺失时 `aRel=0.0`。
7. 接口以 Status 帧作为对象周期边界，发布完整周期；部分丢帧时保留可配对目标，并为已有 track 提供 2 个周期的 grace。
8. `RadarState` 被用于上报临时故障、硬故障与错误配置；配置错误有约 10 秒启动宽限。

## 5. 与 NEW 架构的兼容性

审计结果显示，OLD 与 NEW 的通用 radar 调用链没有差异：

- `selfdrive/car/card.py` 相同，仍从品牌接口取得 `RadarInterface` 并消费 CAN 包；
- `opendbc/car/interfaces.py` 相同，`RadarInterfaceBase` 的 `pts`、`v_ego`、`update()` API 可直接承载旧实现；
- NEW 的 Tesla `interface.py` 仍使用同一 `CarInterfaceBase` 架构；
- NEW 的 Tesla `carcontroller.py` 构造和 update 签名与 OLD 一致。

因此不需要修改 planner、model、UI、`selfdrive/controls/radard.py`、`selfdrive/car/card.py` 或通用接口。迁移应把旧 RadarInterface 注册到 NEW 的 Tesla interface，而不是整体覆盖 NEW 文件。

## 6. 最小补丁范围

### 新增/恢复

- `opendbc_repo/opendbc/car/tesla/ars408_can.py`
- `opendbc_repo/opendbc/car/tesla/radar_interface.py`
- `opendbc_repo/opendbc/dbc/ARS408.dbc`
- `opendbc_repo/opendbc/car/tesla/tests/test_ars408_can.py`
- `opendbc_repo/opendbc/car/tesla/tests/test_radar_interface.py`

### 精确编辑

- `opendbc_repo/opendbc/car/tesla/interface.py`
  - 导入并注册 `RadarInterface`；
  - 设置 `ret.radarUnavailable = False`；
  - 设置 `ret.radarTimeStep = 1.0 / 14.0`。
- `opendbc_repo/opendbc/car/tesla/carcontroller.py`
  - 初始化 `ARS408CAN`；
  - 仅加入雷达配置/过滤帧的定时发送逻辑；
  - 保留 NEW 的其余控制逻辑原样。
- `opendbc_repo/opendbc/safety/safety/safety_tesla.h`
  - 仅恢复 `{0x200, 1, 8}` 与 `{0x202, 1, 5}` 两条白名单。
- `opendbc_repo/opendbc/safety/tests/test_tesla.py`
  - 在 NEW 当前 import/API 风格上，仅恢复两种帧的 bus/DLC 边界测试。

### 明确排除

- `ars408_config.py`：未被运行代码引用，是独立调试脚本，不属于最小运行集。
- `carstate.py`、`values.py`、`teslacan.py`、`fingerprints.py`：无必要雷达差异。
- planner、model、UI、通用 controls、控制参数：不修改。
- OLD 的 `selfdrive/controls/radard.py` ARS408 定制：按本次约束不迁移；基础 RadarPoint 链路仍可工作，但其行为差异应通过 replay 单独验证。

## 7. 必须修正的范围约束

原计划 Round 2 的“只允许 `selfdrive/car/tesla/*`”与实际仓库布局及运行依赖不一致。建议把允许范围改为：

```text
opendbc_repo/opendbc/car/tesla/*
opendbc_repo/opendbc/dbc/ARS408.dbc
opendbc_repo/opendbc/safety/safety/safety_tesla.h
opendbc_repo/opendbc/safety/tests/test_tesla.py
```

如果不允许后 3 类文件：

- 没有 `ARS408.dbc`，`CANPacker("ARS408")` / `CANParser("ARS408")` 无法工作；
- 没有 safety 白名单，Panda 会拒绝配置帧，Sensor ID 会保持默认值；
- parser 期待 Sensor ID 5 的偏移地址，最终不会得到有效对象周期。

## 8. 风险审查

### 高风险

- **Safety 白名单遗漏**：Python 侧看似发送成功，但 Panda 实际拦截。
- **Sensor ID/地址偏移不一致**：配置使用 ID 5，而 parser 或实车雷达仍处于 ID 0，表现为完全无目标。
- **DBC 缺失或未进入构建产物**：初始化时找不到 DBC，或设备端解析失败。

### 中风险

- **雷达启动较慢或 brownout**：旧实现通过 10 秒内多次发送及周期刷新缓解；需要实车确认 frame 时基。
- **共享 bus 负载导致 Quality/Extended 丢帧**：旧 parser 支持部分周期挽救，但必须 replay 验证目标稳定性。
- **未发送车辆运动输入**：旧实现仅配置和读取 ARS408，没有发送 speed/yaw motion frames；静止物过滤及相对速度质量依赖雷达自身状态，需实车验证 `RadarState_MotionRxState`。
- **全车型无条件启用**：`interface.py` 会对 Tesla 候选统一设置 radar 可用。若 NEW 分支同时支持未安装 ARS408 的车辆，应在 Round 2 前决定是否需要显式硬件/参数开关；OLD 当前实现没有该开关。

### 低风险

- 通用 radar API 在两基线间相同，直接接口兼容风险较低。
- 配置不写 NVM，降低 EEPROM 磨损和不可逆配置风险。

## 9. Round 2 验证门槛

建议补丁完成后依次执行：

```bash
python -m compileall opendbc_repo/opendbc/car/tesla
pytest -q \
  opendbc_repo/opendbc/car/tesla/tests/test_ars408_can.py \
  opendbc_repo/opendbc/car/tesla/tests/test_radar_interface.py
pytest -q opendbc_repo/opendbc/safety/tests/test_tesla.py
scons -u -j8
```

此外应确认：

- 生成物中包含 `ARS408.dbc`；
- safety 测试允许且只允许正确 bus/DLC 的 `0x200`、`0x202`；
- replay 中 `RadarData.errors`、目标数量、trackId、`dRel/yRel/vRel` 连续；
- 丢失 Extended 或单个 Quality 帧时不会清空全部目标；
- 实车启动 10 秒后 `RadarState_SensorID == 5`、配置字段符合预期；
- ACC、FCW 和 lead 选择只做观察性验证，不以修改 planner/controls 来修正本轮迁移。

## 10. 建议决策

可以进入 Round 2，但应先接受上述“雷达专用依赖”的范围扩展。实现方式应是把 OLD 的两个独立 radar 文件和 DBC 恢复到 NEW，再对 NEW 的 interface、carcontroller 和 safety 文件做逐行最小编辑；不要整体复制 Tesla 目录，也不要迁移 `ars408_config.py` 或 OLD 的 radard 定制。
