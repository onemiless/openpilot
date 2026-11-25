# lean-mici × dev-sp：特斯拉功能移植方案

> 交付对象：Codex（执行）。调研日期 2026-10-09，所有数字来自 GitHub API / raw 文件的实测，不是估算。
> 凡是"推断"都明确标注"推断"；凡是需要用户拍板的点都集中在第 9 节。

---

## 0. 一页结论

1. **基线选 `lochuan/lean-mici` 的 `lean-master`，不是 `lean-release`。**
   `lean-release` 是设备上构建出来的单孤儿 commit 扁平树（含预编译 `.so`、panda 固件、`prebuilt` 标记），不能 merge、不能 cherry-pick。
   `lean-release` 的内容 = `lean-master`（源）+ gitlink 物化 + 设备编译产物，由 `tools/release/device_release.sh` 生成。
   移植工作全部做在 `lean-master` 之上，发布仍走 lean 自己的 `device_release.sh`（通过 `SRC_BRANCH` / `RELEASE_BRANCH` 环境变量指向新分支）。
2. **要动三个仓库**（lean 的 `opendbc_repo`、`panda` 是 gitlink 子模块）：
   | 仓库 | 起点 | 新分支 | 内容 |
   |---|---|---|---|
   | 主仓 `<you>/lean-mici`（fork 自 lochuan/lean-mici） | `lean-master` @ `4802cb2f` | `lean-tesla` | 特斯拉控制/纵向/红绿灯/UI/硬件 profile |
   | `onemiless/opendbc` | `lochuan/opendbc` @ `7b519bc3`（lean 当前 pin） | `lean-tesla` | 恢复 Tesla 车型、DBC、safety、ARS408 |
   | `onemiless/panda` | lean 当前 pin `74a0adce` | `lean-tesla` | DOS(STM32F4) 固件恢复，保持 H7 不变 |
3. **dev-sp 的改动量其实不大**：主仓 38 个 commit / 198 个文件（相对其基线 `16322aef`），opendbc 2 个 commit / 47 个文件，panda 4 个 commit / 52 个文件。
   其中 **~92 个主仓文件是纯新增**（Tesla 模块、纵向后端、红绿灯控制、UI 页面、硬件 profile），可以原样拷贝，对上游 0 冲突。
   真正会侵入 lean 代码的是"接缝（seam）"文件：Tesla 核心（P2/P3）约 24 个上游文件、约 380 行（其中 cereal + params 约 180 行是纯追加块）；C3/C3XL 硬件（P4）另有约 22 个文件、约 150 行。本方案的核心就是把这些接缝压到最小并登记在册。
4. **不移植**：Chestnut 模型/道路缩放、DM（驾驶员监控）开关、日志开关、更新分支策略、dev-sp 自己的发布工具。
   理由：lean 已 `DISABLE_DRIVER=1`、没有 `modeld_v2`、有自己的 `tools/release`；这些在 lean 里要么无意义要么会和 lean 自己的实现打架。
5. **最大的三个坑（已实测确认，不是猜测）**：
   - `Event` 联合体槽位 `@136` 在 lean 里已被 `bigModelReply` 占用，dev-sp 的 `trafficRadarState @136` 必须改放 `@137`。
   - lean 的 AGNOS 没有 `capnpc`，`openpilot/cereal/gen/cpp` 是**提交进仓库的生成物**；改了 `.capnp` 必须用 `tools/release/regen_cereal_gen.sh` 重新生成并提交，否则设备端用旧生成物编译，且"目前没有工具能拦这个类别"（lean 自己脚本里的原话）。
   - lean 的 panda 只有 H7 板型（`cuatro/red/tres`），pandad 只有 SPI（`spi.cc`）。**C3（DOS/F4 + USB）需要恢复固件 + 恢复 pandad 的 libusb 通路**；C3XL（SPI 的 tres，无座舱摄像头/无功放）需要 profile 层。

---

## 1. 调研事实（已核实）

### 1.1 两个代码库是什么

| | lean-mici（基线） | onemiless/openpilot `dev-sp`（特斯拉来源） |
|---|---|---|
| 上游 | fork 自 `sunnypilot/sunnypilot`，v2026.003.000 | fork 自 sunnypilot，基线 `16322aef`（2026-09-30） |
| 与对方关系 | 相对 `16322aef`：lean 多 518 个 commit、少 132 个 commit（diverged） | 相对 `16322aef`：多 38 个 commit |
| 车型 | **仅 Toyota + mock**（opendbc 里 Tesla/Honda/Hyundai… 全部裁掉；`opendbc/car/values.py` 只有 `MOCK | TOYOTA`） | 上游 sunnypilot 全车型 + Tesla 改造 |
| 特色 | `bigmodeld`（经 WiFi/LAN 把大模型放到 App/NPU 上跑，失败回落小模型）、`lanlinkd`、`NPU_GREEN` HUD、分段 torqued、`DISABLE_DRIVER=1`（无 DM） | Tesla 控制、三种纵向后端、红绿灯停车、BMS、C3/C3XL/C4 三设备 |
| 子模块 | `opendbc_repo`→`lochuan/opendbc@7b519bc3`；`panda`→`74a0adce`（提交信息为 sunnypilot/panda 的 Sync；`.gitmodules` 写的是 commaai/panda）；`msgq_repo@e7396e76`；`rednose_repo@28d4a7f6`；`tinygrad_repo@9d0446a4` | `opendbc_repo`→`onemiless/opendbc@3b9bf189`；`panda`→`onemiless/panda@ac0f791f`；`tinygrad_repo@fe5d3169` |
| 发布 | `tools/release/device_release.sh` 在**设备上**构建并剥离成扁平树，发到 `lean-release`；`release_lib.py` 管产物清单 | `tools/dev_sp_release/`（lean 不需要） |
| 已被裁掉 | NNLC、eagled、Ford/Hyundai/GM/Honda/Nissan/Tesla 车型、`modeld_v2`、Chestnut、sunnylink 云端残留、DM | — |

lean-master 目录里**没有**任何 `tesla` 命名的文件（已用全树搜索确认）。`opendbc/safety/modes/tesla.h` 仍在（safety 模式没裁，只裁了 `car/`、`dbc/`、测试）。

### 1.2 dev-sp 相对其基线的改动清单（按性质）

主仓 198 个文件 → 分类结果（详见附录 A）：

| 类别 | 文件数 | 处理 |
|---|---|---|
| **纯新增 Tesla 相关**（`sunnypilot/selfdrive/car/tesla/*`、`traffic_control/*`、`longitudinal_backends/*`、Tesla UI、测试、fixtures） | ~92 | 原样拷贝 |
| **接缝**（修改上游文件里的几行） | ~24 个 Tesla 必需（+ ~22 个硬件） | 只手工应用 Tesla 的 hunk |
| C3/C3XL 硬件（pandad USB、profile、AGNOS、hardwared…） | ~25 | 第 4 阶段 |
| Chestnut / 模型 / 道路缩放 / camerad | ~20 | **不移植** |
| DM 开关 / 日志开关 / 分支策略 / UI 重启 / 字体 | ~15 | **不移植**（或可选） |
| dev-sp 自己的文档/发布工具 | ~25 | 参考，不拷 |

### 1.3 把 dev-sp 的补丁直接试打到 lean-master 上的结果

方法：取 dev-sp 相对 `16322aef` 的逐文件 patch，对 lean-master 同路径文件执行 `git apply --check`。69 个被修改的文件：

