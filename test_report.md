# Test Report

测试日期：2026-08-09（Asia/Shanghai）

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

完整构建覆盖了 Cap'n Proto 生成、Tesla/opendbc、Panda、安全库、controls、logger/system 和 Qt UI 编译链接。

## 全仓审计限制与既有失败

- 全仓 Ruff 输出约 4700 行，绝大多数是既有格式、未使用变量和长行；本轮没有机械改写整个 fork。
- 车型接口仍有 8 个数据问题：4 个车型缺少 torque 参数，4 个 GM 车型 PID `kf=0`。这些值需要车辆标定，不能安全猜测。
- 完整 Safety suite 与该 fork 的 `aol_allowed=true` 定制语义不一致；MISRA mutation 测试也不能用 xdist 并行，否则会污染动态测试库。Radar safety 定向测试在干净重建后通过。
- `test_cruise_speed.py` 在本机 msgq `pub_sock` 处进程 abort；无 route/设备消息环境，未将其判为车辆运行 Bug。

## 尚未执行

### Replay

当前没有提供包含 Sensor ID 5 ARS408 帧的 Tesla route。待获取 route 后应同时检查：

- `liveTracks/RadarData`: online、canValid、objectCount、mode 和 track 生命周期。
- `radarState`: leadOne/leadTwo 来源、稳定性和掉线恢复。
- `carState`: `canValid` 不应由可选 Radar 缺帧污染。
- `controlsState` / `longitudinalPlan`: Monitor 模式不使用 radar lead；Fusion 模式 lead 变化连续。

### 实车阶段门槛

1. Monitor：确认无控制参与、无总线异常、HUD/日志正确。
2. Fusion：低速封闭环境确认 lead 选择、切入/丢失和紧急 OFF 回退。
3. 高速 ACC：仅在前两阶段通过且有人类驾驶员随时接管时进行。

在完成上述证据前，不能声称 replay 或实车验证通过，也不能启用 `0x300/0x301` motion TX。
