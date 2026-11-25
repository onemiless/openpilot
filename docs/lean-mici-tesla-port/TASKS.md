# lean-mici × dev-sp 特斯拉移植：Codex 任务清单

> 配套文档：`lean-mici-tesla-port-plan.md`（调研依据、风险、附录映射表）。本文件是**可执行版**：每个任务有「命令」和「验收」。
> 所有 SHA、文件路径、行数均来自 2026-10-09 的实测；标注"以仓库实际脚本为准"的命令说明我没能在 lean 仓库里确认确切入口。

---

## 0. 已定决议（用户拍板 + 我的最优选择）

| # | 决议 | 来源 |
|---|---|---|
| D1 | **C3 相机**：零代码改动。沿用 lean 现有 spectra `camerad`（只有 OX03C10 / OS04C10 驱动）和 `modeld/SConscript` 里 `tici/tizi → _ar_ox_fisheye` 的配置。不移植 Chestnut 道路缩放。设备上**必须**验证路相机枚举为 `ox03c10`；若是 `ar0231` 或打不开，立即停止并汇报，不要自己写驱动。 | 用户 + dev-sp 文档（C3 运行时用 OX03C10 路相机） |
| D2 | **AGNOS 启动链**：C3 与 C3XL **不得使用 lean/C4 的 `abl`、`boot`**，一律取 dev-sp 现有值（C3 取 dev-sp `agnos.json`；C3XL 取 dev-sp `agnos-c3xl.json`）。**`system` 分区按 C4 升级**，即取 lean 的 19.6.27 `system`。C4 与 C3X 继续用 lean 原 `agnos.json`，一个字节都不动。 | 用户 |
| D3 | **三套纵向保留，全部按 dev-sp 的注册表落地**：Official=0、Experimental=1、TN-NoDEC=2（ID 不变，已存配置兼容）。Official = lean 上游规划器原样 + 24 行调参钩子；Experimental / TN 共享一对冻结的 legacy acados 求解器（primary + fallback）。默认模式 = Official。非 Tesla 车辆走零成本旁路（不导入 legacy 模块）。 | 我的最优选择（理由见 §P3） |
| D4 | **硬件 profile 运行时读取**：`profile.h` 改为运行时读 `/data/hardware_profile`（与 Python 同源），**删除** dev-sp 在 `SConstruct` 里的编译期 `CPPDEFINES`。这样 C3 与 C3XL **共用一个** `-c3` 发布分支，不必在 C3XL 设备上单独编译。 | 我的最优选择 |
| D5 | **profile 文件取值**：`standard`（C4/C3X，默认）、`c3`、`c3xl`。在 `tici` 设备上文件缺失或为 `standard` ⇒ **跳过 AGNOS 更新**（C3 与 C3XL 设备树同名，无法区分，宁可不刷也不猜）。 | 我的最优选择（对应 dev-sp 的失败案例"C3XL 被当成标准机"） |
| D6 | 默认移植并隔离：ARS408 雷达、BMS（挂 Tesla 页，不替换面板）；空输出模式氛围灯白名单（带 Toyota 负向回归，见 T1.5）。不移植：Chestnut、DM 开关、日志开关、更新分支策略、字体/中文化（P6 可选）。 | 默认值，可随时改 |

**不要做的事（红线）**：不改 `lean-master`/`lean-release`/`dev-sp` 任何分支；不 force-push；不抬 lean 的任何 pin；不向车辆发 CAN；不刷写 panda/AGNOS，除非任务明确写了"在备机上"且用户在场授权。

---

## 1. 工作区与变量

```bash
export WS=$HOME/work/tesla-port && mkdir -p $WS && cd $WS
export LEAN_BASE=4802cb2fe8c993fd7852b1f78be5b8b9604dd5a5      # lean-master
export LEAN_ODBC=7b519bc3                                      # lean 的 opendbc pin（lochuan/opendbc）
export LEAN_PANDA=74a0adced421e8b7acd728d0f9988ce225423f13     # lean 的 panda pin
export DEVSP=0f694538fa8f84190ce9751f106f879a62550f8a          # onemiless/openpilot dev-sp
export DEVSP_BASE=16322aef167fe14de8af28a9e437101ed3c4dac5     # dev-sp 的 sunnypilot 基线
export DEVSP_ODBC=3b9bf1895eca4983b2ed7cb620f318d362129112     # dev-sp 的 opendbc（基线 b2acec1d）
export DEVSP_PANDA=ac0f791f8fb2105073c390784f47591b0d313a23    # dev-sp 的 panda（基线 4230530f）
```

三个仓库并排放：`$WS/lean-mici`、`$WS/opendbc`、`$WS/panda`。主仓跑 Python 时：

```bash
cd $WS/lean-mici
export PYTHONPATH=$PWD:$PWD/opendbc_repo:$PWD/msgq_repo:$PWD/rednose_repo:$PWD/tinygrad_repo
# 依赖安装按仓库 tools/setup.sh / uv.lock 为准
```

**每个任务的通用要求**：提交前 `git status` 确认只含本任务文件；commit 前缀 `[tesla/pN.M]`；接缝文件改动同时登记到 `docs/tesla/SEAMS.md`；验收命令的输出存进 `docs/tesla/evidence/<任务号>.txt` 并随 commit 提交（体积大的放 `.gitignore` 并只记 SHA256）。

---

## P0 · 准备与基线

### T0.1 fork 与分支
```bash
cd $WS
git clone git@github.com:<you>/lean-mici.git && cd lean-mici      # <you>/lean-mici = fork of lochuan/lean-mici
git remote add lean  https://github.com/lochuan/lean-mici.git
git remote add devsp https://github.com/onemiless/openpilot.git
git fetch lean lean-master && git fetch devsp dev-sp
git config rerere.enabled true
git checkout -b lean-tesla $LEAN_BASE

cd $WS && git clone git@github.com:onemiless/opendbc.git opendbc && cd opendbc
git remote add lochuan https://github.com/lochuan/opendbc.git && git fetch lochuan
git fetch origin dev-sp
git checkout -b lean-tesla $LEAN_ODBC

cd $WS && git clone git@github.com:onemiless/panda.git panda && cd panda
git remote add sp https://github.com/sunnypilot/panda.git && git fetch sp
git fetch origin dev-sp
git checkout -b lean-tesla $LEAN_PANDA
```
**验收**
```bash
cd $WS/lean-mici && git rev-parse HEAD            # == $LEAN_BASE
git ls-tree HEAD opendbc_repo panda               # 两个 gitlink 的 SHA 分别以 7b519bc3 / 74a0adce 开头
cd $WS/opendbc && git rev-parse --short HEAD       # == 7b519bc3
cd $WS/panda  && git rev-parse HEAD                # == $LEAN_PANDA
```

### T0.2 基线记录与规约文件（主仓）
创建：
- `docs/tesla/PORT_BASELINE.json`：写入 §1 的全部 SHA、`msgq_repo/rednose_repo/tinygrad_repo` 的 lean pin（`git ls-tree $LEAN_BASE msgq_repo rednose_repo tinygrad_repo`）、dev-sp 的 opendbc/panda 提交区间（`e15d1889..3b9bf189`、`eebfc767..ac0f791f`）。
- `AGENTS.md`：取 `git show $DEVSP:AGENTS.md`，把分支名 `dev-sp` 改成 `lean-tesla`，其余规矩不动（失败模式先行、E2E 优先、不事后补单测、本地 commit 与设备 commit 分开报告）。
- `docs/tesla/SEAMS.md`：表头 `文件 | 阶段 | 增/删 | 作用 | dev-sp 来源 | 状态`，后续每个接缝一行。
- `docs/tesla/check_seams.sh`（≤ 20 行）：对 SEAMS.md 里每个文件执行 `git diff --numstat lean/lean-master -- <file>`，汇总**上游被修改文件数**与**净增行数**，超出预算（Tesla 核心 ≤ 26 文件 / ≤ 400 行；硬件 ≤ 24 文件 / ≤ 180 行）退出码 1。

**验收**：`python -c "import json;json.load(open('docs/tesla/PORT_BASELINE.json'))"` 通过；`bash docs/tesla/check_seams.sh` 在空接缝表下退出码 0。

### T0.3 基线测试（改动前）
```bash
cd $WS/lean-mici
# 以仓库实际脚本为准；下面是 lean 自带的测试入口
python -m pytest -q tools/release/test_release_lib.py tools/release/test_device_release_shell.py 2>&1 | tee docs/tesla/evidence/T0.3-release.txt
python -m pytest -q openpilot/selfdrive/car openpilot/selfdrive/controls openpilot/sunnypilot/selfdrive/controls openpilot/sunnypilot/selfdrive/car 2>&1 | tee docs/tesla/evidence/T0.3-core.txt
(cd opendbc_repo && python -m pytest -q opendbc/safety/tests/test_toyota.py opendbc/safety/tests/test_defaults.py 2>&1 | tee ../docs/tesla/evidence/T0.3-safety.txt)
```
**验收**：记录通过/失败/跳过的用例清单（失败的也记）。**之后任何阶段出现的失败，先与此基线对比，只处理新增失败。**