- **43 个干净通过**（含 `card.py`、`controlsd.py`、`plannerd.py`、`longcontrol.py`、`long_mpc.py`、`longitudinal_planner.py`、`speed_limit/*`、`events.py`、pandad 全部、`hardware.py/.h`、camerad、`hardwared.py`…）
- 4 个放宽上下文后通过（`params_keys.h`、`manager.py`、`sunnypilot/selfdrive/car/interfaces.py`、`.gitignore`）
- **18 个冲突**：`cereal/{custom.capnp,log.capnp,services.py,SConscript}`、`selfdrived.py`、`process_config.py`、`process.py`、`modeld/*`、`models/helpers.py`、若干 UI（`settings.py`、`mici/layouts/settings.py`、`mici/onroad/hud_renderer.py`、`ui_state.py`×2、`mici/.../toggles.py`、`launch_chffrplus.sh`、字体 otf）
- 4 个在 lean 里已不存在：`modeld_v2/*`、`chestnut/status.py`、`vehicle/brands/tesla.py`

结论：**lean 的控制链（card/controlsd/plannerd/longcontrol）和 dev-sp 基本同构**，接缝可以几乎原样套；冲突集中在 cereal 槽位、manager/process_config、UI 注册点——这些正是本方案要手工处理并登记的点。

### 1.4 opendbc 与 panda 的偏移

- **opendbc**：dev-sp 的基线 `b2acec1d`（sunnypilot/opendbc master，2026-09-30）与 lean 的 `7b519bc3` 已分叉：lean 独有 17 个 commit（Toyota 裁剪、Sienna SecOC…），lean 缺 10 个上游 commit（含 `Tesla: add entries for model year HW split (#3748)` 对 `tesla/values.py`、Honda/Hyundai AEB 等）。dev-sp 的 Tesla 文件已经包含 #3748，所以**以 dev-sp 的 Tesla 文件为准**。
  dev-sp 在 opendbc 上只多 2 个 commit（`e15d1889`、`3b9bf189`，47 个文件），其中真正改了上游共享文件的只有：`car/structs.py`(+9)、`sunnypilot/car/interfaces.py`(+53/-5)、`safety/{safety.h,declarations.h,modes/defaults.h,modes/tesla.h}`、`safety/tests/libsafety/safety.c`。
  lean 的裁剪 commit（`a595dced 2622fb1b 821af8e7 45aecca9 339d8c51 d0ba841a 947285bf d254ad5c`）把 Tesla 的 `car/`、`dbc/`、`dbc/generator/tesla`、`safety/tests/test_tesla.py`、`car_list.json`、`torque_data/substitute.toml` 条目、`values.py` 注册都删了（与 `7b519bc3` 对比实测）；`d0ba841a` 还裁了校验函数，需核对其中是否含 Tesla。恢复时要逐个对应。
- **panda**：lean 的 pin `74a0adce` 比 dev-sp 的基线 `4230530f` **旧 21 个 commit**。dev-sp 的 DOS 补丁 52 个文件里，修改类 20 个：14 个直接可打，**6 个需要手工合并**（`SConscript`、`board/boards/board_declarations.h`、`boards/{cuatro,red,tres}.h`、`board/drivers/drivers.h`、`board/flasher.h`）；其余 32 个是纯新增（`dos.h`、`stm32f4/*`、`bxcan*.h`、`dfu_util_f4.sh`）。
  **不要抬 lean 的 panda pin**——会改动 lean 在 Toyota 上已验证的 safety/协议，且和 lean 的发布产物清单耦合。

### 1.5 lean 的发布流水线对移植的约束（读了 `device_release.sh` / `release_lib.py`）

- `materialize_gitlinks` **硬编码**了 `panda → https://github.com/commaai/panda.git`、`opendbc_repo → https://github.com/lochuan/opendbc.git`，并用 canary 文件校验（`SConscript` / `opendbc/car/car.capnp`）。换 fork 必须改这两行 + `.gitmodules`。
- `ARTIFACT_PATHS` 只登记了 `panda_h7` 的两个固件；pandad 运行时按 `McuType.H7` 读 `board/obj`。DOS 固件（`panda.bin.signed`、`bootstub.panda.bin`）没登记 = 发布树缺固件 = **DOS 进 DFU 后无法恢复**（lean 注释里的原话）。
- 新增的 `legacy_mpc` acados 求解器产物（2 个 model × 6 个 `.so`）、pandad 的 libusb 依赖都要进 `ARTIFACT_PATHS` / `NATIVE_INPUT_PATHS`。
- 模型 pkl 在**设备上**编译，内嵌该设备的相机配置（`modeld/SConscript` 按 `HARDWARE.get_device_type()=="mici"` 选 OS04C10 还是 AR/OX）和 QCOM GPU kernel。**C4 上编出来的 release 不能给 C3/C3X 用**——C3/C3XL 必须在 C3 类设备上用同一脚本另出一个 `RELEASE_BRANCH`（脚本本来就支持这个环境变量）。
- `SKIP_CAPNP_REGEN=1`：设备上不重新生成 cereal，见 0.5。

---

## 2. 范围

### 2.1 移植（按优先级）

| 阶段 | 内容 | 来源（dev-sp 路径） | 备注 |
|---|---|---|---|
| P1 | opendbc：Tesla 车型、DBC、safety、ARS408 雷达、coop steering、速度限制控制器 | `opendbc_repo` @ `3b9bf189` | 先于一切；panda 固件和 python 都吃它 |
| P2 | Tesla 控制：card 适配器、selfdrived 运行时、环境氛围灯（盲区）、速度限制策略、控制配置、参数、cereal 槽位、Tesla 设置页（大屏 + mici） | `sunnypilot/selfdrive/car/tesla/*`、UI、cereal、params | 最小可用闭环 |
| P3 | 纵向后端（Official / Experimental / TN-NoDEC）+ 红绿灯/停止线控制（Tesla 观察器、仲裁器）+ 路口 HUD | `longitudinal_backends/*`、`traffic_control/*` | 依赖 P2 的 cereal；含 acados 求解器编译 |
| P4 | C3 / C3XL：panda DOS 固件、pandad USB 通路、硬件 profile、AGNOS 清单保护、功放/蜂鸣器、供电读数 | `onemiless/panda` 4 commit + `selfdrive/pandad/*` + `sunnypilot/hardware/*` | **独立于 P2/P3，可并行** |
| P5 | BMS 电池面板（被动订阅 CAN） | `bms.py`、`tesla/bms.py` | 挂在 Vehicle→Tesla 下，**不要替换 Trips** |
| P6（可选） | 运行时告警中文化、UI 崩溃自动重启 | `alert_localizer.py` 等 | 先确认 lean 的中文界面/告警本地化现状 |
| P7 | 优化轮（行为不变，回放证明） | 见第 7 节 | 与"移植提交"严格分开 |

### 2.2 明确不移植

- **Chestnut 模型选择 / 道路缩放（`CHESTNUT_ROAD_SIZE`、`ife_scale.h`、`camera.py` 缩放）**：lean 没有 `modeld_v2`，模型管线是 `bigmodeld`，两边不可比。
- **DM 开关（`DriverMonitoringEnabled`、`driver_monitoring.py`、`toggles.py`×2、`selfdrived` DM 分支、`process_config` DM 谓词、`latch_driver_monitoring`）**：lean 的 `selfdrived.py` 里已经完全没有 DM；`launch_env.sh` 里 `DISABLE_DRIVER=1`；`hw.h` 的 `CABIN_CAMERA_CONFIG.enabled = !getenv("DISABLE_DRIVER")` 已经满足 C3XL 无座舱摄像头。
- **`LoggingEnabled` 日志总开关、`restart_if_crash` UI 重启、首页隐藏离线告警、copyparty 移除**：与 Tesla 无关，且改动 manager 热点文件。
- **更新分支策略（`branches.py`、`software.py` 改动）**：lean 有自己的发布/安装渠道（`tp.diaperastiko.top`）。
- **`vision_controller.py` 的 5 帧确认 + `desiredCurvature`**：这是对**所有品牌**生效的行为改动，不是 Tesla 功能。默认不移植；若要，门控到 `CP.brand == "tesla"`。
- **dev-sp 的 `tools/dev_sp_release/*`、模型/字体/分支 e2e**：lean 有 `tools/release/*`。

