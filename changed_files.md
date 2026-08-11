# Tesla SP 迁移文件清单

基准：`0c39cc20bec3d8e1a8a5db8b7850df31a869168c`

## 参数、启动与 UI

- `common/params_keys.h`：两个持久开关和五个瞬态、禁止日志的状态/请求 key。
- `system/manager/manager.py`：新增开关默认值，均为 `0`。
- `system/manager/process_config.py`：仅 `EnableTeslaTools=1` 时启动 8090 服务。
- `selfdrive/ui/qt/offroad/settings.cc`：新增网页转向测试与速度同步设置说明。

## Tesla CAN 与目标适配

- `opendbc_repo/opendbc/car/tesla/values.py`：独立 Car/Panda feature bits。
- `opendbc_repo/opendbc/car/tesla/interface.py`：按启动参数配置功能与 safety bit。
- `opendbc_repo/opendbc/car/tesla/carstate.py`：保存 Tesla 速度单位和 AP 活动状态，不改变原事件判断。
- `opendbc_repo/opendbc/car/tesla/turn_signal_controller.py`：新实现 0x3E9 session、反馈与取消状态机。
- `opendbc_repo/opendbc/car/tesla/speed_sync_controller.py`：新实现 0x3C2 单 tick 同步、反馈与手动恢复状态机。
- `opendbc_repo/opendbc/car/tesla/carcontroller.py`：在现有发送列表末端增量接入两个控制器。
- `selfdrive/car/tesla_speed_target_provider.py`：只提供新鲜的道路限速加 offset 目标。
- `selfdrive/car/card.py`：raw CAN observer、窄 Params 协议、变道上下文与目标传递；保留原控制调用顺序。
- `opendbc_repo/opendbc/car/tesla/ars408_can.py`：仅更新 bus 1 网关契约注释。

## Panda Safety

- `opendbc_repo/opendbc/safety/safety/safety_tesla.h`：增加 0x3C2/0x3E9 的模板、字段、频率、session 和独立 flag 校验。
- `opendbc_repo/opendbc/safety/tests/test_tesla.py`：增加拒绝/接受测试，并保留 ARS408/MADS 覆盖。

## 8090 Web 服务

- `selfdrive/tesla_web/__init__.py`
- `selfdrive/tesla_web/auth.py`：当前明确为临时无认证策略。
- `selfdrive/tesla_web/routes.py`：窄 REST API、TTL 所需时间戳、限流和响应头。
- `selfdrive/tesla_web/server.py`：`ThreadingHTTPServer`，监听 8090。
- `selfdrive/tesla_web/templates/index.html`：左/右/取消与状态页。

## 新增或调整测试

- `opendbc_repo/opendbc/car/tesla/tests/test_aux_feature_flags.py`
- `opendbc_repo/opendbc/car/tesla/tests/test_speed_sync_controller.py`
- `opendbc_repo/opendbc/car/tesla/tests/test_turn_signal_controller.py`
- `opendbc_repo/opendbc/car/tesla/tests/test_ars408_can.py`：只更新网关语义测试名。
- `selfdrive/car/tests/test_tesla_speed_target_provider.py`
- `selfdrive/car/tests/test_tesla_tools_protocol.py`
- `selfdrive/tesla_web/tests/__init__.py`
- `selfdrive/tesla_web/tests/test_routes.py`

## 文档

- `target_sha.md`
- `turn_signal_analysis.md`
- `auto_speed_analysis.md`
- `migration_plan.md`
- `migration_report.md`
- `changed_files.md`
- `test_report.md`
- `rollback_plan.md`
