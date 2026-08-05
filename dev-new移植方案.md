# dev-new 移植方案（以 sp260728XL-tici 为基础，移植 dev 功能）

> 目标：在不动现有 dev 分支/子模块分支的前提下，新增 `dev-new`（主仓库 + 子模块同名），
> 以 moumou758/openpilot sp260728XL-tici 为基线，把 dev 的 Tesla/离线/网页等功能完整移植，
> 移植过程中修复代码 bug，保证新特性可完美使用。

## 一、基线事实（盘点结论）

### 1.1 分支与子模块现状

| 项 | dev（现状） | target（新基线） |
|---|---|---|
| 主仓库 | onemiless/sp `dev`（根目录布局） | moumou758/openpilot `sp260728XL-tici`（嵌套 openpilot/ 布局，2026-07 上游） |
| opendbc_repo | 6e4c52e5（onemiless，含 Tesla 增量） | 4c64e8a9（含 VW MEB 等上游，Tesla 基础文件同源） |
| panda | 29819e26（onemiless，离线唤醒链） | 36b08366（"xl test" hack，不可用） |

### 1.2 target 已含（无需移植）
- XL change 系列（change 1#~14#）、MADS 屏幕激活（#1808）、相机偏移 UI（#1813）、lagd 上限（#38307）、SCC-M 修复（#1816）、cruise fault 优先级（#37557）、MADS Pause 修复（#1871）、新版 sunnylink 参数元数据。

### 1.3 dev 独有功能清单（需移植）

**A. 用户点名（9 项）**
1. 离线唤醒：`system/hardware/offline_wake.py`、hardwared/power_monitoring 集成、panda fork（bootkick/wake_monitor/严格STOP）、相关参数
2. 动态 ACC：opendbc `carstate_ext.py` + `dynamic_acc_debug.py` + 参数（DynamicAutoStock 等）
3. 自动速度设置：opendbc `speed_limit_controller.py` + carstate_ext + 参数（TeslaAutoSpeedLimit）
4. 网页端显示：`selfdrive/debug/driving_status.py`、`tesla_turn_signal_web.py`、`tesla_can_visualization.py`、`device_settings.py`、`device_terminal.py`、`device_hotspot.py` + cereal 自定义字段（teslaRoadContext）
5. 自动同步时间：`sunnypilot/gps_time_sync.py` + manager 集成
6. github 代理：`third_party/mihomo` + `scripts/mihomo_control.py` + `system/updated` 集成 + 参数
7. 离线亮度：AUTO_DARK 参数与 UI 逻辑（target 无此参数）
8. 特斯拉协作转向：opendbc `coop_steering.py` 增量（target 有基础版，dev 版本更完整，需保持现有混控程度）+ TeslaCoopSteering 设置
9. 特斯拉型号全部功能：转向灯控制器/验证（tesla_turn_signal_controller + validation + web 控制）、速度按钮验证、AP Hybrid / split control（selfdrived）、雷达处理、MADS Tesla、tesla_can_probe、HW4 CAN 可视化

**B. 盘点中发现的额外 dev 功能（建议一并移植）**
- 转向灯控制器 + 实时验证 + web 控制（`selfdrive/car/tesla_turn_signal_controller.py` 等）
- AP Hybrid / split control（`selfdrive/selfdrived/selfdrived.py` 的 Tesla 过滤）
- `tesla_mads_debug.py`（MADS 状态调试日志）
- 4 个自定义提示音（`selfdrive/assets/sounds/*.wav`）
- 约 28 个 Tesla/MPC/离线唤醒参数键
- cereal 自定义字段（CarStateSP.teslaRoadContext 等）
- 网页端 MADS 开关与设置页（device_settings）

**C. 明确不移植（核对结论）**
- `lateral_mpc_lib`：dev 内无引用（死代码），上游已删除（#38281）
- 大量 debug 工具：target 已迁移到 tools/scripts 或上游已有等价
- 旧路径文件（system/hardware → common/hardware 等）：用 target 新路径版本
- release/CI/Dockerfile 等构建基础设施：默认用 target 的，除非发现 dev 特有脚本必需

## 二、分支与子模块策略（不碰现有分支）

1. **主仓库**：`dev-new` ← `moumou/sp260728XL-tici`（7de18acbac），推送到 onemiless/sp。
2. **opendbc_repo**：`dev-new` ← target 对应 opendbc 4c64e8a9（onemiless/opendbc），再移植 dev opendbc 增量，推送到 onemiless/opendbc。
3. **panda**：`dev-new` ← dev 当前 panda 29819e26（保留离线唤醒链），推送到 onemiless/panda；**不采用** target 的 "xl test"。
4. 主仓库 `.gitmodules` 与子模块指针指向新 dev-new 分支。

## 三、移植顺序（依赖优先，每阶段一个提交）

