# Rollback Plan

## 立即运行回退

将 `TeslaRadarMode` 设为 `0` 并重启相关进程/设备，可使 Tesla `radarUnavailable=True`，停止 ARS408 配置与 fusion 发布，保留原车 steering、brake、ACC 代码路径。若遇到 CAN 异常，优先物理断开外置雷达并恢复原线束。

## 分组代码回退

所有修改都基于 `407ba0bf0f224121836fe3285c049eae3435c0c0`，并作为单一审计提交交付到 `origin/cp0809`。建议按以下独立组回退：

1. Radar core：`ars408_can.py`、`radar_interface.py`、Tesla `carcontroller.py/interface.py`、Params、`car.capnp`。
2. UI：`ui.cc`、`hud.cc/h`。
3. Tests：三个 Tesla radar/safety 测试文件。
4. Build fixes：根/opendbc SConstruct、fake STM、Panda SConscript、screenrecorder 文件。
5. Reports：包括 `bug_audit_report.md` 在内的六份 Markdown 和 `final_diff.patch`。

若要整体撤销交付，最安全的方式是在后续分支上 revert `cp0809` 的交付提交，或保留 `cp0809` 供审计并切回未修改的 `cpv9-dev-tsl`；不要在有额外用户改动时执行硬重置。

## 部署后回退验证

- 确认分支/commit 指向预期基线。
- 完整重建 Panda 与主程序，确认固件签名一致。
- 检查 `liveTracks` 不再参与 fusion，现有 Tesla steering/brake/ACC 行为不变。
- 清除瞬态 `TeslaRadarReinitialize`，防止旧请求跨部署残留。

## Motion TX 特别说明

当前版本未放行 `0x300/0x301`，因此无需撤销 safety allowlist。未来若另行启用，回退必须同时撤销控制器发送、Panda allowlist 和物理总线接线，不能只改其中一层。