### T0.4 Toyota 回放基线（不变性的参照）
```bash
ls openpilot/selfdrive/test/process_replay        # 找到 lean 的回放入口（以仓库实际脚本为准）
# 对 card / controlsd / plannerd / selfdrived 在一段 Toyota 路线上回放，输出哈希存档：
#   docs/tesla/evidence/T0.4-toyota-replay.sha256
```
**验收**：生成基线哈希文件；同一命令重复运行两次哈希一致（排除非确定性）。找不到回放入口时，改用 `tools/sp_tesla_e2e/tesla_planner_chain_e2e.py --mode non-tesla` 的 Toyota 分支（T3.9 引入）并在证据里写明。

---

## P1 · opendbc（仓库：`$WS/opendbc`，分支 `lean-tesla`）

### T1.1 恢复 Tesla 自有路径（lean 已删，无冲突）
```bash
cd $WS/opendbc
git ls-tree -r --name-only origin/dev-sp -- opendbc/dbc | grep -iE 'tesla|ARS408'          # 先看清文件名
git checkout origin/dev-sp -- \
  opendbc/car/tesla \
  opendbc/sunnypilot/car/tesla \
  opendbc/dbc/generator/tesla \
  opendbc/safety/modes/tesla.h \
  opendbc/safety/tests/test_tesla.py
git checkout origin/dev-sp -- $(git ls-tree -r --name-only origin/dev-sp -- opendbc/dbc | grep -E '/(tesla_[^/]+\.dbc|ARS408\.dbc|tesla_can\.dbc)$')
git commit -m "[tesla/p1.1] restore Tesla car/dbc/safety/ars408 from onemiless/opendbc dev-sp (3b9bf189)"
```
**验收**：`git diff --stat HEAD~1 | tail -1` 新增文件数 ≥ 35；`git diff origin/dev-sp --stat -- opendbc/car/tesla opendbc/sunnypilot/car/tesla opendbc/safety/modes/tesla.h` 为空（与 dev-sp 逐字节一致）。

### T1.2 注册 Tesla（共享文件，只加 Tesla 条目）
逐文件做，每个文件先 `git diff b2acec1dc7f15cfb258aa48415168485e29cc4ff $DEVSP_ODBC -- <file>` 看 dev-sp 对它的改动，再手工只加 Tesla：

| 文件 | 动作 |
|---|---|
| `opendbc/car/values.py` | `from opendbc.car.tesla.values import CAR as TESLA`；`Platform = MOCK \| TOYOTA \| TESLA` |
| `opendbc/car/structs.py` | 加 `TeslaRoadContext`，`CarStateSP` 加 `flags`、`teslaRoadContext`（字段顺序与 dev-sp 一致） |
| `opendbc/car/torque_data/{params,override,substitute}.toml` | 用 `git show a595dced^:opendbc/car/torque_data/<f>` 对照，只把 Tesla 条目加回 |
| `opendbc/car/fingerprints.py`、`car_helpers.py` | 若有按品牌聚合的地方，加 Tesla |
| `opendbc/sunnypilot/car/interfaces.py` | 加 `from ...tesla.ars408.constants import TeslaRadarBackend`、`MadsScreenButtonType`、`TeslaFlagsSP`、`TeslaSafetyFlagsSP` 的 import；`setup_interfaces` 里加 `_initialize_coop_steering`、`_initialize_tesla_mads_screen_button`、`_initialize_tesla_dynamic_auto_stock`、`_initialize_tesla_ap_hybrid`、`_initialize_tesla_auto_speed_limit`、`_initialize_tesla_radar_backend` 六个调用及函数体；**不要**带回 Hyundai/Subaru/GM 的 import |
| `opendbc/sunnypilot/car/{car_list.json,platform_list.py,fingerprints_ext.py}` | 加 Tesla 条目（对照 `git show 821af8e7^:<path>`） |
| `opendbc/can/*`、`opendbc/dbc/generator/generator.py` | 用 `git show d0ba841a --stat`、`git show 2622fb1b --stat` 确认被删的 Tesla 校验/schema，只恢复 Tesla 部分 |

**验收**
```bash
python - <<'E'
from opendbc.car.values import PLATFORMS
assert any(str(p).startswith("TESLA") for p in PLATFORMS), "Tesla platforms missing"
from opendbc.car.tesla.interface import CarInterface   # import 链完整
print("ok", len(PLATFORMS))
E
python -m pytest -q opendbc/car/tesla opendbc/sunnypilot/car/tesla opendbc/sunnypilot/car/tests 2>&1 | tail -5
```
期望：Tesla 全部用例通过；`opendbc/car/tests` 里 lean 原有的 Toyota 用例结果与 T0.3 基线一致。

### T1.3 safety 共享文件
```bash
git diff b2acec1dc7f15cfb258aa48415168485e29cc4ff $DEVSP_ODBC -- \
  opendbc/safety/safety.h opendbc/safety/declarations.h opendbc/safety/modes/defaults.h \
  opendbc/safety/tests/libsafety/safety.c opendbc/safety/tests/test_defaults.py > /tmp/odbc-safety.patch
git apply --3way /tmp/odbc-safety.patch      # lean 的这几个文件应无冲突；有冲突则手工合并并保留 lean 的 Toyota 逻辑
```
**验收**：`git diff --stat` 只涉及这 5 个文件；`safety.h` 增 4 行、`declarations.h` 增 2 行（`rx_observer`），`defaults.h` 约 +76/-7。

### T1.4 安全测试
```bash
cd $WS/opendbc
bash opendbc/safety/tests/test.sh 2>&1 | tee ../lean-mici/docs/tesla/evidence/T1.4-safety.txt   # 以仓库实际脚本为准
python -m pytest -q opendbc/safety/tests/test_tesla.py opendbc/safety/tests/test_toyota.py opendbc/safety/tests/test_defaults.py
```
**验收**：`test_tesla.py` 全过（含 dev-sp 新增的 257 行）；`test_toyota.py` 与 T0.3 基线一致；MISRA 脚本（`opendbc/safety/tests/misra/test_misra.sh`，环境具备时）无新增告警。

### T1.5 空输出模式氛围灯：Toyota 负向回归（唯一允许新增的测试）
在 `opendbc/safety/tests/test_defaults.py` 确认存在"param=0 时 `SAFETY_NOOUTPUT` 拒绝 `0x679`"的用例；没有就补这一个负向用例（用 `libsafety_py`：`set_safety_hooks(SAFETY_NOOUTPUT, 0)`，`safety_tx_hook(0x679, bus1, len7)` 必须为 0；param=1 且无新鲜 rx 模板时同样为 0）。
**验收**：`python -m pytest -q opendbc/safety/tests/test_defaults.py -k ambient` 通过；注释掉 `defaults.h` 里 `nooutput_ambient_enabled = param == 1U;` 后该用例必须**失败**（变异检查，做完还原）。

### T1.6 推送与记录
```bash
git push origin lean-tesla
git rev-parse HEAD        # 记入 docs/tesla/PORT_BASELINE.json 的 "opendbc_lean_tesla"
```

---

## P2 · 主仓：cereal / 参数 / Tesla 控制 / UI

> 工作目录 `$WS/lean-mici`，分支 `lean-tesla`。先做 T2.1（cereal），其余依赖它。

### T2.1 cereal（槽位 @137，其余字段序号与 dev-sp 完全一致）
```bash
git diff $DEVSP_BASE $DEVSP -- openpilot/cereal/custom.capnp > /tmp/custom.patch
```
手工编辑 `openpilot/cereal/custom.capnp`（lean 版本里 `CustomReserved10` 已被改名为 `BigModelReply @0xcb9fd56c7057593a`，**不要碰它**）：
1. `LongitudinalPlanSP` 末尾追加 `accelController @8 :AccelController; teslaTrafficControl @9 :TeslaTrafficControlPlan;`，并在该结构体内追加 `struct AccelController { … }`（取自 /tmp/custom.patch）。
2. `CarStateSP` 追加 `flags @1 :UInt32; teslaRoadContext @2 :TeslaRoadContext; teslaTrafficControl @3 :TeslaTrafficControl;`，其后新增 `TeslaRoadContext`、`TeslaTrafficControl`、`TeslaTrafficControlPlan` 三个结构体。
3. 把 `struct CustomReserved11 @0xc2243c65e0340384 {}` 改成 `struct TrafficRadarState @0xc2243c65e0340384 { … }`，字段体取 dev-sp 的 `TrafficRadarState`（33 个字段，序号 `@0..@32` 不变）。

`openpilot/cereal/log.capnp`：把 `customReserved11 @137 :Custom.CustomReserved11;` 改成 `trafficRadarState @137 :Custom.TrafficRadarState;`。**`bigModelReply @136` 保持不动。**

`openpilot/cereal/services.py`：在 `"modelDataV2SP"` 行后加 `"trafficRadarState": (True, 20., 5, QueueSize.SMALL),`。

跳过 dev-sp 对 `cereal/SConscript` 的改动（`CAPNP_BIN_DIR`，lean 不需要）。