---

## 3. 低侵入设计

### 3.1 硬性规则（Codex 必须遵守）

1. **新增优先**：所有 Tesla 代码放进只属于 Tesla 的目录，**路径与 dev-sp 完全一致**，这样以后 dev-sp 的修复可以 `git diff devsp/dev-sp -- <路径>` 直接搬：
   - `openpilot/sunnypilot/selfdrive/car/tesla/`
   - `openpilot/sunnypilot/selfdrive/traffic_control/`
   - `openpilot/sunnypilot/selfdrive/controls/lib/longitudinal_backends/`
   - `openpilot/sunnypilot/hardware/`（只保留 profile/agnos/panda/panda_startup/c3xl_probe，删 DM 与 branches）
   - `openpilot/sunnypilot/system/alert_output.py`
   - `openpilot/selfdrive/ui/sunnypilot/{tesla_settings.py, layouts/settings/vehicle/brands/tesla*.py, mici/layouts/tesla.py, onroad/traffic_control.py}`
   - `tools/sp_tesla_e2e/`（仅 Tesla 相关脚本）
2. **接缝 = 一行 import + 一行调用**。上游文件里不写 Tesla 逻辑，只调用 Tesla 命名空间里的函数（dev-sp 已经是这个形态：`TeslaCardAdapter`、`TeslaControlRuntime`、`create_longitudinal_planner`、`create_long_control`、`tesla_initialization_snapshot`）。
3. **接缝登记**：新建 `docs/tesla/SEAMS.md`，每个被修改的上游文件一行：文件、hunk 数、增删行数、作用、dev-sp 来源 commit。以后同步 lean 时只需要看这张表。
4. **改动预算**（评审红线）：主仓 Tesla 核心（P2/P3）被修改的**上游**文件 ≤ 26 个、净增行 ≤ 400（不含 cereal `gen/cpp`）；硬件（P4）另算，≤ 24 个文件、≤ 180 行；opendbc 被修改的共享文件 ≤ 12 个；panda 被修改的既有文件 ≤ 20 个。超预算必须在 PR 里解释。
5. **cereal 只追加**：不改任何已有字段的顺序/类型，只在结构体末尾加字段、在预留槽位里放新结构体。
6. **不抬 lean 的任何 pin**（panda、tinygrad、msgq、rednose）。opendbc/panda 的新分支只在 lean 当前 pin 之上叠 commit。
7. **不重写已被设备引用的分支历史**（和 dev-sp `SYNC_PREPARATION.md` 的规矩一致）：所有 fork 分支用 merge 同步，不 force-push；主仓 gitlink 钉的是 SHA。

### 3.2 仓库与分支模型

```
lochuan/lean-mici  ──fork──▶ <you>/lean-mici
   lean-master (只读镜像，用 GitHub "Sync fork")
   lean-tesla  = lean-master + [tesla] 系列提交       ← 主工作分支
lochuan/opendbc   ──────────▶ onemiless/opendbc  新分支 lean-tesla（起点 7b519bc3）
sunnypilot/panda 74a0adce ──▶ onemiless/panda    新分支 lean-tesla（起点 74a0adce）
onemiless/openpilot dev-sp   只读参考（git remote: devsp）
```

- 每个 commit 前缀 `[tesla/p1]`…`[tesla/p4]`，一个 commit 只做一个接缝或一个新增模块，便于 `git rebase -i` / `git revert`。
- 主仓 `.gitmodules` 改两处：`opendbc_repo.url → onemiless/opendbc`、`panda.url → onemiless/panda`；gitlink 指向各自 `lean-tesla` 分支的提交。
- 主仓与 fork 的同步统一用 **merge**（`git merge lean/lean-master`），开 `git config rerere.enabled true`；lean 上游节奏很快（实测 5 天约 40 个 commit），rebase 补丁队列会反复解同一批冲突。

---

## 4. 分阶段实施

> 每个阶段的验收遵循用户在 dev-sp `AGENTS.md` 里的规矩：**先列失败模式，再做 E2E 验证；不在写完代码后补单元测试；本地 commit 与设备上实际运行的 commit 分开报告**。已有的回放/fixture 随模块一起拷贝并保留。

### P0 准备（1 天）

1. fork `lochuan/lean-mici`；在 `onemiless/opendbc`、`onemiless/panda` 上从 lean 当前 pin 建 `lean-tesla`（从 `lochuan/opendbc`、`sunnypilot/panda` 拉对象即可，三者同属 commaai 网络）。
2. 主仓 `git checkout -b lean-tesla lean/lean-master`；`git remote add devsp https://github.com/onemiless/openpilot.git && git fetch devsp dev-sp`。
3. 写 `docs/tesla/PORT_BASELINE.json`：lean-master SHA、opendbc/panda/msgq/rednose/tinygrad 的 pin、dev-sp SHA、dev-sp 基线 `16322aef`、opendbc `e15d1889..3b9bf189`、panda `eebfc767..ac0f791f`。
4. 把 dev-sp `AGENTS.md` 的工作规矩改成适配新分支（`dev-sp` → `lean-tesla`）后放进仓库根目录。
5. **基线门禁**：未改任何东西时，`lean-master` 在目标设备（C4；以及 C3X/C3XL 若要验证）能启动、`tools/bench/smoke_after_build.sh` 通过、`pytest` 里 lean 自带的测试通过。记录结果；之后任何失败都要能判断是移植引入的还是基线就有。

### P1 opendbc（Stream A，约 2–3 天）

在 `onemiless/opendbc` 的 `lean-tesla` 分支上：

1. **恢复 Tesla 自有路径**（lean 已删，所以从 dev-sp 直接取，无冲突）：
   ```
   git fetch origin dev-sp   # onemiless/opendbc 本身就含 dev-sp 分支，无需额外 remote
   git checkout origin/dev-sp -- \
     opendbc/car/tesla \
     opendbc/sunnypilot/car/tesla \
     opendbc/dbc/tesla_* opendbc/dbc/ARS408.dbc opendbc/dbc/generator/tesla \
     opendbc/safety/modes/tesla.h opendbc/safety/tests/test_tesla.py
   ```
   （`tesla_model3_party_supplement.dbc`、`tesla_modely_hw4_perception.dbc` 已被 `tesla_*` 覆盖；先 `git ls-tree devsp/dev-sp opendbc/dbc` 核对一遍文件名。）
2. **手工合并共享文件**（只应用 Tesla hunk；每个文件对照 `git diff b2acec1d 3b9bf189 -- <file>`）：
   | 文件 | 要做的事 |
   |---|---|
   | `opendbc/car/values.py` | `MOCK | TOYOTA` → `MOCK | TOYOTA | TESLA`（加一行 import） |
   | `opendbc/car/structs.py` | 加 `TeslaRoadContext` 与 `CarStateSP.flags/teslaRoadContext`（必须与 cereal `CarStateSP` 字段顺序一致） |
   | `opendbc/car/torque_data/{params,override,substitute}.toml` | 恢复 Tesla 条目（参考 `a595dced` 删掉的内容） |
   | `opendbc/car/fingerprints.py` / `car_helpers.py` | 若 FW 指纹聚合处只列了 Toyota，加 Tesla |
   | `opendbc/sunnypilot/car/interfaces.py` | 加 `_initialize_coop_steering`、`_initialize_tesla_*`（mads 屏幕键、dynamic_auto_stock、ap_hybrid、auto_speed_limit、radar_backend）及 `ars408.constants` import；**不要**把 Hyundai/Subaru 等 import 带回来 |
   | `opendbc/sunnypilot/car/{car_list.json,platform_list.py,fingerprints_ext.py}` | 恢复 Tesla 条目 |
   | `opendbc/can/*`、`opendbc/dbc/generator/generator.py` | 若 lean 在 `d0ba841a`/`2622fb1b` 里删了 Tesla 校验/schema，只恢复这部分 |
   | `opendbc/safety/safety.h` | `rx_observer` 调用（+4 行） |
   | `opendbc/safety/declarations.h` | `rx_hook rx_observer;`（+2 行） |
   | `opendbc/safety/modes/defaults.h` | 空输出模式下的"氛围灯固定红色 0x679"白名单（+76/-7，**安全相关，见 9.Q5**） |
   | `opendbc/safety/tests/libsafety/safety.c`、`tests/test_defaults.py` | 随 safety 改动同步 |
   | `docs/CARS.md`（`opendbc/car/docs`） | 重新生成 |
