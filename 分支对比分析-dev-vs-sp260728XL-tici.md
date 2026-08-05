# 分支对比分析：dev vs moumou758/sp260728XL-tici

## 一、总体结论

**dev 分支已经包含了 moumou758/sp260728XL-tici 的全部核心 XL 定制。** 两个分支是同一团队维护的同一套 sunnypilot 定制，差异主要来自三方面：

1. **目录布局不同**：dev 是根目录布局（`selfdrive/`、`system/`、`common/`、`sunnypilot/` 在仓库根），target 是 `openpilot/` 子目录布局。
2. **上游同步进度不同**：target 合并了 2026-07 的 commaai/sunnypilot 上游（sync #118），dev 停留在 2026-06-04 合并基点附近。
3. **子模块来源不同**：dev 用 onemiless 自己的 fork（panda/opendbc），target 用官方 sunnypilot fork。

---

## 二、提交历史结构

| 指标 | dev | target (sp260728XL-tici) |
|------|-----|--------------------------|
| 相对合并基点(46b9253729)新增提交 | 436 | 225 |
| 作者分布 | onemiles(330) + mmoo758(55) + 上游 | mmoo758(20 XL) + 上游(205) |
| XL change N# 提交 | ✅ 全部30个（含历史变体） | ✅ 20个 |

**关键事实**：dev 分支上 mmoo758 提交的 `change 1#~15#` 与 target 上的 `change 1#~14#` 内容一致（除目录前缀），说明 **XL 定制早已合并进 dev**。

---

## 三、逐项分析

### A. XL 定制（change N# 系列）— 已全部在 dev 中

| change | 内容 | dev 状态 |
|--------|------|---------|
| 1# XLpart1 | 硬编码IMEI、禁用自动关机、agnos配置 | ✅ 已含（IMEI号码不同） |
| 2# more-picture | 训练图替换 | ✅ 已含 |
| 3# dm | 注释dmonitoring报警 | ✅ 已含 |
| 4# events | 事件降级 | ✅ 已含 |
| 5# more set | 透明度/音量/更新/提醒/转向弧 | ✅ 已含 |
| 6# relc | 默认开启道路边缘检测 | ✅ 已含 |
| 7# AUTO_DARK | 亮度5-30% | ✅ 已含 |
| 8# bottom | 底部数据显示调整 | ✅ 已含 |
| 9# 方向盘旋转 | exp按钮旋转图标 | ✅ 已含（完全一致） |
| 10# 限速风格 | metric+mutcd | ✅ 已含 |
| 11# 字体 | OpFont字体系统 | ✅ 已含 |
| 12# 汉化 | 默认中文 | ✅ 已含 |
| 13# beep | GPIO蜂鸣器 | ✅ 已含（dev版本更完整） |
| 14# params错误 | 注释locationd/paramsd错误 | ✅ 已含 |

**结论：XL 定制无需再同步，dev 已完整保留。**

### B. 真正的冲突区（4个核心文件）— 必须保留 dev 版本

| 文件 | target 的 XL 改动 | dev 的 Tesla 功能 | 冲突 |
|------|------------------|------------------|------|
| `system/hardware/power_monitoring.py` | `should_shutdown` 直接 `return False`（禁用关机） | 完整关机逻辑（Tesla 离线唤醒需要） | **高**：不可覆盖 |
| `system/hardware/hardwared.py` | 简单 `if should_shutdown: DoShutdown` | 完整离线唤醒关机流程（`request_panda_deepsleep`、`CanShutdownGate`、bus1 CAN 静默门控） | **高**：不可覆盖 |
| `common/params_keys.h` | 删除全部 Tesla/MPC/离线唤醒参数 | 约28个 Tesla/MPC/离线唤醒参数 | **高**：不可覆盖 |
| `selfdrive/selfdrived/selfdrived.py` | 简单 DM/params 注释 | Tesla split-control 过滤、AP Hybrid、AP_HYBRID_ACTIVE 标志位 | **高**：不可覆盖 |

### C. 子模块差异

#### panda 子模块
- **dev HEAD**: `d49b69de`（onemiless，离线唤醒定制链：bootkick 318行 + wake_monitor + 严格STOP）
- **target commit**: `36b08366`（sunnyhaibin，"xl test"）
- **分析**：target 的 "xl test" 仅在 `python/__init__.py` 中把 `get_type()` 硬编码为 `HW_TYPE_TRES`（`return b'\x09'`）。**不是真实的 XL/c3x 硬件支持**（无新 board 文件、无 c3x 代码）。sync#118 只是上游 cosmetic 修正。
- **结论**：**不应同步**。"xl test" 是 hack，会让所有设备伪装成 Tres，破坏 dev 的设备/唤醒调试逻辑。dev 的 bootkick/wake_monitor 定制与目标直接冲突。