```bash
bash tools/release/regen_cereal_gen.sh
git status --short openpilot/cereal      # .capnp 与 gen/cpp 同时出现变更
git add openpilot/cereal && git commit -m "[tesla/p2.1] cereal: Tesla CarStateSP/LongitudinalPlanSP fields, trafficRadarState @137"
```
**验收**
```bash
bash tools/release/regen_cereal_gen.sh && git diff --exit-code openpilot/cereal/gen        # 再次生成无差异
python - <<'E'
from openpilot.cereal import log, custom
ev = log.Event.new_message()
ev.init("trafficRadarState"); assert ev.which() == "trafficRadarState"
ev2 = log.Event.new_message(); ev2.init("bigModelReply"); assert ev2.which() == "bigModelReply"
ev3 = log.Event.new_message(); ev3.init("carStateSP"); ev3.carStateSP.flags = 5; ev3.carStateSP.teslaTrafficControl.available = True
ev4 = log.Event.new_message(); ev4.init("longitudinalPlanSP"); ev4.longitudinalPlanSP.teslaTrafficControl.mode = 1
print("cereal ok")
E
```
并在 C++ 侧编译一次：`scons -j8 openpilot/cereal`（以仓库实际目标为准）无错。PR 描述写明：**设备需全量重建**。

### T2.2 参数键（末尾独立块）
编辑 `openpilot/common/params_keys.h`，在表尾 `// --- sunnypilot params ---` 之前**之后均可**，但必须是**一个连续块**，以 `// --- tesla fork params (docs/tesla/SEAMS.md) ---` 开头。内容取 dev-sp 的以下键，**默认值与标志位逐字一致**：
`TeslaBlindspotAmbientEnabled/Brightness/DayBrightness`、`MpcTuningProfile`、`MpcXObstacleCost`、`MpcJerkCost`、`MpcAccelChangeCost`、`MpcDangerZoneCost`、`MpcLeadDangerFactor`、`MpcComfortBrake`、`MpcStopDistance`、`MpcJerkFactorStandard`、`MpcTFollowRelaxed/Standard/Aggressive`、`SpeedLimitOffsetMaxSpeed`、`TeslaARS408Radar`、`TeslaTouchLongitudinalSwitch`、`TeslaApHybrid`、`TeslaDynamicApLongitudinal`、`DynamicAutoStock`、`DynamicAutoStockBlinkerToSP`、`DynamicAutoStockCurveToSP`、`DynamicAutoStockSpeedKph`、`DynamicAutoStockSpeedLowKph`、`LongitudinalPlannerMode`、`ActiveLongitudinalBackend`、`LongitudinalTuningConfig`、`AccelPersonalityEnabled`、`AccelPersonality`、`TeslaTrafficSignalControlEnabled`、`TeslaTrafficStopReference`、`TeslaTrafficControlMaxSpeed`。
**不带** `DriverMonitoringEnabled`、`ActiveDriverMonitoringEnabled`、`LoggingEnabled`；`TeslaCoopSteering`、`TeslaMadsScreenButton` lean 已有，不重复。

**验收**
```bash
python - <<'E'
import re,subprocess
new = set(re.findall(r'\{"(\w+)",', subprocess.check_output(["git","diff","-U0","HEAD","--","openpilot/common/params_keys.h"],text=True)))
assert not (new & {"DriverMonitoringEnabled","ActiveDriverMonitoringEnabled","LoggingEnabled","TeslaCoopSteering","TeslaMadsScreenButton"}), new
print(len(new),"keys added")
E
scons -j8 openpilot/common/libparams_c.so      # 重建键表
python -c "from openpilot.common.params import Params; p=Params(); print(p.get('LongitudinalPlannerMode', return_default=True))"   # 期望 0
```

### T2.3 拷贝 Tesla 自有模块（0 冲突）
```bash
git checkout $DEVSP -- \
  openpilot/sunnypilot/selfdrive/car/tesla \
  openpilot/selfdrive/ui/sunnypilot/tesla_settings.py \
  openpilot/selfdrive/ui/sunnypilot/layouts/settings/vehicle/brands/tesla.py \
  openpilot/selfdrive/ui/sunnypilot/layouts/settings/vehicle/brands/tesla_control.py \
  openpilot/selfdrive/ui/sunnypilot/layouts/settings/vehicle/brands/tesla_planner.py \
  openpilot/selfdrive/ui/sunnypilot/mici/layouts/tesla.py
```
然后做两处**不改上游**的适配：
1. `tesla.py` 里 `from openpilot.system.ui.lib.multilang import tr, trf` → `tr` 仍从 multilang 引，`trf` 改从 `tesla_settings` 引；在 `tesla_settings.py` 末尾加 `def trf(text, *a, **k): return tr(text).format(*a, **k)`（需 `from openpilot.system.ui.lib.multilang import tr`）。**不修改 `multilang.py`。**
2. `grep -rn "sunnypilot.hardware" openpilot/sunnypilot/selfdrive/car/tesla openpilot/selfdrive/ui/sunnypilot/*tesla* openpilot/selfdrive/ui/sunnypilot/layouts/settings/vehicle/brands/tesla*.py openpilot/selfdrive/ui/sunnypilot/mici/layouts/tesla.py` 必须**无输出**（Tesla 模块不依赖硬件 profile）。

`traffic_control.tesla_observer` 被 `card_adapter` 引用：此时 `traffic_control/` 还没拷（P3）。**做法**：本任务一并拷 `openpilot/sunnypilot/selfdrive/traffic_control/{__init__,tesla_observer,radar_state}.py`（仅这三个，`card_adapter` 的最小依赖），P3 再补其余文件。先 `python -c "import openpilot.sunnypilot.selfdrive.car.tesla.card_adapter"` 看缺什么，按 import 链补，**不要多拷**。

**验收**：`python -c "import openpilot.sunnypilot.selfdrive.car.tesla.card_adapter, openpilot.selfdrive.ui.sunnypilot.tesla_settings"` 无异常；上面的 grep 无输出。

### T2.4 `card.py` 接缝
```bash
git diff $DEVSP_BASE $DEVSP -- openpilot/selfdrive/car/card.py | git apply --3way
```
保留的内容（dev-sp 原样，lean 上已验证可干净套用）：`TeslaCardAdapter` import；`SubMaster` 增 `*CONTEXT_SERVICES`；`self.tesla_adapter = TeslaCardAdapter(...)`；`observe_can` / `publish_state` / `update_context` / `control_sends` / `service_params` 各一行；**`carStateSP` 在 `carState` 之前发布**（原子性需要，别"优化"回去）。
**验收**：`git diff --numstat -- openpilot/selfdrive/car/card.py` ≈ `19 6`；`python -c "import openpilot.selfdrive.car.card"` 通过。

### T2.5 `selfdrived.py` 接缝（只取 Tesla 的 5 处）
```bash
git diff $DEVSP_BASE $DEVSP -- openpilot/selfdrive/selfdrived/selfdrived.py > /tmp/sd.patch   # 手工选 hunk
```
只加：`TeslaControlRuntime` import；`__init__` 里 `self.tesla_control = TeslaControlRuntime(self.CP.brand == 'tesla')`、`car_state_sp_sock`（仅 enabled 时订阅）、`car_state_sp_flags`、`car_state_sp_mono_time`；`update_events` 里 `car_events` 之后 `self.tesla_control.filter_transition_events(self.events)`；`data_sample` 里读 `carStateSP` 并 `self.tesla_control.update(...)`；`step` 末尾 `self.tesla_control.commit_cycle()`。
**不加**：`driver_monitoring_enabled` import、`dm_enabled`、对 `cabinCameraState/driverMonitoringState` 的 ignore、DM 块的条件改写、`events_sp.add_from_msg` 的缩进调整。
**验收**：`git diff --numstat` ≈ `14 0`；`grep -n "dm_enabled\|driver_monitoring" openpilot/selfdrive/selfdrived/selfdrived.py` 无输出。

### T2.6 SP 侧小接缝
```bash
for f in \
  openpilot/sunnypilot/selfdrive/car/interfaces.py \
  openpilot/sunnypilot/selfdrive/controls/lib/speed_limit/__init__.py \
  openpilot/sunnypilot/selfdrive/controls/lib/speed_limit/speed_limit_assist.py \
  openpilot/sunnypilot/selfdrive/controls/lib/speed_limit/speed_limit_resolver.py ; do
  git diff $DEVSP_BASE $DEVSP -- $f | git apply --3way --whitespace=nowarn ; done
```
`openpilot/sunnypilot/selfdrive/selfdrived/events.py`：只取 `import math`、`resolve_pcm_long_required_max` 的 import 与 `speed_limit_pre_active_alert` 里那 4 行；**`big_model_ready_alert` 与 `HardwareProfile` import 留到 T4.9**。
**验收**：Toyota 路径不变——
```bash
python - <<'E'
from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit import resolve_pcm_long_required_max, PCM_LONG_REQUIRED_MAX_SET_SPEED, CONFIRM_SPEED_THRESHOLD
for metric in (True, False):
    lo, hi = PCM_LONG_REQUIRED_MAX_SET_SPEED[metric]
    for lim in (10, 30, 120):
        for has in (True, False):
            exp = lo if has and lim < CONFIRM_SPEED_THRESHOLD[metric] else hi
            assert resolve_pcm_long_required_max(metric, lim, has, brand="toyota") == exp
print("non-tesla identical")
E
```