3. 确认 Tesla 的 `car/tesla/*` 对 lean 比 `b2acec1d` 旧 10 个 commit 的共享基础设施（`opendbc.car.interfaces`、`lateral.py`、`Bus`、`structs`）没有隐含依赖；有就最小补齐。

**验收（失败模式先行）**

- F1.1 `PLATFORMS` 没带 Tesla → CarParams 回落 mock。→ 用 dev-sp 的 Tesla 路由/FW 指纹各跑一遍 `car_helpers.interfaces`，必须选出 `TESLA_MODEL_3/Y`。
- F1.2 safety 与 python 不一致。→ `opendbc/safety/tests` 里 Tesla 全量测试 + `test_defaults.py` 通过，且 **Toyota 的 safety 测试结果不变**（回归）。
- F1.3 `CarStateSP` python/capnp 字段错位。→ 往返序列化测试。
- F1.4 `no-output` 模式放宽导致非 Tesla 车辆行为变化。→ 用 `libsafety` 对 Toyota 在 `SAFETY_NOOUTPUT` 下发 `0x679` 必须被拒。
- 命令：`cd opendbc_repo && ./test.sh`（以仓库实际脚本为准）+ `pytest opendbc/car/tesla opendbc/sunnypilot/car/tesla opendbc/safety/tests/test_tesla.py`。

### P2 Tesla 控制（Stream C，约 3–4 天，依赖 P1 才能跑全量测试）

**2.1 cereal（先做，别的都依赖它）**

- `openpilot/cereal/custom.capnp`：
  - `LongitudinalPlanSP` 末尾加 `accelController @8 :AccelController; teslaTrafficControl @9 :TeslaTrafficControlPlan;` 及两个子结构体（dev-sp 原文，**保持字段序号完全一致**）。
  - `CarStateSP` 加 `flags @1`、`teslaRoadContext @2`、`teslaTrafficControl @3` 及 `TeslaRoadContext`、`TeslaTrafficControl`。
  - 新增 `TrafficRadarState` 结构体，**放在 `CustomReserved11 @0xc2243c65e0340384` 的位置**（把预留结构体改名并填字段，结构体 ID 用 `0xc2243c65e0340384`，不是 dev-sp 的 `0xcb9fd56c7057593a`——后者在 lean 里是 `BigModelReply`）。
- `openpilot/cereal/log.capnp`：`customReserved11 @137 :Custom.CustomReserved11` → `trafficRadarState @137 :Custom.TrafficRadarState`。**绝对不要动 `@136 bigModelReply`。**
- `openpilot/cereal/services.py`：加 `"trafficRadarState": (True, 20., 5, QueueSize.SMALL)`。
- **跳过** dev-sp 对 `cereal/SConscript` 的改动（`CAPNP_BIN_DIR`，那是另一套 capnp 打包，lean 不需要）。
- 运行 `tools/release/regen_cereal_gen.sh`，把 `openpilot/cereal/gen/cpp/*` 的变更与 `.capnp` **放在同一个 commit**。
- 副作用要写进 PR：设备端需要**一次全量重建**（lean 历史上同类 commit 都这么写）。
- 已知限制：dev-sp 录的 rlog 里 `trafficRadarState` 在 `@136`，到 lean 会被当成 `bigModelReply`；做回放验证时要过滤该事件。

**2.2 参数** `openpilot/common/params_keys.h`：在文件末尾新增一个独立块 `// --- tesla fork params ---`，只放 Tesla/纵向相关键（`TeslaBlindspotAmbient*`、`TeslaARS408Radar`、`TeslaTouchLongitudinalSwitch`、`TeslaApHybrid`、`TeslaDynamicApLongitudinal`、`DynamicAutoStock*`、`LongitudinalPlannerMode`、`ActiveLongitudinalBackend`、`LongitudinalTuningConfig`、`AccelPersonality*`、`Mpc*`×12、`TeslaTraffic*`、`SpeedLimitOffsetMaxSpeed`）。**不要带** `DriverMonitoringEnabled`、`ActiveDriverMonitoringEnabled`、`LoggingEnabled`。`TeslaCoopSteering`、`TeslaMadsScreenButton` 在 lean 里还在，不要重复。

**2.3 openpilot 侧接缝**

| 文件 | 改动（≈行数） | 备注 |
|---|---|---|
| `selfdrive/car/card.py` | +19/-6 | `TeslaCardAdapter`；`carStateSP` 要在 `carState` **之前**发布（原子性所需，别"优化"回去） |
| `selfdrive/selfdrived/selfdrived.py` | ~14 | 只取 Tesla hunk：`TeslaControlRuntime`、`carStateSP` conflate socket、`filter_transition_events`、`commit_cycle`；**不取** DM 的三处 |
| `sunnypilot/selfdrive/car/interfaces.py` | ~6 | `initialize_params` 末尾追加 `tesla_initialization_snapshot(params)` |
| `sunnypilot/selfdrive/controls/lib/speed_limit/{__init__,speed_limit_assist,speed_limit_resolver}.py` | ~35 | `resolve_pcm_long_required_max`、`SpeedLimitOffsetMaxSpeed` |
| `sunnypilot/selfdrive/selfdrived/events.py` | ~10 | 只取 `resolve_pcm_long_required_max` 那一处；C3XL 蜂鸣器那处放 P4 |
| `system/manager/process_config.py` | ~3 | 只加 `trafficcontrold`（P3）；放在 lean 已有的 `# sunnypilot` 块里 |
| `selfdrive/ui/sunnypilot/layouts/settings/vehicle/brands/factory.py` | +2 | `"tesla": TeslaSettings` |
| `selfdrive/ui/sunnypilot/mici/layouts/settings.py` | ~5 | Tesla 页入口；注意 lean 新增了 `mici/layouts/{bigmodel,lanlink}.py`，核对设置页里 `items.insert` 的下标不冲突 |

**2.4 新增**：`sunnypilot/selfdrive/car/tesla/*`（7 个）、`tesla_settings.py`、`brands/tesla*.py`、`mici/layouts/tesla.py`。`trf()` 是 dev-sp 加在 `multilang.py` 里的，**不要改 `multilang.py`**——在 `tesla_settings.py` 里本地定义 `def trf(t, *a, **k): return tr(t).format(*a, **k)`，`tesla.py` 从那里 import。

**验收**

- F2.1 cereal 过期生成物：`regen_cereal_gen.sh` 之后 `git diff --exit-code openpilot/cereal/gen`；Python/C++ 各自订阅 `trafficRadarState`、`carStateSP.flags` 读写一遍。
- F2.2 非 Tesla 车被影响：Toyota 的 `card`/`selfdrived` 回放前后 `carControl`、`selfdriveState` 逐字节相同（process_replay）。
- F2.3 Tesla 所有权解析错位（FAULT 否决、AP hybrid 交接）：搬 `tools/sp_tesla_e2e/tesla_control_chain_e2e.py`、`ambient_safety.py`（需要 `libsafety`），先把脚本里写死的 `/Users/mile/...` 路径改成仓库相对路径。
- F2.4 参数在 `Params` 与 `CP_SP.flags` 间不一致：`tesla_settings_e2e.py`。
- F2.5 C4 上设置页不可达：`ui_smoke`（离线，无车）+ 真机点一遍；核对 mici 页的入口下标与 lean 的 `bigmodel`、`lanlink` 页不冲突。
- 车辆级验收（实车/台架）是**独立门禁**，不能用上述结果替代。

