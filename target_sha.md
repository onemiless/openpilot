# Tesla CPV9 迁移基线

记录时间：2026-08-11（Asia/Shanghai）

## Git 基线

- 仓库：`/Users/mile/Desktop/cp/cpv9-mads-worktree`
- 来源分支：`cpv9-mads-ars408-motion-track-20260810`
- 实施分支：`codex/tesla-tools-migration-20260811`
- 基线提交：`0c39cc20bec3d8e1a8a5db8b7850df31a869168c`
- 远程：`origin = https://github.com/juyun86/cp`
- 来源分支在冻结时相对对应远程分支 ahead 9。
- 冻结前工作树只有第一阶段生成的三份未跟踪分析文档：`turn_signal_analysis.md`、`auto_speed_analysis.md`、`migration_plan.md`。

## 受保护的目标功能基线

以下为代码配置，不代表设备运行态或实车验证结果：

- ARS408：`TeslaRadarMode` 默认 `2`（Fusion），14 Hz radar time step。
- ARS408 motion input：`TeslaRadarMotionInput` 默认 `1`；代码常量 `ARS408_MOTION_INPUT_ENABLED = True`。
- ARS408 CAN：bus 1，Sensor ID `0`，现有配置、filter、`0x300/0x301` motion 发送链必须保留。
- MADS：`Mads=1`、`MadsUserEnabled=1`、`MadsSteeringMode=2`。
- Cooperative steering：`TeslaCoopSteering=1`。
- Tesla longitudinal：保留现有 `0x2B9` 发送、安全限制与 stock AEB passthrough。

## 本阶段边界

- 两项新增功能使用用户确认的 bus 1 双向 `0x3E9`/`0x3C2` 前提。
- 不 cherry-pick 来源功能提交，不复制或替换整个 `card.py`、Tesla CarController、Tesla safety 文件。
- 未经明确接口契约确认，不开始车辆动作实现。