### T2.7 Tesla UI 注册（2 个接缝）
- `openpilot/selfdrive/ui/sunnypilot/layouts/settings/vehicle/brands/factory.py`：加 `from ...brands.tesla import TeslaSettings`，`_BRAND_MAP` 加 `"tesla": TeslaSettings`。
- `openpilot/selfdrive/ui/sunnypilot/mici/layouts/settings.py`：加 `from ...mici.layouts.tesla import TeslaSettingsMici`；在 `items` 构造处插入 Tesla 入口按钮（参照 dev-sp 的 4 行）。**先读 lean 当前的 `items.insert(...)` 下标**（lean 新增了 bigmodel/lanlink 入口），把 Tesla 入口放在这些之后，不改既有下标。入口按钮仅在 `CP.brand == "tesla"` 时可见（`ui_state.CP` 已知时）。
**验收**：`python tools/sp_tesla_e2e/tesla_settings_e2e.py`（T2.9 完成路径修复后）通过；手工渲染（`ui_smoke`）无异常。

### T2.8 gitlink 与 `.gitmodules`
```bash
git config -f .gitmodules submodule.opendbc.url https://github.com/onemiless/opendbc.git
git config -f .gitmodules submodule.panda.url   https://github.com/onemiless/panda.git
git submodule sync
git -C opendbc_repo fetch origin lean-tesla && git -C opendbc_repo checkout $(git -C $WS/opendbc rev-parse HEAD)
git add .gitmodules opendbc_repo && git commit -m "[tesla/p2.8] point opendbc_repo/panda gitlinks to onemiless forks (lean-tesla)"
```
panda 的 gitlink 在 P4 完成后再改（此刻仍 `$LEAN_PANDA`，但 URL 已换，`git ls-remote https://github.com/onemiless/panda.git` 必须能看到该 SHA——它在 `lean-tesla` 分支起点上，先 `git -C $WS/panda push origin lean-tesla`）。
**验收**：`git submodule status` 无 `+`/`-` 前缀；`git ls-remote https://github.com/onemiless/opendbc.git lean-tesla` 的 SHA == gitlink。

### T2.9 Tesla E2E 脚本可移植化
```bash
git checkout $DEVSP -- tools/sp_tesla_e2e/{tesla_control_chain_e2e,ambient_safety,tesla_settings_e2e,tesla_display_e2e}.py
grep -rn "/Users/mile" tools/sp_tesla_e2e || true
```
把所有硬编码路径（`/Users/mile/...`）改成 `Path(__file__).resolve().parents[2]` 或环境变量；`libsafety` 用 `opendbc_repo/opendbc/safety/tests/libsafety`（先 `scons` 构建）。
**验收**：`grep -rn "/Users/" tools/sp_tesla_e2e` 无输出。

### T2.10 P2 验收（失败模式先行）
先在 `docs/tesla/evidence/P2-failures.md` 逐条写下失败模式再跑：
- F2.1 cereal 生成物过期/槽位冲突 → T2.1 验收已覆盖。
- F2.2 Tesla 所有权解析错位（FAULT 否决、AP hybrid 交接、停用后残留输出）。
- F2.3 参数快照与 `CP_SP.flags` 不一致；非 Tesla 车读到 Tesla 参数。
- F2.4 C4 设置页不可达 / 按钮下标冲突。
- F2.5 Toyota 路径被改动。

```bash
PYTHONDONTWRITEBYTECODE=1 python tools/sp_tesla_e2e/tesla_control_chain_e2e.py --output docs/tesla/evidence/P2-control-chain.json
python tools/sp_tesla_e2e/ambient_safety.py            --output docs/tesla/evidence/P2-ambient.json
python tools/sp_tesla_e2e/tesla_settings_e2e.py        --output docs/tesla/evidence/P2-settings.json
python tools/sp_tesla_e2e/tesla_display_e2e.py         --output docs/tesla/evidence/P2-display.json
# Toyota 不变：重跑 T0.4 的回放，哈希必须与 T0.4 基线一致
sha256sum -c docs/tesla/evidence/T0.4-toyota-replay.sha256
bash docs/tesla/check_seams.sh
```
**验收**：四个 JSON 里所有 `pass` 字段为真；Toyota 回放哈希一致；`check_seams.sh` 退出码 0。**车辆级验收不在此范围。**

---

## P3 · 三套纵向 + 红绿灯

### 设计（为什么这样最优）
1. **三套全保留**（Official / Experimental / TN-NoDEC）：它们对应你三种实际用法；dev-sp 已对三者做过 4248 周期逐位回放，重新发明只会引入偏差。
2. **Official = lean 上游规划器原样**。`registry.py` 里的 provider 指向 `openpilot.selfdrive.controls.lib.longitudinal_planner:LongitudinalPlanner`，不复制代码；lean 与 dev-sp 的该文件 **diff 为空**（已核实），所以上游变更会自动带入。
3. **Official 的 `Mpc*` 调参钩子（`long_mpc.py` +24/-5）保留**：补丁在 lean 上干净套用；用子类替代需要复制 `update()` 的 50 行，会随上游漂移，成本更高。登记进 SEAMS。
4. **Experimental 与 TN 共用一对冻结的 legacy 求解器**（`sp_legacy_cruise_v1` + `_fallback`，N=12、8 参数）与同一个 `LegacyLongitudinalPlanner`。**不要**把它并回上游 MPC（数值契约在 `legacy_mpc/contract.py` 里钉死）。fallback 求解器**保留**——它是主求解器失败时的恢复路径，砍掉会改变故障行为。
5. **默认模式 Official(0)**；TN 的 `high_speed_comfort_enabled=True` 保持 dev-sp 现状。
6. **非 Tesla 零成本旁路**：`create_longitudinal_planner/create_long_control` 对 `brand != "tesla"` 直接返回 Official / 普通 `LongControl`，不读 session 参数、不导入 `legacy_mpc`；legacy 的 `.so` 在发布树里存在但 Toyota 不加载。
7. **红绿灯默认关**（`TeslaTrafficSignalControlEnabled=0`）：关闭时 `create_final_plan_arbitrator` 返回 `None`，`plannerd` 走原始发布路径。
8. **dev-sp 回放没覆盖的三类场景在 lean 上补测**：DEC / Vision SCC / Map SCC / SLA 打开；bigmodeld ↔ 小模型回落；设备端（aarch64）求解器。

### T3.1 拷贝后端（含测试与 fixtures）
```bash
git checkout $DEVSP -- \
  openpilot/sunnypilot/selfdrive/controls/lib/longitudinal_backends \
  openpilot/sunnypilot/selfdrive/controls/tests
git rm -q --cached -r openpilot/sunnypilot/selfdrive/controls/lib/longitudinal_backends/legacy_mpc/c_generated_code* 2>/dev/null || true   # 生成物不入库（有 .gitignore）
```
`openpilot/sunnypilot/SConscript` 加一行：`SConscript(['selfdrive/controls/lib/longitudinal_backends/legacy_mpc/SConscript'])`。
**验收**：`git diff --numstat -- openpilot/sunnypilot/SConscript` == `1 0`。

### T3.2 构建 legacy 求解器（开发机）
```bash
scons -j$(nproc) openpilot/sunnypilot/selfdrive/controls/lib/longitudinal_backends/legacy_mpc   # 目标写法以仓库 SConstruct 为准
ls openpilot/sunnypilot/selfdrive/controls/lib/longitudinal_backends/legacy_mpc/c_generated_code{,_fallback}/ | grep -c '\.so'    # 期望 ≥ 12
python -c "
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_backends.legacy_mpc.c_generated_code.acados_ocp_solver_pyx import AcadosOcpSolverCython as A
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_backends.legacy_mpc.c_generated_code_fallback.acados_ocp_solver_pyx import AcadosOcpSolverCython as B
print('solvers import ok')"
```
**验收**：两个求解器均可导入；`legacy_mpc/contract.py` 的 N=12、`T_IDXS` 与生成的 OCP 元数据一致（dev-sp 的 `test_legacy_mpc.py` 覆盖）。

### T3.3 控制链接缝
| 文件 | 命令 | 保留内容 |
|---|---|---|
| `openpilot/selfdrive/controls/controlsd.py` | `git diff $DEVSP_BASE $DEVSP -- <f> \| git apply --3way` | `create_long_control(self.CP, self.CP_SP)` 替换 `LongControl(...)`（2 行） |
| `openpilot/selfdrive/controls/lib/longcontrol.py` | 同上 | `stopping_policy` 参数与 2 处调用（+8/-2） |
| `openpilot/sunnypilot/selfdrive/controls/lib/longitudinal_planner.py` | 同上 | `enable_dec`、`_update_backend`、`_publish_backend_state`（+15/-8） |
| `openpilot/selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py` | 同上 | 运行期调参钩子（+24/-5，D3-3） |
| `openpilot/selfdrive/controls/plannerd.py` | 同上（**此刻只取 `create_longitudinal_planner`**，仲裁器在 T3.6 加） | `planner = create_longitudinal_planner(CP, CP_SP, params=params)` |
**验收**：`python -c "import openpilot.selfdrive.controls.controlsd, openpilot.selfdrive.controls.plannerd"`；Toyota 回放（T0.4 哈希）一致。