### P3 纵向后端 + 红绿灯（约 4–5 天，依赖 P2）

1. 原样拷贝 `longitudinal_backends/*`（含 `legacy_mpc/SConscript`、`tn_no_dec/*`、`tuning.py`、`registry.py`、`session.py`）、`traffic_control/*`（含测试与 fixtures）、`controls/tests/*`、`ui/sunnypilot/onroad/traffic_control.py`。
2. 接缝：
   | 文件 | 改动 |
   |---|---|
   | `selfdrive/controls/controlsd.py` | 2 行：`create_long_control(self.CP, self.CP_SP)` 替换 `LongControl(...)` |
   | `selfdrive/controls/plannerd.py` | ~12 行：`create_longitudinal_planner`、`create_final_plan_arbitrator`、订阅 `trafficRadarState`、`ignore_services` |
   | `selfdrive/controls/lib/longcontrol.py` | ~8 行：`stopping_policy` 钩子 |
   | `sunnypilot/selfdrive/controls/lib/longitudinal_planner.py` | ~15 行：`enable_dec`、`_update_backend`、`_publish_backend_state` |
   | `selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py` | ~24 行：运行期调参钩子（**可选，见 9.Q3**；不要它就没有 Official 档的 `Mpc*` 调参） |
   | `system/manager/manager.py` | 2 行：`end_longitudinal_session(...)`（先停 plannerd/controlsd 再清 session，**不取** `latch_driver_monitoring`） |
   | `system/manager/process_config.py` | `PythonProcess("trafficcontrold", ..., only_onroad)` |
   | `sunnypilot/SConscript` | +1：`SConscript(['selfdrive/controls/lib/longitudinal_backends/legacy_mpc/SConscript'])` |
   | `selfdrive/ui/sunnypilot/onroad/hud_renderer.py`、`mici/onroad/hud_renderer.py` | 各 +4 |
3. **发布流水线**（见第 6 节）：`ARTIFACT_PATHS` 增加两套求解器（`c_generated_code`、`c_generated_code_fallback`）各 6 个文件；`NATIVE_INPUT_PATHS` 增加 `legacy_mpc` 目录。
4. **UI 布局冲突检查（C4）**：lean 把 `NPU_GREEN` 图标放在右下角、方向盘在左下角、左上角是定速显示。`TrafficControlRenderer(compact=True)` 在 mici 上的位置要避开这三处和 Reverse Gear 告警。

**验收**

- F3.1 acados 求解器 ABI/常量漂移：dev-sp 的 `test_legacy_mpc.py`、`test_legacy_planner_replay.py` + 三个 fixtures（`tesla_legacy_{experimental,tn,linux_aarch64}.json`）。**在设备上也要跑一遍**（fixtures 里有 `linux_aarch64` 一份，Darwin 构建不等于设备构建）。
- F3.2 红绿灯：Off 时不得改变基础计划；红灯 stop 事件连续；陈旧绿灯不得起步；`forceDecel`/未知 `controlsState` 时不放行。→ `traffic_control/tests/*`（`test_final_plan_arbitrator.py` 2269 行等）+ `tools/sp_tesla_e2e/traffic_override_e2e.py`、`tesla_planner_chain_e2e.py`。
- F3.3 与 bigmodeld 的交互：大模型 ↔ 小模型回落期间 `modelV2` 字段连续性；TN 档用 `modelV2` 的哪些字段要列清单并回放（正常 / 回落 / `SEQ_RESET`）。
- F3.4 Toyota 路径零变化：`LongitudinalPlannerMode` 默认值下，Toyota 的 `longitudinalPlan` 回放与基线逐字节一致。
- F3.5 live 切换模式导致 plannerd/controlsd 分裂：dev-sp 的"原子锁存 + manager 先停后清"必须保留，不能为了省行数去掉。

### P4 C3 / C3XL 硬件与 panda（Stream B，可与 P1–P3 并行，约 4–6 天）

**4.1 panda（`onemiless/panda` `lean-tesla`）**

1. 从 `onemiless/panda` 取 dev-sp 的 4 个 commit：`eebfc767 0f41a1f5 ce77749f ac0f791f`，`git cherry-pick` 到 `74a0adce` 之上。
2. 预计冲突的 6 个文件手工合并：`SConscript`、`board/boards/board_declarations.h`、`board/boards/{cuatro,red,tres}.h`、`board/drivers/drivers.h`、`board/flasher.h`。
   dev-sp 给每个板子加了 `fan_stall_recovery` 字段，它**可能**依赖 dev-sp 基线里比 lean 新的上游 commit——先判断 DOS 是否真需要这个字段，不需要就不带。
3. 其余按"纯新增"处理：`board/boards/dos.h`、`board/stm32f4/*`（含 `stm32f413xx.h` 15k 行）、`board/drivers/bxcan*.h`、`board/debug/dfu_util_f4.sh`。`python/{__init__,constants,dfu}.py` 的 F4 支持可直接打。
4. 固件门禁：用 lean 的 opendbc pin（含 Tesla safety）完整构建 `panda`（F4）与 `panda_h7`，检查 **F4 镜像是否仍然装得下**（加了 Tesla safety + `rx_observer` 之后的 flash/RAM 占用）；CAN 缓冲在 F4 上被缩小到 1024/128，Tesla 的 TX 帧长都 ≤ 8，OK，但要在台架上确认没有溢出计数。

**4.2 pandad（主仓接缝，几乎都能干净套用）**

- 新增 `openpilot/selfdrive/pandad/usb.cc`（245 行，libusb 通路）；修改 `panda.cc`（USB 优先、SPI 回退；C3 上只枚举 USB）、`panda.h`、`panda_comms.h`（`PandaCommsHandle` 基类）、`pandad.h`（`DOS` 加入受支持类型）、`pandad.py`（`InternalPanda`、`PandaStartup`、`get_mcu_type()`）、`SConscript`（`usb-1.0`）。
- `SConstruct`：`pkg_names` 加 `'libusb'`。**依赖已满足**：lean 的 `pyproject.toml` 已有 `comma-deps-libusb`，`uv.lock` 有 `libusb1`。**已决议（D4）**：不加编译期 `CPPDEFINES`，`profile.h` 改为运行时读 `/data/hardware_profile`，C3 与 C3XL 共用一个发布分支。
- 新增 `openpilot/sunnypilot/hardware/{profile.py,profile.h,agnos.py,panda.py,panda_startup.py,c3xl_probe.py,__init__.py}` 与其测试。**删掉 `driver_monitoring.py`、`branches.py`**。
- `hardware.h`：`tici` 加回 `device_map`；C3XL 报告为 `TIZI`。`hardware.py`：`amplifier` 对 C3XL 返回 `None`。
- `hardwared.py`：(a) "非 tici 通道禁止行车"的门控改为按 profile 放行（`get_hardware_profile() in (C3, C3XL)`），不依赖分支名；(b) DOS 用主机电压（`HARDWARE.get_voltage()`），因为 DOS 的 ADC 和 SOM GPIO 共线。`power_monitoring.py`：忽略非正电压。
- 蜂鸣器：`sunnypilot/system/alert_output.py` + `process_config` 里一个只在 C3XL 起的进程 + `events.py` 里 `big_model_ready_alert`（lean 有 `bigModelReady` 事件，补丁可套）。

