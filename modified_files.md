# Modified Files

基线：`onemiless/cpv9-dev-tsl@407ba0bf0f224121836fe3285c049eae3435c0c0`
工作分支：`cp0809`

## Radar 功能与接口

| 文件 | 函数/区域 | 修改原因 | 风险 | 测试结果 |
|---|---|---|---|---|
| `opendbc_repo/opendbc/car/tesla/radar_interface.py` | `object_rejection_reason()`、track cycle、`_missing_can_signature()`、状态发布 | 增加拒绝原因、lost 目标两周期保护、掉线检测、模式语义；修复 Monitor 不完整周期泄漏缓存 track | 阈值过严可能漏目标；超时过短可能误报 | Monitor 回归测试先失败后通过；完整构建通过；需 replay/实车确认阈值 |
| `opendbc_repo/opendbc/car/tesla/ars408_can.py` | `should_configure_radar()`、`create_speed_information()`、`create_yaw_rate_information()` | 配置改为启动/异常事件触发；实现 motion frame 编码 | `0x300/0x301` 与共享车载 CAN 冲突 | 编码/DLC 测试通过；实际 TX 保持关闭 |
| `opendbc_repo/opendbc/car/tesla/carcontroller.py` | `send_radar_motion()`、`update()` | 计算速度方向与 yaw rate；响应一次性重新初始化请求 | 错误启用 motion TX 会产生 CAN 冲突 | steering/brake/ACC 路径未改；motion 返回空且 safety 测试确认阻断 |
| `opendbc_repo/opendbc/car/tesla/interface.py` | `_get_params()` | 依据 `TeslaRadarMode` 决定 Radar OFF/Monitor/Fusion/Debug | Params 无效值可能误启用 | 无效值安全回退 OFF；完整构建通过 |
| `common/params_keys.h` | Params key registry | 注册 `TeslaRadarMode` 与瞬态 `TeslaRadarReinitialize` | 清理标志选择错误可能重复配置 | Params C++/Python 生成链随完整构建通过 |
| `system/manager/manager.py` | `get_default_params()` | 默认模式设为 Fusion (`2`)，保持原分支雷达默认启用能力 | 未安装雷达的 Tesla 需手动选 OFF | Python lint/compile 与完整构建通过 |
| `opendbc_repo/opendbc/car/car.capnp` | `RadarData` | 向 UI 发布 online、CAN、object count、mode 元数据 | schema 变更要求消费者同步重建 | Cap'n Proto 生成和完整构建通过 |

## UI

| 文件 | 函数/区域 | 修改原因 | 风险 | 测试结果 |
|---|---|---|---|---|
| `selfdrive/ui/ui.cc` | `UIState` subscriptions | UI 订阅 `liveTracks` 雷达诊断数据 | 新订阅可能增加轻微消息开销 | UI 链接成功 |
| `selfdrive/ui/qt/onroad/hud.cc` | `updateState()`、`drawRadarStatus()` | Tesla HUD 显示模式、online/offline、对象数、lead 来源、CAN 状态 | 小屏布局重叠需设备目视确认 | macOS UI 完整编译/链接通过 |
| `selfdrive/ui/qt/onroad/hud.h` | Radar HUD state | 保存雷达 UI 状态 | 低 | 编译通过 |

## 测试

| 文件 | 函数/区域 | 修改原因 | 风险 | 测试结果 |
|---|---|---|---|---|
| `opendbc_repo/opendbc/car/tesla/tests/test_ars408_can.py` | config/motion tests | 固化启动配置、禁止周期刷新、motion DLC/编码 | 测试不等于实车兼容 | 通过 |
| `opendbc_repo/opendbc/car/tesla/tests/test_radar_interface.py` | tracking/error/mode tests | 覆盖拒绝原因、Sensor ID 5、lost grace、掉线签名、Monitor 模式 | 合成帧不能覆盖道路分布 | 通过 |
| `opendbc_repo/opendbc/safety/tests/test_tesla.py` | Tesla safety cases | 明确验证共享 bus 1 上 `0x300/0x301` 被阻断 | 无 | 6 passed, 3 skipped（定向筛选） |
| `selfdrive/frogpilot/fleetmanager/test_helpers.py` | destination tests | 覆盖地址搜索成功/失败分支 | mock 不覆盖真实 Mapbox 网络 | 2 passed |
| `selfdrive/carrot/test_carrot_man.py` | radar error test | 确保异常处理不再被未定义日志函数二次覆盖 | 低 | 1 passed |