### T3.4 manager 接缝
`openpilot/system/manager/manager.py`：加 `from ...longitudinal_backends.session import end_longitudinal_session`；在 `elif not started and started_prev:` 分支**最前面**加
`end_longitudinal_session(params, (managed_processes[name] for name in ("plannerd", "controlsd")))`。**不取** `latch_driver_monitoring`。
**验收**：`git diff --numstat` ≈ `2 0`。

### T3.5 回放工具与 dev-sp 参照
dev-sp 的回放基线在其本地 `artifacts/`（被 gitignore），需要自己重新生成：
```bash
git worktree add $WS/devsp-ref $DEVSP            # 只读参照，不要在里面提交
git checkout $DEVSP -- tools/sp_tesla_e2e/tesla_planner_chain_e2e.py tools/sp_tesla_e2e/traffic_override_e2e.py   # 然后修路径（同 T2.9）
# 参照侧（dev-sp 源码）生成基线
(cd $WS/devsp-ref && PYTHONPATH=. python tools/sp_tesla_e2e/tesla_planner_chain_e2e.py --mode replay --output $WS/replay-devsp.json)
# 移植侧
python tools/sp_tesla_e2e/tesla_planner_chain_e2e.py --mode replay --baseline $WS/replay-devsp.json --output docs/tesla/evidence/T3.5-replay-lean.json
```
**验收**：输出里 3 后端 × 3 调参档 × ACC/E2E = 18 组合各 236 周期逐位一致（`aTarget/shouldStop/allowThrottle/source/速度/加速度/jerk`）。若参照侧在你机器上无法构建 dev-sp 的求解器，改用 fixtures（`controls/tests/fixtures/tesla_legacy_*.json`）并在证据里写明。

### T3.6 红绿灯控制
```bash
git checkout $DEVSP -- openpilot/sunnypilot/selfdrive/traffic_control openpilot/selfdrive/ui/sunnypilot/onroad/traffic_control.py
git checkout $DEVSP -- tools/sp_tesla_e2e/traffic_override_e2e.py
```
接缝：
- `plannerd.py`：补 `create_final_plan_arbitrator` import、`ignore_services` 加 `"trafficRadarState"`、`SubMaster` 加 `'trafficRadarState'`、发布处 `publish_sink = pm if traffic_arbitrator is None else traffic_arbitrator.publisher(pm, sm)`。
- `openpilot/system/manager/process_config.py`：在 lean 现有 `# sunnypilot` 的 `procs += [...]` 里加一项
  `PythonProcess("trafficcontrold", "openpilot.sunnypilot.selfdrive.traffic_control.trafficcontrold", only_onroad),`。**不取** dev-sp 对该文件的其他改动。
- `openpilot/selfdrive/ui/sunnypilot/onroad/hud_renderer.py` 与 `.../mici/onroad/hud_renderer.py`：各加 import + `__init__` 一行 + `_update_state` 一行 + `_render` 一行（各 +4）。mici 版冲突时手工合并。
- **mici 布局核对**：lean 的 mici HUD 左上角是定速、左下角方向盘、右下角 `NPU_GREEN`、中部有 Reverse Gear 告警。真机截图确认 `TrafficControlRenderer(compact=True)` 与这四处不重叠，否则调它的锚点（只改 `traffic_control.py` 里的坐标）。
**验收**
```bash
python -m pytest -q openpilot/sunnypilot/selfdrive/traffic_control 2>&1 | tee docs/tesla/evidence/T3.6-traffic-tests.txt
python tools/sp_tesla_e2e/traffic_override_e2e.py --output docs/tesla/evidence/T3.6-traffic-override.json
```
期望：全过；JSON 覆盖——红灯停车事件连续、陈旧绿灯不起步、`forceDecel`/无效 `controlsState` 否决放行、油门/刹车/物理前车仍有效。

### T3.7 三套后端链路 E2E
```bash
for m in p1 session-transition cold-start non-tesla; do
  python tools/sp_tesla_e2e/tesla_planner_chain_e2e.py --mode $m --output docs/tesla/evidence/T3.7-$m.json
done
```
**验收**
- `p1`：27 个 case 全过（planner → Capnp 发布 → 所选 LongControl，含 force/health 否决）。
- `session-transition`：并发消费者与 manager ONROAD/OFFROAD 边界，旧写者在 session 清除前已退出/被 kill，下一 session 选到新的 Desired。
- `cold-start`：首帧已 engaged 时三种 provider 不崩。
- `non-tesla`：Toyota CP + 已存 Tesla 的 Experimental/TN/CrazyMAX 参数 ⇒ 仍返回 Official 与普通 `LongControl`，且 `'legacy_mpc' not in sys.modules`。

### T3.8 补测：dev-sp 没覆盖的场景（在 `tesla_planner_chain_e2e.py` 加三个 `--mode`，这是本阶段允许新增的 E2E）
1. `--mode features`：对 3 后端各打开 DEC / Vision SCC / Map SCC / SLA 回放，要求无异常、输出有限；Official 在 `Mpc*` 全默认时与"移除钩子"的上游规划器**逐位一致**（把钩子旁路后对比）。
2. `--mode bigmodel-fallback`：用含大模型→小模型回落（含 `SEQ_RESET/ZERO_PAIR`）的录制或合成 `modelV2` 序列，TN 与 Experimental 的 `aTarget` 连续（相邻周期跳变 ≤ 上限，上限取 jerk 限幅×dt），`shouldStop` 不抖。
3. `--mode device`（在 C3 设备上跑）：读 `fixtures/tesla_legacy_linux_aarch64.json`，设备端求解器输出与 fixture 一致。
**验收**：三个模式在开发机/设备上通过，证据入库。

### T3.9 发布清单与冒烟（`tools/release/`）
`release_lib.py`：
- `ARTIFACT_PATHS` 追加 `openpilot/sunnypilot/selfdrive/controls/lib/longitudinal_backends/legacy_mpc/{c_generated_code,c_generated_code_fallback}/` 下各 6 个文件：`acados_ocp_solver_pyx.so`、`libacados.so`、`libacados_ocp_solver_sp_legacy_cruise_v1.so`（fallback 目录为 `..._fallback.so`）、`libblasfeo.so`、`libhpipm.so`、`libqpOASES_e.so.3.1`。
- `NATIVE_INPUT_PATHS` 追加 `openpilot/sunnypilot/selfdrive/controls/lib/longitudinal_backends/legacy_mpc` 与 `openpilot/sunnypilot/hardware`。
- 同步改 `tools/release/test_release_lib.py`。
`tools/bench/smoke_after_build.sh`：追加一行设备端导入检查（两个求解器 `import`），失败即发布失败。
**验收**：`python -m pytest -q tools/release/test_release_lib.py` 通过；`python tools/release/release_lib.py artifact-paths | grep -c legacy_mpc` == 12。

### T3.10 P3 总验收
```bash
bash docs/tesla/check_seams.sh
sha256sum -c docs/tesla/evidence/T0.4-toyota-replay.sha256        # Toyota 不变
python -m pytest -q openpilot/sunnypilot/selfdrive/controls/tests openpilot/sunnypilot/selfdrive/traffic_control
```
期望全绿；`LongitudinalPlannerMode` 默认 0 时 Tesla 的 `longitudinalPlan` 与"无 Tesla 补丁"的 lean 规划器逐位一致（T3.8-1 已证）。

---

## P4 · C3 / C3XL：panda 固件 + pandad + 硬件 profile + AGNOS

> 可与 P1–P3 **并行**（独立工作流 B）。依赖：T1.x 的 opendbc 分支（固件需带 Tesla safety）。

### T4.1 panda：摘取 DOS 补丁
```bash
cd $WS/panda
git cherry-pick eebfc767 0f41a1f5 ce77749f ac0f791f        # 预期 6 个文件冲突
git status --short | grep -E '^(UU|AA)'
```
冲突文件：`SConscript`、`board/boards/board_declarations.h`、`board/boards/{cuatro,red,tres}.h`、`board/drivers/drivers.h`、`board/flasher.h`。逐个解决，原则：**以 lean 的当前内容为底，只加 DOS/F4 所需**。`fan_stall_recovery` 字段：先判断 DOS 的代码是否引用它，不引用就不带（并从 `cuatro/red/tres.h` 里去掉对应初始化行）。
**验收**：`git diff $LEAN_PANDA --stat -- board/boards/cuatro.h board/boards/red.h board/boards/tres.h` 为空或仅含 DOS 必需的行。

### T4.2 panda：构建与体积门禁（带 Tesla safety）
```bash
cd $WS/lean-mici
git -C panda checkout lean-tesla                 # 主仓里 panda 目录指向新分支（本地验证用）
scons -j8 panda/board/obj/panda.bin.signed panda/board/obj/bootstub.panda.bin panda/board/obj/panda_h7.bin.signed panda/board/obj/bootstub.panda_h7.bin
arm-none-eabi-size -A panda/board/obj/panda/main.elf | tee docs/tesla/evidence/T4.2-f4-size.txt
```
**验收**：四个文件都生成；F4 `main.elf` 的 `.text+.data` 不超过 `board/stm32f4/stm32f4_flash.ld` 里 app 区长度，`.data+.bss` 不超过 RAM 长度（把两个上限数值写进证据）；H7 固件内容会因 Tesla safety 改动而变化，属预期；Toyota 行为由 T1.4 的 safety 测试保证。

