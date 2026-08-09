# Repository Bug Audit Report

审计日期：2026-08-09
分支：`cp0809`

## 已确认并修复

1. **Monitor 隔离泄漏**：不完整 ARS408 周期发布缓存 track，使 Monitor 短暂进入 fusion。新增失败回归测试后修复。
2. **CarInterface API 断裂**：`get_params()` 的 `is_release/docs` 变为必填，旧调用全部 `TypeError`。恢复向后兼容默认值。
3. **Controls 测试不可运行**：缺少 `generate_livePose()`，并仍解包旧 interface 四元组。补齐 mock 并更新测试 API。
4. **共享内存路径不可移植**：Python/C++ 多处硬编码 `/dev/shm/params`。统一使用仓库已有 `Paths.shm_path()`/`Path::shm_path()`；Linux/tici 行为不变。
5. **Hyundai 空指纹崩溃**：`FingerPrints` 缺失时执行 `ast.literal_eval(None)`。改为空 bus map 安全回退。
6. **Fleet Manager 目的地崩溃**：地址分支使用未定义 `lon/lat`、传错参数类型，并在搜索失败时仍确认。新增成功/失败测试并修复。
7. **Carrot Radar 异常处理二次崩溃**：异常分支调用未定义 `debug_print`，掩盖原始错误。新增测试并修复。
8. **设备兼容风险清理**：撤回未被 macOS 构建使用且未在 tici 验证的 FFmpeg/OpenMAX API 改写，保留平台选择修复。

## 已确认但未安全修复

| 问题 | 证据 | 原因 |
|---|---|---|
| 缺 torque 数据 | `FORD_ESCAPE_MK4_5`、`FORD_EXPEDITION_MK4`、`GMC_YUKON_CC`、`KIA_K5_DL3_24_HEV` 触发 `KeyError` | 需要真实车辆标定，不能填写猜测值 |
| PID tuning 不完整 | `BUICK_REGAL`、`CADILLAC_ATS`、`CHEVROLET_VOLT_CC`、`HOLDEN_ASTRA` 的 `kf=0` | 改值会直接影响横向控制，需车型验证 |
| Safety 测试契约分叉 | 通用 angle/torque 测试假定 controls disabled 时禁止转向，但 fork 核心写死 `aol_allowed=true` | 属于全 fork 控制策略决策，不能在 Radar 迁移中擅自禁用 |
| Sensor ID 5 配置地址 | RX 使用 `0x251/0x65A-0x65D`，TX 仍为 `0x200/0x202` | 需 ARS408 协议文档或实车 CAN capture 确认是否应使用 `0x250/0x252` |

## 环境限制

- 无 Tesla ARS408 replay route、Panda/雷达硬件或实车。
- macOS 下 `test_cruise_speed.py` 在 msgq publisher 初始化处 abort，无法作为车辆行为结论。
- MISRA mutation 测试会改写/重建 safety 测试库，不能与 xdist 并发运行。

因此，本报告覆盖可静态证明、可构建和可在本机确定重现的代码问题；不把未运行的车辆行为描述为已经验证。
