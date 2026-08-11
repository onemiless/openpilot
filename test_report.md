# Tesla SP 迁移测试报告

## 通过项

| 范围 | 结果 | 说明 |
|---|---:|---|
| 新控制器、feature flags、目标 provider | 16 passed | 包含 1 秒边界与超过 1 秒不恢复、MADS-only/制动/AP fail-closed |
| Tesla car 全目录 + provider | 88 passed | 包含既有 ARS408、radar、cooperative steering 测试 |
| Card JSON/TTL 协议 | 2 passed | 对象类型、5 秒边界、未来时间和过期请求 |
| Tesla Web API | 4 passed | start/cancel/status/health、无 CORS 通配、无认证提示 |
| Tesla interface | 2 passed | Model 3/Y 实例化和 apply 冒烟 |
| Manager process config | 3 passed, 1 skipped | 包含新进程 prepare/import 检查 |
| MADS | 19 passed | 独立状态机与 radar/driver override 回归 |
| Tesla Safety 定向回归 | 42 passed, 21 skipped | `turn_signal or speed_sync or ars408 or mads` |
| UI 编译 | passed | `selfdrive/ui/ui` 完整链接成功 |
| Panda 固件编译 | passed | F4 `panda.bin` 与 H7 `panda_h7.bin` |
| Python compileall | passed | 新 Web、provider 和两个控制器 |
| Ruff（本次新增/修改 Python，排除 card 既存告警） | passed | 没有新增 lint 错误 |

测试使用独立的 `/private/tmp` LOG/Params/ARS408 根目录，避免污染用户运行数据。

## 完整 Tesla Safety 结果

结果：`95 passed, 55 skipped, 2 failed`。

两个失败均为 `test_vehicle_speed_measurements`：期望 4.5，实际 4.3889999，差值 0.111 超过既有 0.1 容差。已在干净的起始提交 `0c39cc20b` 临时 worktree 单独运行同一测试，得到同样的两个失败，因此不是本次迁移引入。本次没有修改车速测量或该测试的容差。

## 未取得通过证据的既有测试

- `selfdrive/controls/tests/test_longcontrol.py`：3 个测试均以旧参数调用当前 `long_control_state_trans`，缺少 `a_ego`、`stopping_accel`、`radarState`，在测试体进入前失败。本次未修改 `longcontrol.py` 或这些测试。
- `selfdrive/car/tests/test_cruise_speed.py`：本机 macOS 在 `msgq.pub_sock` 初始化处主动 abort，提升本机权限后结果相同，没有进入巡航仿真。本次没有修改该测试所用 cruise 逻辑。
- Ruff 扫描 `card.py` 会报告原文件末尾一处 173 字符行和一处空白行；两处在基线已存在且不在本次 diff 中。

## 证明边界

未连接 Panda、未刷固件、未连接车辆、未采集真实 bus 1 回包。因此以下仍未验证：实机 Safety accept/reject、0x3E9 灯光反馈、0x3C2 Tesla PCM 反馈、TX echo 方向标记、实际 KPH/MPH 显示步进、道路联合行为。

---

# 历史快照：Test Report（2026-08-09）

以下保留仓库原有 ARS408 迁移测试记录的关键事实用于追溯；其 motion TX 状态不代表当前分支。

## 已执行

| 检查 | 命令/范围 | 结果 |
|---|---|---|
| Python 语法 | 全部修改 Python 文件 `python -m compileall` | 通过 |
| Ruff 确定性错误 | 修改 Python 文件 `ruff --select F821` | 通过（仓库仍有大量既有风格 lint） |
| Tesla/Radar/interface | Radar 两文件加 Tesla generic interface | `19 passed, 267 deselected` |
| Tesla safety 定向测试 | `pytest .../test_tesla.py -k 'radar or ars408 or motion'` | `6 passed, 3 skipped, 89 deselected` |
| Lateral Controls | `selfdrive/controls/lib/tests/test_latcontrol.py` | `3 passed` |
| Fleet/Carrot 回归 | 新增两个测试文件 | `3 passed` |
| 全车型 interface 快速样例 | `MAX_EXAMPLES=1 ... selfdrive/car/tests/test_car_interfaces.py` | `261 passed, 8 failed`；8 项均为既有 tuning/torque 数据缺口 |
| Safety 行为 | ARS408 config bus/DLC；motion `0x300/0x301` bus 1 DLC 2 | 配置约束通过；motion 均被拒绝 |
| 完整构建 | `PARAMS_ROOT=/private/tmp/cp-new-params CACHEDB=/private/tmp/cp-new-tinygrad-cache.db PATH=.venv/bin:... .venv/bin/scons -u -j8` | `scons: done building targets.` |
| Diff 健康 | `git diff --check` | 通过，无 whitespace error |

当时完整构建覆盖 Cap'n Proto、Tesla/opendbc、Panda、安全库、controls、logger/system 和 Qt UI。

## 当时的限制与既有失败

- 全仓 Ruff 有大量既有风格告警，没有机械改写整个 fork。
- 全车型 interface 有 8 个既有 tuning/torque 数据缺口。
- 完整 Safety suite 与当时 fork 的 `aol_allowed=true` 语义不一致。
- `test_cruise_speed.py` 在本机 msgq `pub_sock` 处 abort。

## 当时尚未执行

缺少 Sensor ID 5 ARS408 route，未完成 replay；Monitor、Fusion、高速 ACC 三阶段实车验证均待硬件执行。