### T4.3 panda：推送
```bash
cd $WS/panda && git push origin lean-tesla && git rev-parse HEAD     # 记入 PORT_BASELINE.json 的 "panda_lean_tesla"
cd $WS/lean-mici && git -C panda fetch origin lean-tesla && git -C panda checkout $(git -C $WS/panda rev-parse HEAD) && git add panda
git commit -m "[tesla/p4.3] bump panda gitlink to onemiless/panda lean-tesla (DOS/F4 restored)"
```
**验收**：`git ls-remote https://github.com/onemiless/panda.git lean-tesla` == gitlink。

### T4.4 pandad：USB 通路
```bash
cd $WS/lean-mici
git checkout $DEVSP -- openpilot/selfdrive/pandad/usb.cc
for f in SConscript panda.cc panda.h panda_comms.h pandad.h; do
  git diff $DEVSP_BASE $DEVSP -- openpilot/selfdrive/pandad/$f | git apply --3way ; done
# pandad.py 的 hunk 依赖 T4.5 的 hardware 包（InternalPanda / PandaStartup），放到 T4.5 末尾再套
```
`SConstruct`：`pkg_names` 里加 `'libusb'`（**只加这一个词**；`comma-deps-libusb` 已在 lean 的 `pyproject.toml`，`libusb1` 已在 `uv.lock`）。**不要**加 `HARDWARE_PROFILE`/`CPPDEFINES`（D4）。
**验收**
```bash
scons -j8 openpilot/selfdrive/pandad/pandad
file openpilot/selfdrive/pandad/pandad && ldd openpilot/selfdrive/pandad/pandad | grep -i usb
```
期望：构建通过且链接 `libusb-1.0`。

### T4.5 硬件 profile 包（D4、D5）
```bash
git checkout $DEVSP -- openpilot/sunnypilot/hardware
git rm -q openpilot/sunnypilot/hardware/driver_monitoring.py openpilot/sunnypilot/hardware/branches.py
```
修改：
1. `profile.py`：`HardwareProfile` 增 `C3 = "c3"`（能力与 `STANDARD` 相同；所有 `!= C3XL` 判断不变）。`get_hardware_profile()` 的取值顺序保持：参数 > 环境变量 `SUNNYPILOT_HARDWARE_PROFILE` > 文件 `/data/hardware_profile` > `STANDARD`。
2. `profile.h`：把编译期 `#ifdef SUNNYPILOT_HARDWARE_PROFILE_C3XL` 改成运行时：
```cpp
#include <cstdlib>
#include <fstream>
#include <string>
inline HardwareProfile get_hardware_profile() {
  static const HardwareProfile cached = [] {
    std::string v;
    if (const char *e = std::getenv("SUNNYPILOT_HARDWARE_PROFILE")) v = e;
    else { const char *p = std::getenv("SUNNYPILOT_HARDWARE_PROFILE_FILE"); std::ifstream(p ? p : "/data/hardware_profile") >> v; }
    return v == "c3xl" ? HardwareProfile::C3XL : HardwareProfile::STANDARD;   // C3 在 C++ 侧与 STANDARD 等价
  }();
  return cached;
}
```
3. `tests/`：删除引用 `driver_monitoring`、`branches` 的用例；`test_profile.py` 增加 `c3` 取值用例；`test_agnos.py` 在 T4.8 一并改。
4. 写一个 10 行的 C++ 小程序 `tools/tesla/profile_h_check.cc` + `tools/tesla/profile_h_check.sh`：分别在 `SUNNYPILOT_HARDWARE_PROFILE=` 空 / `standard` / `c3` / `c3xl` 下编译运行，打印 `is_c3xl()`。
5. 现在套 `pandad.py`：`git diff $DEVSP_BASE $DEVSP -- openpilot/selfdrive/pandad/pandad.py | git apply --3way`（`get_expected_signature(panda)`、`InternalPanda`、`PandaStartup`、`./pandad <serial>`）。
**验收**
```bash
python -m pytest -q openpilot/sunnypilot/hardware/tests
python -c "import openpilot.selfdrive.pandad.pandad"
bash tools/tesla/profile_h_check.sh        # 期望仅 c3xl 输出 1，其余 0
grep -rn "driver_monitoring\|branches" openpilot/sunnypilot/hardware || echo clean
```

### T4.6 设备类型与供电接缝
```bash
for f in openpilot/common/hardware/comma/hardware.h openpilot/common/hardware/comma/hardware.py \
         openpilot/system/hardware/power_monitoring.py ; do
  git diff $DEVSP_BASE $DEVSP -- $f | git apply --3way ; done
```
`hardware.h`：`device_map` 加回 `{"tici", TICI}`；`is_c3xl()` 时 `tici` 报 `TIZI`。`hardware.py`：`amplifier` 在 `not has_amplifier()` 时返回 `None`。`power_monitoring.py`：忽略非正电压。
`openpilot/system/hardware/hardwared.py`：
- DOS 供电读数：`peripheralState.pandaType == dos` 时电压取 `HARDWARE.get_voltage()`（dev-sp 原 hunk，lean 可干净套用）。
- **tici 通道门控**（不要写死 `dev-sp`）：
  `is_unsupported_combo = COMMA_HARDWARE and HARDWARE.get_device_type() == "tici" and build_metadata.channel_type != "tici" and get_hardware_profile() not in (HardwareProfile.C3, HardwareProfile.C3XL)`
**验收**：`python -m pytest -q openpilot/system/hardware/tests`；`git diff --numstat` 各文件与 SEAMS 登记一致。

### T4.7 蜂鸣器（C3XL 无功放）
```bash
git checkout $DEVSP -- openpilot/sunnypilot/system/alert_output.py
```
- `process_config.py`：在 `# sunnypilot` 块加
  `PythonProcess("alert_output", "openpilot.sunnypilot.system.alert_output", lambda started, params, CP: not PC and get_hardware_profile() == HardwareProfile.C3XL),`
  以及对应 import（`from openpilot.sunnypilot.hardware.profile import HardwareProfile, get_hardware_profile`）。
- `sunnypilot/selfdrive/selfdrived/events.py`：补 T2.6 留下的 `big_model_ready_alert`（C3XL 用 `promptRepeat`）和 `EventNameSP.bigModelReady` 的可调用形式。
**验收**：C3XL profile 下 `managed_processes["alert_output"].should_run(...)` 为真，其余 profile 为假（用 `SUNNYPILOT_HARDWARE_PROFILE` 环境变量逐一验证的 10 行脚本，存 `tools/tesla/alert_output_gate_check.py`）。