**4.3 AGNOS 启动链（已决议 D2/D5，详见任务清单 T4.8）**：C3 与 C3XL 的 `xbl/xbl_config/abl/aop/devcfg/boot` 取 dev-sp 现有值（C3=dev-sp `agnos.json`，C3XL=dev-sp `agnos-c3xl.json`），`system` 取 lean 的 19.6.27（按 C4 升级）；C4/C3X 的 `agnos.json` 不动。注意：dev-sp 标准清单的 `abl`（`29fd7ed1…`）与 lean 的 C4 `abl` 是同一个哈希，只有 `boot` 不同；C3XL 的 `abl`/`boot` 都不同。`tici` 设备树 C3 与 C3XL 同名，所以 `/data/hardware_profile` 必须明确写 `c3` 或 `c3xl`，缺失则**跳过 AGNOS 更新**。清单生成、白名单校验、启动脚本选择的具体做法见任务清单 T4.8。

**4.4 C3 的相机（已决议 D1）**：dev-sp 和 lean 的 `camerad` 都只有 OX03C10 / OS04C10 驱动，没有 AR0231，dev-sp 文档里 C3 运行时也是 OX03C10 路相机。做法：camerad 零改动，不移植 Chestnut 缩放；设备上用 `tools/tesla/camera_check.py` 验证路相机枚举为 `ox03c10`，不是则停止汇报。

**验收**

- F4.1 C3 USB panda 与内置/外置 panda 选错：dev-sp 的 `test_panda_startup.py` + 台架上 SPI 内置 + USB 外置同时存在的枚举测试（只传一个已校验的序列号给 `./pandad`）。
- F4.2 DOS 固件签名/大小：`panda.bin.signed`、`bootstub.panda.bin` 进 `ARTIFACT_PATHS`，`release_lib` 的 ELF/大小检查要放行"裸机 `.bin`"。
- F4.3 C3XL 被误判为标准或反之（丢功放/麦克风/刷错启动链）：`test_profile.py`、`test_agnos.py`；`/data/hardware_profile` 是唯一权威，**不要**根据设备树名推断。
- F4.4 H7（C4/C3X）回归：同一个 pandad 二进制在 C4 上 SPI 启动正常，`smoke_after_build.sh` 通过。
- F4.5 `tools/bench/jungle_replay.sh` 在 C3/C3XL 台架上：Toyota（Sienna 循环）核心进程 onroad 稳定；再加一个 **Tesla CAN 回放**（见 6.3）。
- 物理验收（安装、点火、实车）是独立门禁，源码/构建通过不代表通过。

### P5 BMS（约 1 天）

拷贝 `selfdrive/ui/sunnypilot/layouts/settings/bms.py`、`tesla/bms.py`、`docs/tesla_bms_dashboard.md`。**不替换 Trips**（lean 本来就没有 Trips 面板，也别去改 `settings.py` 的面板表）：从 `TeslaSettings` 里加一个入口按钮推入 BMS 页。要求：只在页面可见且 `CarParams` 已知是 Tesla 时才订阅 `can`，换车清数据，被动只读、绝不发送。

### P6 可选：告警中文化 / UI 重启

先确认 lean 的界面与 `alert_renderer` 是否已有中文/本地化。若没有再移植 `alert_localizer.py` + `font_characters.py`（改动落在 `alert_renderer.py`×2、`application.py`、`multilang.py`、字体 otf，都是热点文件，成本高）。

---

## 5. 接缝总表（主仓上游文件）

| 文件 | 阶段 | 增/删 | 冲突风险 |
|---|---|---|---|
| `openpilot/cereal/custom.capnp` | P2 | +~135 | **高**（槽位） |
| `openpilot/cereal/log.capnp` | P2 | 1 行 | **高**（`@137`） |
| `openpilot/cereal/services.py` | P2 | +1 | 低 |
| `openpilot/cereal/gen/cpp/*` | P2 | 生成 | 必须用脚本重生 |
| `openpilot/common/params_keys.h` | P2 | +~40（末尾独立块） | 中 |
| `openpilot/selfdrive/car/card.py` | P2 | +19/-6 | 低（已验证可套） |
| `openpilot/selfdrive/selfdrived/selfdrived.py` | P2 | ~14 | 中（lean 已删 DM，行号漂移） |
| `openpilot/sunnypilot/selfdrive/car/interfaces.py` | P2 | ~6 | 低 |
| `…/speed_limit/{__init__,assist,resolver}.py` | P2 | ~35 | 低 |
| `openpilot/sunnypilot/selfdrive/selfdrived/events.py` | P2(+P4) | ~10 | 低 |
| `openpilot/system/manager/{process_config,manager}.py` | P2/P3 | ~6 | 中 |
| `…/vehicle/brands/factory.py` | P2 | +2 | 低 |
| `…/sunnypilot/mici/layouts/settings.py` | P2 | ~5 | 中 |
| `selfdrive/controls/{controlsd,plannerd}.py`、`lib/longcontrol.py`、`lib/longitudinal_mpc_lib/long_mpc.py` | P3 | ~46 | 低（已验证可套） |
| `…/lib/longitudinal_planner.py`（sunnypilot） | P3 | ~15 | 低 |
| `…/onroad/hud_renderer.py`×2 | P3 | +8 | 中（mici 版冲突过） |
| `openpilot/sunnypilot/SConscript` | P3 | +1 | 低 |
| `SConstruct` | P4 | ~7 | 低 |
| `launch_env.sh`、`launch_chffrplus.sh` | P4 | ~14 | **中**（lean 有 AGNOS 版本锁） |
| `common/hardware/comma/{agnos.py,hardware.h,hardware.py}` | P4 | ~20 | 低 |
| `selfdrive/pandad/{panda.cc,panda.h,panda_comms.h,pandad.h,pandad.py,SConscript}` + 新增 `usb.cc` | P4 | ~100 | 低（已验证可套） |
| `system/hardware/{hardwared,power_monitoring}.py`、`system/updated/updated.py` | P4 | ~12 | 低 |
| `.gitmodules` | P0 | 2 | — |
| `tools/release/{device_release.sh,release_lib.py,test_release_lib.py}` | P3/P4 | ~30 | 中 |

超出此表的上游文件改动，一律视为越界。

---

## 6. 与 lean 发布流水线的对接

### 6.1 必改项

1. `tools/release/device_release.sh` 的 `materialize_gitlinks`：`panda` 的 URL 改为 `https://github.com/onemiless/panda.git`，`opendbc_repo` 改为 `https://github.com/onemiless/opendbc.git`；canary 再各加一个 Tesla/DOS 特征文件（`opendbc/car/tesla/carcontroller.py`、`board/boards/dos.h`）——这是 lean 为"旧 opendbc 被当新的发出去"事故（commit `663f1284`）加的防线，别绕过。
2. `tools/release/release_lib.py`：
   - `ARTIFACT_PATHS` 增加 `panda/board/obj/bootstub.panda.bin`、`panda/board/obj/panda.bin.signed`；`legacy_mpc/c_generated_code/*` 与 `c_generated_code_fallback/*` 各 6 个文件（`acados_ocp_solver_pyx.so`、`libacados.so`、`libacados_ocp_solver_sp_legacy_cruise_v1[_fallback].so`、`libblasfeo.so`、`libhpipm.so`、`libqpOASES_e.so.3.1`）。
   - `NATIVE_INPUT_PATHS` 增加 `legacy_mpc` 目录与 `openpilot/sunnypilot/hardware`。
   - 同步更新 `tools/release/test_release_lib.py`。
3. `.gitmodules` 两处 URL。

### 6.2 设备分档发布