## 构建期间发现并修复的基线 Bug

| 文件 | 函数/区域 | 修改原因 | 风险 | 测试结果 |
|---|---|---|---|---|
| `opendbc_repo/SConstruct` | SCons options | safety 子构建读取 `--coverage`，但未声明该选项 | 低，仅补齐既有调用契约 | safety 构建和 pytest 通过 |
| `opendbc_repo/opendbc/safety/board/fake_stm.h` | test hardware stubs | safety 测试构建缺少 `putui()` | 低，仅测试桩 | safety 构建通过 |
| `panda/SConscript` | `gitversion.h` generation | C 字符串数组未为 NUL 终止符预留空间，现代编译器报错 | 固件签名字节数组长度变化 1 字节，语义修正 | 完整 Panda/根构建通过 |
| `SConstruct` | generated-code environment | 子构建未继承显式 `PARAMS_ROOT`/`CACHEDB`，受限构建环境写入失败 | 仅显式设置时生效 | 完整构建通过 |
| `selfdrive/ui/SConscript` | platform screen recorder selection | Darwin/WSL 无 OpenMAX，却仍编译设备专用录屏器 | 不影响设备架构；Darwin/WSL 不提供录屏 | macOS UI 编译/链接通过 |
| `selfdrive/ui/qt/screenrecorder/screenrecorder.h` | disabled stub | 为无 OpenMAX 平台复用录屏 stub | 低 | UI 编译通过 |
| `opendbc_repo/opendbc/car/interfaces.py` | `get_params()` | `is_release/docs` 无默认值破坏旧调用 API | 默认只影响未显式传参的工具/测试，运行时仍显式传参 | Tesla generic interface 2 passed |
| `common/mock/generators.py` | `generate_livePose()` | Controls 测试引用的 mock 缺失 | 低，仅测试工具 | lateral controls 3 passed |
| `selfdrive/controls/lib/tests/test_latcontrol.py` | interface setup | 测试仍解包旧四元组 API | 低，仅测试 | 3 passed |
| `opendbc_repo/opendbc/car/hyundai/carstate.py` | `CarState.__init__()` | 缺少 `FingerPrints` Param 时 `literal_eval(None)` 崩溃 | 空指纹会关闭可选 ECU 能力，不会凭空启用 | 全车型接口测试中 Hyundai 初始化越过该故障 |
| `selfdrive/car/cruise.py`、`selfdrive/carrot/carrot_man.py`、`carrot_serv.py`、`fleetmanager/helpers.py`、`locationd/paramsd.py` | memory Params paths | 硬编码 `/dev/shm` 在 macOS 不存在 | Linux/tici 路径保持 `/dev/shm` | 261/269 全车型接口样例通过；完整构建通过 |
| `selfdrive/ui/carrot.cc`、`selfdrive/ui/qt/maps/map_settings.cc` | memory Params paths | C++ 同类跨平台路径 Bug | Linux/tici 路径保持不变 | UI 编译/链接通过 |
| `selfdrive/frogpilot/fleetmanager/helpers.py` | `set_destination()` | 修复未定义 `lon/lat`、错误参数类型及失败仍确认目的地 | 真实地理编码仍依赖外部服务 | 2 个回归测试通过 |
| `selfdrive/carrot/carrot_man.py` | `get_radar_data()` exception path | 未定义 `debug_print` 会掩盖原始异常 | 低 | 回归测试通过；F821 检查通过 |

第二轮审计撤回了未被 macOS 构建实际使用、且缺少 tici 验证的 FFmpeg/OpenMAX API 改写。构建生成的翻译重写和缓存文件已清理，没有纳入迁移。