### T4.8 AGNOS 清单（D2、D5）——最需要小心的一步
**4.8.1 取参照文件**
```bash
mkdir -p docs/tesla/ref/agnos
git show $DEVSP:openpilot/common/hardware/comma/agnos.json       > docs/tesla/ref/agnos/devsp-c3.json
git show $DEVSP:openpilot/common/hardware/comma/agnos-c3xl.json  > docs/tesla/ref/agnos/devsp-c3xl.json
git show $LEAN_BASE:openpilot/common/hardware/comma/agnos.json   > docs/tesla/ref/agnos/lean-c4.json
```
**4.8.2 生成脚本** `tools/tesla/build_agnos_manifest.py`（约 25 行，原样实现下面的规则）：
```python
#!/usr/bin/env python3
"""C3/C3XL manifest = dev-sp boot chain (xbl..boot) + lean C4 system. Byte-exact copies, no re-hashing."""
import json, sys
REF = "docs/tesla/ref/agnos/"
OUT = "openpilot/common/hardware/comma/"
CHAIN = ["xbl", "xbl_config", "abl", "aop", "devcfg", "boot"]

def load(name):
  return {p["name"]: p for p in json.load(open(REF + name))}

def build(devsp_name):
  chain, lean = load(devsp_name), load("lean-c4.json")
  return [chain[n] for n in CHAIN] + [lean["system"]]

if __name__ == "__main__":
  for ref, out in (("devsp-c3.json", "agnos-c3.json"), ("devsp-c3xl.json", "agnos-c3xl.json")):
    manifest = build(ref)
    if "--check" in sys.argv:
      assert json.load(open(OUT + out)) == manifest, f"{out} drifted"
    else:
      with open(OUT + out, "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
  print("ok")
```
```bash
python tools/tesla/build_agnos_manifest.py && python tools/tesla/build_agnos_manifest.py --check
```
**4.8.3 事实断言**（写成 `tools/tesla/check_agnos_manifests.py`，并存证据）：
- `agnos-c3.json` 与 `agnos-c3xl.json`：前 6 个分区（`xbl…boot`）与对应 dev-sp 文件**逐字段相等**；`system` 与 `lean-c4.json` 的 `system` 相等。
- 两者的 `boot` 哈希**都不等于** lean-c4 的 `boot`（`86275abc…`）；C3XL 的 `abl` **不等于** lean-c4 的 `abl`（`29fd7ed1…` vs `32a2174b…`）。**C3 的 `abl` 等于 lean-c4 的 `abl`（dev-sp 标准清单本来就是 `29fd7ed1…`）——这是 dev-sp 的现状，按"取 dev-sp 的值"处理，脚本只断言等于 dev-sp，不要求不同于 C4，并在证据里打印这条事实。**
- 所有 boot-chain 分区 `has_ab == True` 且 `full_check == True`。
- `lean-c4.json` 与 `git show $LEAN_BASE:...` 字节一致（C4 清单未被改动）。
**4.8.4 白名单校验**：把 dev-sp `sunnypilot/hardware/agnos.py` 里手写的 `C3XL_BOOT_CHAIN_ALLOWLIST` 换成**由参照 JSON 生成**的两份常量（`C3_BOOT_CHAIN_ALLOWLIST`、`C3XL_BOOT_CHAIN_ALLOWLIST`，字段 `hash/hash_raw/size`，含 `boot`），用 `tools/tesla/gen_bootchain_allowlist.py` 打印后粘贴，不要手敲哈希。`validate_agnos_manifest(partitions, profile)` 对 `C3`、`C3XL` 两个 profile 都执行白名单比对，对 `STANDARD` 直接放行。
**4.8.5 启动脚本选择清单**（`launch_env.sh` + `launch_chffrplus.sh` + `updated.py`）
`launch_env.sh` 追加（保留 lean 的 `AGNOS_VERSION`/`AGNOS_ACCEPTED_VERSIONS` 原样）：
```bash
model_file="${SUNNYPILOT_HARDWARE_MODEL_FILE:-/sys/firmware/devicetree/base/model}"
profile_file="${SUNNYPILOT_HARDWARE_PROFILE_FILE:-/data/hardware_profile}"
profile_value="${SUNNYPILOT_HARDWARE_PROFILE:-}"
[ -z "$profile_value" ] && [ -f "$profile_file" ] && profile_value="$(cat "$profile_file")"
device_model="$(tr -d '\0' < "$model_file" 2>/dev/null)"
export AGNOS_MANIFEST_FILE="openpilot/common/hardware/comma/agnos.json"
export AGNOS_SKIP_UPDATE=0
case "$device_model" in
  *tici)
    case "$profile_value" in
      c3)   AGNOS_MANIFEST_FILE="openpilot/common/hardware/comma/agnos-c3.json" ;;
      c3xl) AGNOS_MANIFEST_FILE="openpilot/common/hardware/comma/agnos-c3xl.json" ;;
      *)    AGNOS_SKIP_UPDATE=1 ;;      # tici 设备树 C3 与 C3XL 同名：不明确就不刷
    esac ;;
esac
export AGNOS_MANIFEST_FILE AGNOS_SKIP_UPDATE
```
`launch_chffrplus.sh`：`MANIFEST="$DIR/$AGNOS_MANIFEST_FILE"`；`if [ "$AGNOS_SKIP_UPDATE" = "1" ]; then AGNOS_UPDATE_REQUIRED=0; echo "AGNOS update skipped: tici without /data/hardware_profile in {c3,c3xl}" >&2; fi`。
`openpilot/system/updated/updated.py`：`handle_agnos_update` 的清单名按 profile 选 `agnos-c3.json / agnos-c3xl.json / agnos.json`（路径在 `openpilot/common/hardware/comma/`）。
`openpilot/common/hardware/comma/agnos.py`：`load_agnos_manifest()` + `validate_agnos_manifest()`（dev-sp 原 hunk，lean 可干净套用）。
**验收**（E2E，纯本地，无设备）：`tools/tesla/agnos_select_e2e.sh` 遍历下表，源 `launch_env.sh` 后断言：

| 设备树 model | profile | `AGNOS_MANIFEST_FILE` | `AGNOS_SKIP_UPDATE` |
|---|---|---|---|
| `comma mici` | 空 | `agnos.json` | 0 |
| `comma tizi` | 空 | `agnos.json` | 0 |
| `comma tici` | `c3` | `agnos-c3.json` | 0 |
| `comma tici` | `c3xl` | `agnos-c3xl.json` | 0 |
| `comma tici` | 空 / `standard` | `agnos.json` | **1** |

另：`python -m pytest -q openpilot/sunnypilot/hardware/tests/test_agnos.py` 覆盖——喂一个把 `abl` 换成 C4 值的 C3XL 清单，必须抛 `UnsafeBootChainManifest`；喂 `STANDARD` 则放行。

### T4.9 离线兼容性预检（dev-sp 的 boot + lean 的 system，**用户已决定，此处只做证据，不做阻断以外的判断**）
```bash
mkdir -p $WS/agnos-check && cd $WS/agnos-check
python - <<'E'
import json
for ref in ("devsp-c3","devsp-c3xl","lean-c4"):
    for p in json.load(open(f"/path/to/lean-mici/docs/tesla/ref/agnos/{ref}.json")):
        if p["name"] in ("boot","system"): print(ref, p["name"], p["url"])
E
# 下载（URL 来自上面输出）→ 校验 hash_raw/hash → 解压
curl -LO <boot url>; xz -dk boot-*.img.xz 2>/dev/null; sha256sum boot-*.img            # 与清单 hash_raw 比对
strings -n 16 boot-*.img | grep -m1 'Linux version'                                    # 记下 dev-sp boot 与 lean boot 各自的内核版本串
simg2img system-*.img system.raw 2>/dev/null || cp system-*.img system.raw
debugfs -R 'ls -l /lib/modules' system.raw; debugfs -R 'cat /VERSION' system.raw        # lean system 里的内核模块目录与版本
```
写入 `docs/tesla/evidence/T4.9-agnos-compat.md`：dev-sp boot（C3、C3XL 各一）内核版本串、lean boot 内核版本串、lean system 的 `/lib/modules/*`。
**验收/停止条件**：证据文档存在；**如果** lean system 的 `/lib/modules` 目录里**没有**任何 dev-sp boot 内核版本对应项，**且**设备上的 `lsmod` 在 dev-sp 当前系统里非空（说明驱动依赖模块），则**停止，把结论报告给用户**，不要继续 T6.x 的刷机步骤。其余情况继续。

### T4.10 设备端后检查脚本（供备机刷后运行）
`tools/tesla/agnos_postflash_check.sh`（输出 JSON 行，存 `/data/agnos_postflash_$(date +%s).json`）采集：`cat /VERSION`、`uname -r`、`abctl --boot_slot`、`sudo abctl --get_success`（或等价）、`dmesg -l err,crit | wc -l`、`ls /dev/kgsl-3d0 /dev/spidev0.0 /dev/ion`、`lsusb`、`ip -br a`、`systemctl is-active comma`、`cat /data/hardware_profile`、`python tools/tesla/camera_check.py`。
另写 `tools/tesla/agnos_slot_check.py`（**只读**，设备上 root 运行）。注意 `agnos.py --verify` **会在目标槽就绪时直接换槽**，不能当只读检查用：
```python
#!/usr/bin/env python3
import json, subprocess, sys
from openpilot.common.hardware.comma.agnos import slot_number_to_suffix, verify_partition
slot = 0 if subprocess.check_output(["abctl", "--boot_slot"], encoding="utf-8").strip() == "_a" else 1   # 当前启动槽
for p in json.load(open(sys.argv[1])):
  print(f"{p['name']:<10} active{slot_number_to_suffix(slot)} match={verify_partition(slot, p, force_full_check=True)}")
```
**验收**：脚本存在，在 PC 上 `bash -n` / `python -m py_compile` 通过；设备上的运行在 T6.x。

### T4.11 C3 相机验收脚本（D1）
`tools/tesla/camera_check.py`（设备上、**离线**、manager 停止时运行）：启动 `camerad`，订阅 `roadCameraState`/`wideRoadCameraState`/`driverCameraState`（C3XL 无座舱相机，预期无帧），各取 ≥ 100 帧，打印 `sensor` 枚举名、`frameId` 连续性、平均帧率；退出码非 0 当：路相机不是 `ox03c10`、帧率 < 18 Hz、帧号跳变 > 0。
**验收**：脚本 `python -m py_compile` 通过；设备运行结果在 T6.x。**若 `sensor` 为 `ar0231` 或 camerad 起不来 → 停止并汇报（D1）。**

### T4.12 P4 本地总验收
```bash
bash docs/tesla/check_seams.sh
python -m pytest -q openpilot/sunnypilot/hardware openpilot/system/hardware tools/release
bash tools/tesla/agnos_select_e2e.sh
python tools/tesla/check_agnos_manifests.py
# H7 回归：C4 路径不受影响
python -m pytest -q openpilot/selfdrive/pandad/tests 2>&1 | tail -5
```
期望全绿。pandad 的 `test_pandad_spi.py` 等设备用例在 T6.x 跑。

---

## P5 · BMS（约 1 天）

