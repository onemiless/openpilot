# Tesla SP 迁移回滚方案

## 运行时停用（首选）

1. 将 `EnableTeslaTools` 设为 `0`。
2. 将 `TeslaSpeedSyncEnabled` 设为 `0`。
3. 重启 openpilot/车辆会话，使 CarParams、Panda safetyParam 和 manager 进程重新初始化。

结果：8090 不再启动，0x3E9 和 0x3C2 的 Python 控制器均未配置，Panda 对这两类新增 TX 默认拒绝。既有 ARS408、MADS、cooperative steering 和 Tesla longitudinal 参数不需要改变。

仅关闭浏览器或防火墙端口不等同于完整停用；功能 flag 是启动时读取，必须修改参数并重启。

## 代码回滚

- 部署前：继续运行基线分支 `cpv9-mads-ars408-motion-track-20260810` 即可。
- 已部署主程序但未刷 Panda：切回基线分支并重建/重启。
- 已刷入包含新 Safety 的 Panda：切回基线分支后，必须同时用基线代码重建并刷回 Panda 固件，避免主程序和 safetyParam/whitelist 版本不一致。

本分支按功能层拆分提交，可在新分支上从后往前 revert；不要单独回退 Safety 而保留 Python 发送，也不要单独保留 Safety 白名单而删除应用层状态机。

## 故障时立即动作

- 转向灯无法取消、拨轮持续动作、ARS408 数据中断或现有纵向/横向行为异常：人工接管，停止测试，关闭两个参数并重启。
- 在完成静止车辆取消验证前，不进入道路速度同步测试。
- 回滚后先确认 8090 不监听，再确认 Panda 使用基线固件，最后复跑 ARS408/MADS/Tesla longitudinal 基线测试。

---

# 历史快照：Rollback Plan（2026-08-09）

以下为仓库原有 ARS408 迁移回滚记录，保留用于追溯；其中 motion TX 未放行等结论只对应当时版本。

## 当时的立即运行回退

将 `TeslaRadarMode` 设为 `0` 并重启相关进程/设备，使 `radarUnavailable=True`，停止当时的 ARS408 配置与 fusion 发布。若遇到 CAN 异常，优先物理断开外置雷达并恢复原线束。

## 当时的分组代码回退

修改基于 `407ba0bf0f224121836fe3285c049eae3435c0c0`，作为 `origin/cp0809` 交付。分组包括 Radar core、UI、Tests、Build fixes 和 Reports；建议在后续分支 revert 交付提交，禁止在含其他改动时硬重置。

## 当时的部署后验证

- 确认分支/commit 和固件签名。
- 检查 `liveTracks` 不再参与 fusion，Tesla steering/brake/ACC 保持原行为。
- 清除瞬态 `TeslaRadarReinitialize`。

## 当时的 Motion TX 说明

该版本未放行 `0x300/0x301`；未来启用时要求同时协调控制器、Panda allowlist 和物理总线。当前分支的实际状态应以 `target_sha.md` 与现行代码为准。