- C4：沿用 `lean-release` 流程，`SRC_BRANCH=lean-tesla RELEASE_BRANCH=lean-tesla-release`。
- C3 / C3XL：**必须在 C3 类设备上**跑同一脚本，`RELEASE_BRANCH=lean-tesla-release-c3`（C3 与 C3XL 共用，D4）。原因：pkl 内嵌设备相机配置与 QCOM kernel（见 1.5）。
- 安装器 `setup.py/tici_setup.py/mici_setup.py` 指向的是 lean 作者的域名；新分支的默认安装地址是用户自己要决定的事（9.Q1），本方案不替用户改。

### 6.3 台架

`tools/bench/jungle_replay.sh` 目前只有 `sienna_can_loop.xz`。建议新增 `tesla_can_loop.xz`（用 dev-sp 的 Tesla 路由生成点火循环），并让 `smoke_after_build.sh` 能按 `CAR=tesla|toyota` 选择。这样发布末尾的冒烟能覆盖 Tesla。

---

## 7. 优化项（P7，行为不变，单独提交，附回放证据）

用户要求"移植过程中优化 Tesla 代码"。为了不把"移植"与"改行为"搅在一起，约定：**先做到与 dev-sp 回放一致（P2–P4 的验收），再在独立 commit 里优化**。候选项（均来自对源码的实际阅读）：

1. **解耦 Tesla 与非 Tesla 的 dev-sp 特性**：Tesla 模块里只有 `alert_output.py` 与 `hardware/*` 依赖 `HardwareProfile`，其余不依赖；移植时保证 `car/tesla/*`、`traffic_control/*`、`longitudinal_backends/*` 对 `sunnypilot.hardware` **零 import**（用 `grep` 做成检查）。
2. **接缝瘦身**：`speed_limit/__init__.py` 里的 `resolve_pcm_long_required_max(...brand=)` 现在在通用函数里分支品牌；可改成"Tesla 注册覆盖函数"，通用文件只留一个 `_OVERRIDES` 字典读取。
3. **BMS 入口**：改为挂在 Tesla 设置页里，不占用顶层面板（已纳入 P5）。
4. **去掉墓碑**：`TeslaRoadContext`（已退役的可视化）、`AccelController.shadowOnlyDEPRECATED`、`TrafficRadarState.suppressedByPhysicalLead`（deprecated）、已退役的 TX 兼容位（`TURN_SIGNAL_VALIDATION`、`SPEED_BUTTON_VALIDATION`）。**注意**：删字段会改变序号、使 dev-sp 的 rlog 无法回放，所以放在最后，并且在 `docs/tesla/SEAMS.md` 记录。
5. **E2E 脚本可移植**：`tools/sp_tesla_e2e/*` 里硬编码 `/Users/mile/...`，改成相对路径/环境变量，能在 Linux 与 macOS 下同样运行。
6. **`long_mpc.py` 运行期调参钩子（24 行）**：如果 9.Q3 选"保留"，评估能否改为在 `create_longitudinal_planner` 里用子类替换 `planner.mpc`，从而让上游 `long_mpc.py` 零改动。
7. **`traffic_control/controller.py`（927 行）与 `final_plan_arbitrator.py`（938 行）**：体量大，先原样搬；等回放基线稳定后，再看是否能按职责拆分——这是后续收益项，不属于本次移植。

---

## 8. 同步策略（以后怎么跟上游）

1. **跟 lean-master**：`git fetch lean && git merge lean/lean-master`，`rerere` 开启。冲突几乎只会出现在第 5 节的"中/高"风险文件。每次合并后跑 `docs/tesla/check_seams.sh`（一个很短的脚本：对第 5 节的文件逐个检查接缝标记仍在、`git diff --stat lean/lean-master -- <上游文件>` 不超预算）。
2. **跟 dev-sp**：Tesla 自有路径与 dev-sp 同名，用 `git diff <PORT_BASELINE 里的 dev-sp SHA>..devsp/dev-sp -- <路径>` 取增量，`git apply --3way`。每次同步后更新 `docs/tesla/PORT_BASELINE.json`。
3. **opendbc / panda**：fork 分支定期 `git merge lochuan/opendbc master`（opendbc）和 `sunnypilot/panda master`（panda，**但不要抬主仓的 gitlink**，除非 lean 自己抬了）。主仓 gitlink 永远指向 `lean-tesla` 分支上已推送的具体 SHA，并在推送主仓之前确认子模块提交已在远端可见（`git ls-remote`）。
4. **LFS**：lean 有 `.lfsconfig-comma`；dev-sp 的 `.lfsconfig` 改动**不要带**。本方案不新增任何 LFS 对象。

---

## 9. 风险与待用户决定的问题

**问题（每个都给了默认值，Codex 可按默认值推进，用户随时改）**

- **Q1（已定）** C3 相机：零改动 + 设备端 `ox03c10` 验证。仍待你定：新 fork 的所有者/仓库名（默认 `onemiless/lean-mici`、`onemiless/opendbc@lean-tesla`、`onemiless/panda@lean-tesla`）；新分支的安装器默认地址指向哪里。
- **Q2（已定）** C3/C3XL 的 abl/boot 用 dev-sp 现有值，system 按 C4 升级。残余风险：dev-sp 的 boot（内核）+ lean 的 system（rootfs）是未经验证的组合，任务清单 T4.9 做离线预检、T6.2 只在备机上刷，且更新只写非当前槽，可换槽回退。
- **Q3（已定）** 三套纵向全部保留，Official 的 `Mpc*` 调参钩子（`long_mpc.py` 24 行）保留；设计与理由见任务清单 P3。
- **Q4 ARS408 外接雷达**：默认移植（它在 opendbc 的 Tesla 包里，拆开反而是侵入）。
- **Q5 空输出模式氛围灯白名单**（`defaults.h` +76/-7，让 `SAFETY_NOOUTPUT` 在 param=1 时允许发 `0x679`）：这是**安全代码的放宽**，且 lean 是 Toyota 为主。默认移植并隔离（只在 param==1 生效，附 Toyota 回归测试）；若你不使用盲区氛围灯，可以整块不移植——这是最干净的做法。
- **Q6 BMS**：默认挂在 Tesla 设置页下，不替换任何顶层面板。
- **Q7 P6 中文化**：默认不做，先确认 lean 现状。

**主要风险**

| # | 风险 | 缓解 |
|---|---|---|
| R1 | cereal 槽位冲突/生成物过期 | 2.1 的规则；`regen_cereal_gen.sh` + `git diff --exit-code`；PR 写明设备全量重建 |
| R2 | opendbc 基线漂移（lean 缺 10 个上游 commit） | 以 dev-sp 的 Tesla 文件为准；safety 全量测试；Toyota 回归不变 |
| R3 | panda 基线比 dev-sp 旧 21 个 commit | 6 个文件手工合并；F4 镜像大小/RAM 门禁；不抬 lean pin |
| R4 | lean 发布脚本硬编码 URL/产物清单 | 第 6 节必改项；漏改的症状是"发布树缺固件/旧 opendbc" |
| R5 | C4 编出的 release 误发给 C3 | 按设备分档的 `RELEASE_BRANCH`；`release_lib` 检查里加设备类型断言 |
| R6 | AGNOS 刷错启动链（变砖） | Q2；保留 `validate_agnos_manifest` 白名单 |
| R7 | bigmodeld 与 Tesla TN 规划器的 `modelV2` 连续性 | F3.3 回放，含回落与 `SEQ_RESET` |
| R8 | lean 上游更新频繁 | merge + rerere + 接缝表 + 预算红线 |
| R9 | mici HUD 元素重叠（NPU_GREEN、定速、方向盘、告警） | P3 的 UI 检查；真机截图 |
| R10 | 把 dev-sp 的"通用行为改动"（5 帧确认等）带进 Toyota | 2.2 节明确不移植；回放对比 |

---

## 10. 给 Codex 的执行规约