#### opendbc 子模块
- **dev HEAD**: `eda62ff4`（onemiless，大量 Tesla 定制）
- **target commit**: `d6b9c1ad`（sunnypilot sync #501）
- **分析**：target 是纯上游 sync，新增 VW MEB (ID.4)、Ford/GM/Nissan/Toyota safety 重构等**通用上游**内容。**Tesla 部分与合并基点完全一致**（目标对 Tesla 零改动），唯一改动是**删除** `interface.py` 的 `vEgoStopping/vEgoStarting/stoppingDecelRate`（上游删除了纵向停止调参）。
- **结论**：**可选择性同步非 Tesla 文件**（VW MEB 等新平台），但合并后必须**重新应用 dev 的 `interface.py` stopping 参数**（上游恰好删了它们）。dev 的 Tesla 定制文件（speed limit、动态ACC、coop steering、turn signal）目标都没碰，无冲突。

### D. 潜在可同步的上游内容（dev 尚未跟进）

target 独有的上游提交中，以下是有价值且与 dev 无冲突的（均为 2026-06 至 07 的 commaai 上游修复）：

**高价值（安全/功能）**：
- `fd22de1c9a` SCC-M: fix operator precedence in quadratic roots (#1816) — 弯道速度计算修复
- `ee3583df33` [tizi/tici] ui: Camera offset controls (#1813) — 相机偏移UI（与 dev 已有 CameraOffset 参数配套）
- `c8786d930d` DM: reasonable lockout ramp up (#38358) — 驾驶员监控锁定渐进
- `3a55f31dc5` agnos 18.5 (#38302) — 系统镜像更新
- `c21b0821da` fix(ui): label alignment and text with icon (#38365)
- `5472e69e35` + `78909dac73` New sounds / soundd complete sound (#38154/#38390) — 新音效（需资源文件）

**中价值（重构/清理，需评估依赖）**：
- `d9596fa998` / `e124d6df9b` 死代码清理
- `fef29ad225` 测试迁移到 unittest
- `c20263d985` speedup chunk reading
- `b9f25f8a43` webrtcd: move to libdatachannel（大重构，慎用）
- `3a05c03079` ci: no more docker

**可能破坏 dev 的（需谨慎）**：
- `fdd1df79fb` longitudinal: remove per-car stopping tunes (#38394) — 删除纵向停止调参（与 dev 的 Tesla MPC 调参冲突）
- `031b1ad0a3` longcontrol: remove starting state (#38340) — 长控状态机简化
- `d1e143ac98` longcontrol: simplify state machine (#38337)
- `45b53cf66a` Rename LeadData.status to LeadData.present (#38339) — API 改名（dev 多处引用需同步改）
- `a26254304f` Move eigen dependency into rednose — 依赖迁移

---

## 四、同步建议（按优先级）

### 建议执行（低风险、高收益）
1. **`fd22de1c9a` SCC-M operator precedence 修复** — cherry-pick，弯道减速计算正确性。
2. **`ee3583df33` Camera offset UI (#1813)** — 为 dev 已有的 CameraOffset 参数补上设备端 UI 入口（此前方案已规划）。
3. **`c8786d930d` DM lockout ramp** — 独立功能，无冲突。
4. **`c21b0821da` UI label 对齐修复** — 独立。
5. **`3a55f31dc5` agnos 18.5** — 需要同时更新 agnos.json 与镜像，评估后再做。
6. **非 Tesla 的 opendbc 上游**（VW MEB、safety 重构）— cherry-pick 非 Tesla 文件。

### 建议评估后执行（中风险）
7. **`5472e69e35`/`78909dac73` 新音效** — 需要同步新 wav 资源，且 dev 的 soundd.py 有 XL 音量 0.1 改动需保留。
8. **`45b53cf66a` LeadData.status→present** — 需要全局替换 dev 中所有 `.status` 引用。
9. **上游 modeld/desire_helper 重构** — target 已跟进，dev 未跟进，长期会扩大分叉。但重构涉及 tinygrad 模型接口，需整体评估。

### 不建议执行（会破坏 dev）
10. **panda "xl test" (`36b08366`)** — 无实际价值，且与 dev 唤醒定制冲突。
11. **`fdd1df79fb` 删除纵向停止调参** — 与 dev Tesla MPC 调参冲突。
12. **power_monitoring/hardwared/params_keys/selfdrived 四个核心文件的 target 版本** — 会丢失 Tesla 离线唤醒功能。

---

## 五、操作建议

如需同步，建议**按 commit cherry-pick 而非整体 merge**，因为：
1. 两个分支目录布局不同（根 vs openpilot/ 前缀），整体 merge 会产生海量文件路径冲突。
2. dev 的核心 Tesla 文件与 target 直接冲突。
3. 子模块 gitlink 指向不同仓库。

推荐流程：
```bash
# 逐个评估目标上游提交
git log dev..FETCH_HEAD --oneline --no-merges | grep -iE 'SCC-M|Camera offset|DM:|label alignment|agnos'
# 对选中的提交，用 patch 方式应用到 dev（手动处理路径前缀）
git show <commit> | git apply -p1 --3way  # 或手动改路径
```

---

*分析日期：2026-08-01*
*合并基点：46b9253729（2026-06-04）*
*dev HEAD：f94f3c0f70*
*target HEAD：9d0ddfdbb9*