### 阶段 0：分支创建
- 主仓库 + opendbc + panda 建 dev-new；主仓库 checkout 新基线；子模块指向新分支。

### 阶段 1：地基
- `common/params_keys.h`：新增 dev 的 28 个参数键（Tesla/MPC/离线唤醒/代理/亮度），对照 target 现有键去重。
- cereal：按新统一 schema 重加自定义字段（custom.capnp/log.capnp/car.capnp），编译并跑 cereal 校验。
- opendbc dev-new：把 dev 的 7 个独有文件 + carstate_ext/coop_steering 等增量移植到 target opendbc 基线；**重加 upstream 删除的 stopping 调参**（vEgoStopping 等）。

### 阶段 2：系统/硬件层
- 离线唤醒：offline_wake.py + hardwared/power_monitoring 集成（适配 common/hardware 新路径）+ panda 唤醒链。
- 自动同步时间：gps_time_sync.py + manager/服务注册。
- github 代理：mihomo 集成 + updated 钩子 + 控制脚本。
- 离线亮度：AUTO_DARK 参数 + UI 逻辑。

### 阶段 3：opendbc Tesla 功能层
- 动态 ACC、自动速度、协作转向（dev 版本）、转向灯/速度按钮验证、AP Hybrid 纵向标志位。
- 每项带对应测试（opendbc 测试）。

### 阶段 4：主仓库控制层
- selfdrived Tesla split-control / AP_HYBRID_ACTIVE 过滤：按新基线状态机重放（新基线已改 IMMEDIATE_DISABLE 优先级、plannerd 校验等）。
- tesla_mads_debug 接入。

### 阶段 5：网页端
- driving_status、tesla web、CAN 可视化、device settings/terminal/hotspot、MADS 开关。
- 适配新 cereal 字段与路径；补齐网页测试。

### 阶段 6：收尾
- 自定义提示音、参数迁移、模型端接口核对（drivingModelData 压缩、单模型 ONNX 对 dev 功能的影响）、全量测试、实车验证清单。

## 四、关键适配点与 bug 风险区

1. **路径/导入**：`system.hardware → common.hardware`、`cereal → openpilot.cereal`、`opendbc.car.structs` 等。
2. **cereal schema**：新基线 car.capnp 统一 + `LeadData.status → present` 改名，dev 消费方需同步。
3. **参数体系**：target 已用动态参数元数据；新键要同时进 params_keys.h 与元数据。
4. **selfdrived 状态机**：新基线改动多，Tesla 过滤逻辑重放时最容易出回归——按"功能语义不变、适配新 API"处理。
5. **opendbc**：upstream 删除了 stopping 调参、改了结构体导入；dev 增量重放后必须跑 opendbc 测试。
6. **panda**：直接用 dev 分支作基础，避免 xl test hack。
7. **modeld/modeld_v2**：drivingModelData 压缩（#38165）与单模型 ONNX 可能改变 dev 依赖的字段，阶段 3 前核对。

## 五、移植纪律（每步可验证）

- 每功能一个提交，先跑对应测试再进入下一项。
- 遇到新 API 导致的 bug：只做"语义不变的最小适配"，在提交信息记录原因。
- 不混入无关重构；不移植 target 已含功能的重复实现（以 target 版为准，除非 dev 版有功能增量）。

## 六、验证策略

- 每阶段：opendbc 测试、cereal 校验、selfdrived/监控测试、网页测试。
- 主仓库整体：可跑测试集。
- 实车验证清单：离线唤醒（休眠→CAN 唤醒）、动态 ACC 切换、自动速度、协作转向混控程度、转向灯验证、网页端驾驶信息/终端/设置、时间同步、代理、离线亮度、AP 混合接管。
- 回归：target 已有功能（XL、MADS、相机偏移、lagd）不受影响。

## 七、已确认决策（2026-08-04）

1. **离线亮度**：不做 5-30% 档位，改为 **0-100% 全范围**，步进加大（如 5% 一档），上限不用太亮（默认值待移植时按合理值设定）。
2. **调试脚本**：移除不影响功能则**直接移除**（只移植影响功能的 dev 自研部分：驾驶信息/终端/设置/热点/转向灯 web）。
3. **dev 特有脚本**：移除不影响功能则**直接移除**（release/CI/构建脚本用 target 的；1.sh、抓包工具等除非功能必需否则不移植）。
4. **实车验证**：暂不做；移植完成后可直连设备测试，设备 IP：**172.16.1.210**。
5. **移植纪律补充**：
   - 移植过程中发现现有代码不规范或有 bug → **直接修复**（语义不变的最小修复，记录在提交信息）。
   - 发现方案清单之外、但属于 dev 特性且影响功能的 → **补入移植范围**，不限于已列功能。
   - 每阶段验证：先跑对应测试，再进入下一阶段。