### T5.1
```bash
git checkout $DEVSP -- openpilot/selfdrive/ui/sunnypilot/layouts/settings/bms.py openpilot/sunnypilot/selfdrive/car/tesla/bms.py docs/tesla_bms_dashboard.md
```
在 `TeslaSettings`（`brands/tesla.py`）加一个入口按钮，点击 `gui_app.push_widget(BmsLayout())`。**不碰 `layouts/settings/settings.py`**（不替换任何面板；lean 本来也没有 Trips）。
**验收**
```bash
python tools/sp_tesla_e2e/tesla_display_e2e.py --output docs/tesla/evidence/T5.1-bms.json
grep -n "BmsLayout" openpilot/selfdrive/ui/sunnypilot/layouts/settings/settings.py || echo "settings.py untouched"
```
期望：被动订阅（只在页面可见且 CarParams 为 Tesla 时订阅 `can`）、换车清数据、无任何 CAN 发送；`git diff --stat lean/lean-master -- openpilot/selfdrive/ui/sunnypilot/layouts/settings/settings.py` 为空。

---

## P6 · 发布与设备验收

> 本阶段涉及真机，**由用户在场执行或明确授权**。Codex 负责准备脚本与清单、解读输出。

### T6.1 发布脚本接入（`tools/release/`）
1. `device_release.sh` 的 `materialize_gitlinks`：`panda` URL → `https://github.com/onemiless/panda.git`，canary 改为 `board/boards/dos.h`；`opendbc_repo` URL → `https://github.com/onemiless/opendbc.git`，canary 改为 `opendbc/car/tesla/carcontroller.py`。
2. `release_lib.py`：`ARTIFACT_PATHS` 追加 `panda/board/obj/bootstub.panda.bin`、`panda/board/obj/panda.bin.signed`（T3.9 已加 legacy 求解器）。
3. 新增发布前置检查：当 `RELEASE_BRANCH` 以 `-c3` 结尾时，要求 `/data/hardware_profile` ∈ {`c3`,`c3xl`}；以 `-c4` 或无后缀时要求 `standard`。不匹配 `die`。
4. `tools/release/test_release_lib.py`、`test_device_release_shell.py` 同步。
**验收**：`python -m pytest -q tools/release` 全过；`grep -n "onemiless" tools/release/device_release.sh` 出现两行。

### T6.2 备机刷 AGNOS（C3 一台、C3XL 一台，**不是车上的设备**）
前置：T4.9 通过且用户确认；备机有 USB 线与 EDL/恢复手段；先记录刷前状态 `bash tools/tesla/agnos_postflash_check.sh` → `before.json`。
```bash
echo c3 > /data/hardware_profile          # C3XL 设备写 c3xl
cd /data/openpilot && git fetch origin lean-tesla && git checkout lean-tesla     # 备机放在 lean-tesla
AGNOS_PY=openpilot/common/hardware/comma/agnos.py
sudo python tools/tesla/agnos_slot_check.py openpilot/common/hardware/comma/agnos-c3.json   # 只读：当前槽
# 期望：xbl/xbl_config/abl/aop/devcfg/boot 全部 match=True（设备本来就是 dev-sp 启动链），system match=False
# 不要用 agnos.py --verify 做检查：目标槽就绪时它会直接换槽。
# 确认无误后，由 launch_chffrplus.sh 触发更新（updater 把清单写入**非当前槽**并换槽），或手动：
sudo python $AGNOS_PY --swap openpilot/common/hardware/comma/agnos-c3.json && sudo reboot   # 同样只在备机、有人值守时
```
**验收**：
- `agnos_slot_check.py` 显示 `xbl…boot` 在**当前槽**均 `match=True`、仅 `system` 为 False；若任何 boot-chain 分区不匹配 ⇒ **停止**（备机当前启动链不是 dev-sp 的，D2 前提不成立）。
- 更新只写**非当前槽**，当前槽保持原样，所以回退就是换回旧槽。
- 刷后 `agnos_postflash_check.sh` → `after.json`：`/VERSION == 19.6.27`；`systemctl is-active comma == active`；`/dev/kgsl-3d0`、`/dev/spidev0.0`（C3XL）、USB panda（C3）存在；`dmesg -l err,crit` 条数与 `before.json` 相比无**新增类别**；`abctl` 当前槽标记成功。
- 失败回退：`sudo abctl --set_active <旧槽>` 后 `reboot`；仍起不来走 EDL。

### T6.3 备机上跑相机与 panda
```bash
sudo systemctl stop comma
python tools/tesla/camera_check.py                                   # D1 验收
python -m pytest -q openpilot/selfdrive/pandad/tests/test_pandad.py   # C3：USB DOS；C3XL：SPI tres（以仓库实际用例为准）
python -c "from panda import Panda; p=Panda(); print(p.get_type(), p.get_version(), p.get_mcu_type())"
```
**验收**：C3：`get_type()==b'\x06'`（DOS）且 `get_mcu_type()==F4`；固件签名与 `panda.bin.signed` 一致；`health()['temperature'] is None`（F4 无 DTS）。C3XL：内部 SPI panda 原始类型为 `0x00` 或 `0x09`，有效类型解析为 tres。`camera_check.py` 退出码 0。

### T6.4 按设备类别构建发布（在对应设备上）
```bash
# C4：SRC_BRANCH=lean-tesla RELEASE_BRANCH=lean-tesla-release bash tools/release/device_release.sh
# C3 与 C3XL 共用（D4），在任一 C3 类备机上构建：
SRC_BRANCH=lean-tesla RELEASE_BRANCH=lean-tesla-release-c3 bash tools/release/device_release.sh
```
**验收**：脚本末尾的 `jungle` 台架冒烟通过；`release_lib.py check-flat-tree` 通过；产物包含 `panda.bin.signed`、`bootstub.panda.bin`、12 个 legacy 求解器文件、`pandad` 链接 libusb。**C4 上编出的发布分支不得安装到 C3 类设备**（pkl 内嵌相机配置与 GPU kernel）。

### T6.5 台架（无车，不发 CAN 到车）
扩展 `tools/bench/jungle_replay.sh`：支持 `CAR=tesla|toyota`，新增 `tools/bench/tesla_can_loop.xz`（取 dev-sp 的 Tesla 路由生成点火循环）。
**验收**：Toyota 循环与 Tesla 循环各跑一遍，核心进程 onroad 稳定、`plannerd/controlsd/card/trafficcontrold` 无重启；`pandaStates` 无 `canTxBufferOverflow`/`canRxBufferOverflow` 增长（F4 缓冲被缩小，需特别看）。

### T6.6 实车门禁（人工清单，Codex 不执行）
- [ ] 静止、熄火：设置页可达；BMS 无发送；氛围灯按安全白名单发帧速率 ≤ 10 Hz。
- [ ] 点火、不接合：`carState` 正常、ARS408/OEM 雷达选择生效、无 CAN 错误。
- [ ] 低速场地：横向接合 → 纵向 Official → Experimental → TN；红绿灯 Off/Shadow/On 分步，先 Off。
- [ ] 每次模式切换必须熄火重启（session 锁存，行为符合预期）。
- [ ] C3XL：蜂鸣器提示；无座舱相机、无麦克风 ⇒ 无相关报错。

---

## P7 · 优化轮（全部放在移植验收通过之后，单独 commit，每个附回放证据）

| 任务 | 内容 | 验收 |
|---|---|---|
| T7.1 | `speed_limit/__init__.py` 里的 `brand=` 分支改为 Tesla 注册覆盖 | T2.6 的非 Tesla 恒等脚本 + `tesla_planner_chain_e2e.py --mode replay` 逐位一致 |
| T7.2 | 删退役墓碑：`TeslaRoadContext`、`AccelController.shadowOnlyDEPRECATED`、`TrafficRadarState.suppressedByPhysicalLead`、退役的 TX 兼容位 | **会改字段序号**，仅在不再需要回放 dev-sp rlog 时做；`regen_cereal_gen.sh` + 全 E2E |
| T7.3 | 评估把 Official 调参钩子改成子类（D3-3 的反方案） | 若子类需复制 > 20 行 `update()` 则放弃并在 SEAMS 记录结论 |
| T7.4 | `traffic_control/controller.py`（927 行）、`final_plan_arbitrator.py`（938 行）按职责拆分 | 回放逐位一致；不改对外接口 |

---

## 附：阶段依赖与并行建议

```
P0 ─┬─ P1 (opendbc) ─┬─ P2 (cereal/params/控制/UI) ─ P3 (纵向+红绿灯) ─┐
    │                └─ T4.1–T4.3 (panda 固件，需要 P1 的 safety)       ├─ P6 (发布/设备)
    └─ T4.4–T4.12 (pandad/profile/AGNOS，独立) ──────────────────────────┘
                                               P5 (BMS) 依赖 P2；P7 在 P6 之后
```

建议 Codex 开三条并行线：**A**（P1→P2→P3→P5）、**B**（T4.1–T4.3 + T4.4–T4.12）、**C**（T0.x 与 T6.1 的发布脚本改动）。A 与 B 在 T2.8/T4.3 处通过 gitlink 汇合。

## 附：何时必须停下来问用户

1. T4.9 的兼容性预检触发"停止条件"。
2. T4.11 / T6.3 发现 C3 路相机不是 `ox03c10`。
3. T6.2 的 `--verify` 显示备机 boot-chain 分区与 dev-sp 清单不一致。
4. 任何步骤需要改 `lean-master`、`lean-release`、`dev-sp`，或需要抬 lean 的 pin。
5. 接缝预算（`check_seams.sh`）超限。
6. 任何一步需要向车辆发 CAN 或刷写 panda/AGNOS 而任务里没有写明授权。
