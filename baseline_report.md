# Tesla ARS408 Migration Baseline Report

生成日期：2026-08-09（Asia/Shanghai）

## 1. 比较基线

开始比较前已执行远端同步。比较对象如下：

| 角色 | 远端/分支 | Commit | 时间 | 说明 |
|---|---|---|---|---|
| Base | `onemiless/openpilot:cpv9-dev-tsl` | `407ba0bf0f224121836fe3285c049eae3435c0c0` | 2026-08-05 11:23:48 +0800 | 当前目标基线，已包含两次 Tesla ARS408 迁移提交 |
| Additional check | `mooo758/openpilot:cpv9-dev-tsl` | `053db6cfadc47eb840245afc70cf8f698287e5f0` | 2026-08-04 14:19:39 +0800 | 是 Base 的直接祖先 |
| Reference | `juyun86/cp:cpv9` | `bf64c31fd986e1c65e44f67bd2823a18ea6b6e29` | 2026-08-09 11:56:45 +0800 | ARS408 增强参考分支 |

`onemiless/cpv9-dev-tsl...mooo758/cpv9-dev-tsl` 的左右提交数为 `2/0`，共同基线是 `053db6cfa`。Base 多出的两个提交为：

1. `aae522cef Restore Tesla ARS408 radar support`
2. `407ba0bf0 Harden Tesla radar enablement`

`onemiless/cpv9-dev-tsl...juyun86/cpv9` 的左右提交数为 `14/10`，共同基线是 `5ba8b2a769e00ab0e9ea357b6d80b3fa5e09f6cb`。因此不能直接 merge 或批量 cherry-pick，只能做函数级审计和迁移。

## 2. Tesla 差异

相对 mooo758，Base 已增加/修改 11 个雷达相关文件，共 `1437 insertions, 3 deletions`，包括：

- `opendbc_repo/opendbc/car/tesla/ars408_can.py`
- `opendbc_repo/opendbc/car/tesla/radar_interface.py`
- Tesla `carcontroller.py`、`interface.py`
- `opendbc_repo/opendbc/dbc/ARS408.dbc`
- Tesla Radar/Panda safety 定向测试
- Tesla Panda safety allowlist

当前架构的 Tesla 实现位于 `opendbc_repo/opendbc/car/tesla/`，文档中的 `selfdrive/car/tesla/` 路径不存在。后续修改必须遵循现有目录，不建立重复实现。

Reference 与 Base 的 Tesla 目录有 8 个文件差异，合计 `685 insertions, 138 deletions`。Reference 还包含未被运行时调用的 `ars408_config.py`，不会整文件迁入。

## 3. Controls 差异

Reference 与 Base 的 `selfdrive/controls` 有 4 个文件差异，合计 `894 insertions, 721 deletions`：

- `selfdrive/controls/controlsd.py`
- `selfdrive/controls/lib/desire_helper.py`
- `selfdrive/controls/radard.py`
- `selfdrive/controls/tests/test_radar_track_selection.py`

这些差异包含分支架构和功能分叉，不能用 Reference 覆盖 Base。Task 5 只审核 Base 的 `RadarState -> radard -> LongitudinalPlan/Controls` 调用链；仅在发现确定 bug 时做最小修复。

## 4. Model 差异

`selfdrive/modeld` 在 Base 与 Reference 之间没有文件差异；Base 相对 mooo758 的两次雷达提交也没有修改 model。当前模型能力和输入结构因此以 Base 为准，Radar 迁移不得修改模型输入或输出结构。

## 5. UI 差异

Reference 与 Base 的 `selfdrive/ui` 有 13 个文件差异，合计 `3455 insertions, 403 deletions`，主要涉及 `carrot.cc`、设置页和多语言翻译。它们不是独立的 Radar 状态实现，不能整体迁移。

Task 7 若增加 Radar 状态，只允许在 Base 当前 UI/消息架构内做最小增量，并必须验证不会破坏现有 UI 构建和消息兼容性。

## 6. Safety 差异与迁移边界

当前仓库的 Panda safety 实现在 `opendbc_repo/opendbc/safety/safety/safety_tesla.h`，不是文档中的 `panda/board/safety/safety_tesla.cc`。Reference 与 Base 的 Tesla safety 及测试有 2 个文件差异，合计 `30 insertions, 14 deletions`。

Base 已允许 ARS408 配置帧 `0x200`（bus 1, DLC 8）和 `0x202`（bus 1, DLC 5）。共享 Tesla CAN 上的 motion input `0x300/0x301` 存在原车 CAN ID 冲突风险；在没有隔离总线或实车 CAN capture 证明无冲突前，不得仅为满足功能项而降低 safety allowlist。

## 7. 基线结论

- 保留 `407ba0bf0` 之后的全部 cpv9-dev-tsl 能力。
- 以 Base 已有的 ARS408 迁移为起点，逐函数对照 Reference，不重复迁移。
- 不修改 model 输入结构，不覆盖 controls/UI，不修改 steering/brake/ACC 核心控制。
- 配置、tracking、掉线诊断、参数模式、状态显示和 safety 分别验证。
- 任何 motion input TX 必须先通过物理网络冲突审计；不能以扩大 allowlist 代替安全证明。