1. 每开始一个阶段先核对：当前仓库、分支、HEAD、是否有未提交文件；不要动不相关的工作区。
2. 一个 commit 一件事，前缀 `[tesla/pN]`；只提交该变更涉及的文件；撤销用 `git revert`。**禁止 force-push**，**禁止改 `lean-master`、`lean-release`、`dev-sp` 任何分支**。
3. 先写"这一步会怎么失败"（本文件各阶段的 F 条目是起点），再做 E2E 验证；有可重复的命令与产物（JSON/日志）；**不要写完代码再补单元测试**。已有 fixtures 与回放随模块拷贝并保留。
4. 报告里把"本地 commit"和"设备上实际运行的 commit"分开写；回放通过 ≠ 已部署；源码/构建通过 ≠ 硬件/实车通过。
5. 接缝改动前先在 `docs/tesla/SEAMS.md` 登记；超出第 3.1 节预算要停下来问。
6. 不要运行任何会向车辆发 CAN、刷写 panda/AGNOS 的命令，除非用户明确授权且设备处于离线（熄火、无控制）状态。
7. 命令速查见附录 B；映射表见附录 A。

---

## 附录 A：dev-sp 文件 → 动作

**COPY（原样拷贝）**
- `openpilot/sunnypilot/selfdrive/car/tesla/*`（7）
- `openpilot/sunnypilot/selfdrive/traffic_control/*`（含 tests、fixtures）
- `openpilot/sunnypilot/selfdrive/controls/lib/longitudinal_backends/*`（含 `legacy_mpc/SConscript`、`.gitignore`）
- `openpilot/sunnypilot/selfdrive/controls/tests/{test_legacy_mpc,test_legacy_planner_replay,test_longitudinal_backend_seam,test_longitudinal_tuning}.py` 与 `fixtures/*`
- `openpilot/selfdrive/ui/sunnypilot/{tesla_settings.py, layouts/settings/vehicle/brands/tesla.py, tesla_control.py, tesla_planner.py, mici/layouts/tesla.py, onroad/traffic_control.py, layouts/settings/bms.py}`（`tesla.py` 要去掉对 `multilang.trf` 的 import）
- `openpilot/sunnypilot/hardware/{__init__,profile,agnos,panda,panda_startup,c3xl_probe}.py`、`profile.h`、`tests/*`
- `openpilot/sunnypilot/system/alert_output.py`
- `openpilot/selfdrive/pandad/usb.cc`
- `tools/sp_tesla_e2e/{tesla_control_chain_e2e,tesla_planner_chain_e2e,tesla_settings_e2e,tesla_display_e2e,traffic_override_e2e,ambient_safety}.py`
- `docs/tesla_bms_dashboard.md`；`docs/sp-tesla-migration/{TESLA_*.md,TN_HIGHWAY_COMFORT_REPLAY.md}` → 放到 `docs/tesla/ref/`

**SEAM（只应用 Tesla hunk，见第 5 节）**
`cereal/{custom.capnp,log.capnp,services.py}`、`params_keys.h`、`card.py`、`selfdrived.py`、`sunnypilot/selfdrive/car/interfaces.py`、`speed_limit/*`、`events.py`、`manager.py`、`process_config.py`、`controlsd.py`、`plannerd.py`、`longcontrol.py`、`long_mpc.py`、`longitudinal_planner.py`、`hud_renderer.py`×2、`mici/layouts/settings.py`、`SConscript`(sunnypilot)、`SConstruct`、`launch_env.sh`、`launch_chffrplus.sh`、`agnos.py`、`hardware.h`、`hardware.py`、`hardwared.py`、`power_monitoring.py`、`updated.py`、`pandad/{panda.cc,panda.h,panda_comms.h,pandad.h,pandad.py,SConscript}`

**ADAPT**
`.gitmodules`（URL）、`agnos-c3xl.json`（见 4.3）、`AGENTS.md`（分支名）

**SKIP**
`modeld/*`、`modeld_v2/*`、`models/helpers.py`、`chestnut/*`、`camerad/*`、`camera.py`（缩放）、`ui_state.py`×2、`toggles.py`×2、`home.py`、`developer.py`、`software.py`、`settings.py`、`vision_controller.py`、`process.py`、`manager/helpers.py`、`cereal/SConscript`、`NotoSansCJK` 字体、`.lfsconfig`、`.github/*`、`tools/dev_sp_release/*`、非 Tesla 的 e2e、`docs/sp-tesla-migration/{FONT,MODEL,RELEASE,BRANCH,SYNC}*`

**OPTIONAL（P6）**
`alert_localizer.py`、`font_characters.py`、`alert_renderer.py`×2、`application.py`、`multilang.py`

## 附录 B：命令速查

```bash
# ---- 主仓 ----
git clone git@github.com:<you>/lean-mici.git && cd lean-mici
git remote add lean  https://github.com/lochuan/lean-mici.git
git remote add devsp https://github.com/onemiless/openpilot.git
git fetch lean lean-master && git fetch devsp dev-sp
git config rerere.enabled true
git checkout -b lean-tesla lean/lean-master          # 4802cb2f

# 取 dev-sp 某些路径相对其基线的 Tesla 改动并三方套用（以接缝为单位，不要整体 apply）
git diff 16322aef167fe14de8af28a9e437101ed3c4dac5 devsp/dev-sp -- openpilot/selfdrive/car/card.py | git apply --3way

# 纯新增目录直接检出
git checkout devsp/dev-sp -- \
  openpilot/sunnypilot/selfdrive/car/tesla \
  openpilot/sunnypilot/selfdrive/traffic_control \
  openpilot/sunnypilot/selfdrive/controls/lib/longitudinal_backends

# cereal 改完必须重生
bash tools/release/regen_cereal_gen.sh && git diff --stat openpilot/cereal/gen

# ---- opendbc ----
git clone git@github.com:onemiless/opendbc.git && cd opendbc
git remote add lochuan https://github.com/lochuan/opendbc.git && git fetch lochuan
git checkout -b lean-tesla 7b519bc3                  # lean 当前 pin
git fetch origin dev-sp                              # 之后用 origin/dev-sp 取 Tesla 路径，按 P1 步骤 1/2

# ---- panda ----
git clone git@github.com:onemiless/panda.git && cd panda
git remote add sp https://github.com/sunnypilot/panda.git && git fetch sp
git checkout -b lean-tesla 74a0adced421e8b7acd728d0f9988ce225423f13
git cherry-pick eebfc767 0f41a1f5 ce77749f ac0f791f  # 预期 6 个文件冲突，见 P4.1

# ---- 回写 gitlink ----
cd ../lean-mici
git -C opendbc_repo fetch && git -C opendbc_repo checkout <lean-tesla 上已推送的 SHA>
git add opendbc_repo panda .gitmodules
```

## 附录 C：本次调研用到的基线 SHA

| 项 | SHA |
|---|---|
| lean-master | `4802cb2fe8c993fd7852b1f78be5b8b9604dd5a5`（2026-10-09） |
| lean-release | `0ee12bb8c0a2c49b74840d56fb189f9bf48303a2`（单孤儿 commit，勿作基线） |
| lean opendbc pin | `7b519bc3`（lochuan/opendbc master） |
| lean panda pin | `74a0adced421e8b7acd728d0f9988ce225423f13` |
| dev-sp | `0f694538fa8f84190ce9751f106f879a62550f8a`（2026-10-06） |
| dev-sp 基线 | `16322aef167fe14de8af28a9e437101ed3c4dac5`（sunnypilot，2026-09-30） |
| dev-sp opendbc | `3b9bf1895eca4983b2ed7cb620f318d362129112`（基线 `b2acec1dc7f15cfb258aa48415168485e29cc4ff`） |
| dev-sp panda | `ac0f791f8fb2105073c390784f47591b0d313a23`（基线 `4230530f5ec4c7f11971f868ae9930b3547346eb`） |
