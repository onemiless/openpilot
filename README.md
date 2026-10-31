# sp-flasher

从 dev-sp 派生的专用 R2 刷写分支。仅自动识别底座、整片刷 R2、回读校验、固定大模型推理 60 秒。
无驾驶/摄像头/Panda/导航/设置/OTA/AGNOS 更新。启动路径不读取系统版本，不安装依赖、不下载资源、不重启系统。

## 运行边界

开发阶段仅完成主机模拟，不连接或刷写设备。不要在开发主机运行 launch_openpilot.sh 或 station.py。
以后单独安排设备验收。安装到 C3 后 comma.service 的启动入口仍为 launch_openpilot.sh；服务只启动 station.py。
只在独占维护的 C3 使用此分支，不运行其他 SP/驾驶进程。应用不写 IsOffroad/IsEngaged 参数。

启动优先复用兼容的系统 Python/NumPy、libusb、LLVM 和 fuser；缺少或不兼容时使用 `runtime/` 下的离线依赖。
随包版本：ARM64 Python 3.11.15、NumPy 2.2.6、libusb 1.0.23、LLVM 19.1.7、fuser 23.3 及必要共享库。
Python/NumPy 按 ABI 成对选择；系统 Python 无法加载 cp311 NumPy 时自动使用随包 Python。
整个选择过程只做 NumPy 运算、库 API 检查及 gfx1200 LLVM 内核编译，不创建 USB 上下文。
选择完成后，在最终共享库环境中再次验证，并使用同一解释器启动 station、刷写预检和推理。

`runtime/` 是普通文件夹，不往 `/usr`、`/lib` 或系统 Python 环境写文件。
不携带、不替换 glibc 和系统动态加载器。随包 ELF 最高需要 GLIBC_2.30；实际加载失败时停止，不更新系统。
启动不按 AGNOS 版本号拦截，不执行 apt/pip/uv、不联网安装、不解压下载包。
`requirements.txt` 只是开发依赖说明，设备启动不会安装它。

```text
runtime/python/   独立 Python（移除了 pip、开发头文件和 GUI 资源）
runtime/numpy/    cp311 ARM64 NumPy 与其私有运算库
runtime/libusb/   libusb、libudev
runtime/llvm/     LLVM 与原生库的传递依赖
runtime/tools/    fuser 后备
runtime/licenses/许可文件
```

启动前用系统 SHA-256 工具校验 `runtime/SHA256SUMS`，然后才会执行随包 Python。
实际解释器、NumPy 路径、libusb/LLVM 路径及编译结果哈希记录在 `/data/sp-flasher/runtime.json`。
仅检查依赖并退出可运行 `bash runtime.sh --check-runtime`；此模式不导入 station、不枚举 USB，不启动刷写。
主机验证需要设置主机自己的 LLVM/libusb 路径；ARM64 随包程序只用于 Linux ARM64。

## 唯一流程

1. 检测到一个受支持 USB 通路的底座后自动开始；无指定 UID/serial/旧固件/许可证绑定。
2. 校验随包模型、R2、GPU 固件和运行文件的 SHA-256，检查运行库。
3. 三次整片备份落盘，保留当前本板前 256 字节配置和 0x17FE0 后内容。
4. 重写全部 64 个 4 KiB 扇区，扇区 0 最后；逐页、逐扇区和三次整片回读校验。
5. 状态为 WAIT_POWER_CYCLE 时，同时断开底座 12V 和 USB 约 10 秒，再接回。当前没有已验证的纯软件断电替代方式。
6. 自动核对本次板 UID（用于避免验证错板，无白名单）和三次完整读回，恢复临时寄存器。
7. 固定使用 SP 官方最新目录中的 Light Speed Model v2（2026-10-29，LSMV2），在 USB+AMD:LLVM 后端运行预处理后的合成模型输入。
   不启动摄像头或图像 warp。模型预热后持续推理至少 60 秒，保留循环状态，取回输出并检查有限值和 plan。
8. 记录成功/失败、速度和 hash。无 20 Hz 性能门槛。完成后等待移除底座再处理下一个。

R2 包为 wrapper，最终完整 256 KiB 镜像由本板数据合成，不能使用别人的完整镜像。
SPI 算法支持 JEDEC 854012、256 KiB、4 KiB 扇区和 128 字节页；不匹配不会执行未知擦写协议。
接入多个底座时等待只剩一个，以免刷错目标。

## 状态与证据

专用全屏状态页显示等待、预检、备份、64 扇区进度、三次回读、断电重接提示、加载、60 秒推理倒计时和最终结果。
显示进程只读取状态和事件文件，不访问底座。主流程先等待画面就绪，显示失败时不会开始刷写；耗时刷写与推理不会阻塞画面更新。
屏幕使用中文点阵资源和 libdrm；复用 magic.service 的 DRM 描述符交接，不修改系统服务。系统缺少 libdrm 时使用随包 ARM64 后备。
完成页仅显示通过结果、推理统计和“可移除底座”。程序 stdout 仍保留状态与进度。
`/data/sp-flasher/state.json` 是持久状态；每轮独立目录保存三份备份、目标、写后及重接后读回、
result.json、inference.json、report.json 和 SHA256SUMS。刷写成功、激活后回读、推理结果分别记录。
推理超时上限为 600 秒（包含加载），超时不重刷。失败保留全部文件，不自动恢复或重试不确定擦写。
程序重启会保留等待重接状态；写入/验证/推理途中重启标记失败，同次连接不重复刷写。

仅保留一套模型，文件 SHA-256：`9f70c95b846428d36f2f31b570b9e4c78cd24196864464801eb58dc30b0b79f8`。
模型和 LLVM 以不超过 45 MiB 的普通 Git 分块文件发布；无 Git LFS、无子模块。首次启动只在本地合成并验证完整文件，
否则完整性校验失败且不会开始擦写。无需 recursive clone 或 submodule update。
所有型号的 AMDGPU 微码来自 tinygrad 固定 hash 列表，覆盖该后端支持的 GPU，不额外绑定显卡型号。
模型来源、tinygrad 提交及 R2 hash 见 provenance.json；主机验证范围见 VALIDATION.md。

## 主机 E2E（不会打开 USB）

用安装了 NumPy 的 Python 3.11+，为每次验证选择一个不存在的新输出目录：

```sh
python3 e2e/spi_flow.py /absolute/new-evidence/spi
python3 e2e/workflow.py /absolute/new-evidence/workflow
python3 e2e/station_spi.py /absolute/new-evidence/integrated
python3 e2e/inference_flow.py /absolute/new-evidence/inference
python3 e2e/package.py /absolute/new-evidence/package.json
python3 e2e/runtime_flow.py /absolute/new-evidence/runtime-flow
python3 e2e/runtime_elf.py /absolute/new-evidence/runtime-elf.json
```

SPI 和流程为主机传输模拟。推理入口测试模拟 GPU 和时钟，验证 60 秒循环与错误结果，不证明真实推理速度或输出数值。

## 复现离线运行依赖（仅开发主机）

```sh
python3 tools/build_runtime.py /absolute/new-runtime-directory /absolute/archive-cache
```

开发脚本按 `runtime/sources.json` 中固定的 URL、SHA-256 重建目录；需要联网仅限开发阶段下载归档。
启动入口不会调用它。对照新目录的 SHA256SUMS 与随包 runtime/SHA256SUMS 可逐文件验证复现结果。

`python3 e2e/payload_checkout.py /absolute/new-checkout-evidence` 还可以验证当前 Git 暂存树的普通
文件能离线还原全部运行依赖；此测试不下载文件，也不执行 ARM64 程序。

## 显示验证（不刷底座）

```sh
python3 e2e/screen_flow.py /absolute/new-screen-evidence
python3 e2e/screen_startup.py /absolute/new-startup-evidence
python3 status_screen.py --state /path/to/state.json --snapshot /path/to/screen.ppm
```

在独占显示的 C3 上，单独运行 `status_screen.py` 只展示已有状态，不启动 station 或访问 USB。
`--capture /path/to/frame.ppm` 可在首帧呈现后保存显示缓冲区读回和状态 JSON。正常启动无需这些验证参数。

## Installer 发布状态

预期入口为 `https://installer.comma.ai/onemiless/sp-flasher`，对应公开仓库 `onemiless/openpilot` 的 `sp-flasher` 分支。
启动文件 `launch_openpilot.sh` 已保留，安装器的子模块初始化在本分支无子模块时无需下载子模块。
安装阶段通过普通 Git 获取模型与 LLVM 分块；启动阶段只在本地合成、验证和使用，不联网安装。
已发布到远端，并在 C3XL/AGNOS 19.9 上完成官方 installer 新克隆、完整资源校验、正常入口启动与等待页面验收；随后恢复原 xpilot。
不要将浏览器访问安装器地址返回 HTTP 200 当作分支存在或安装成功的证据。

GitHub LFS 预算超额时仍可安装：当前发布树不含 LFS 指针。`payload/targets.tsv` 固定完整模型与 LLVM 的哈希，
`payload/SHA256SUMS` 校验分块。合成过程先写临时文件、核对完整哈希，再原子替换目标；正确的现有目标直接复用。
普通 Git 分块与本地合成文件同时保留，需要为安装与运行预留约 3 GiB 空间，不含原系统和其他应用数据。

安装界面支持直接输入 `onemiless/sp-flasher`，会补全为上述 installer URL。安装时需要联网下载普通 Git 内容；
首次启动会离线合成模型和 LLVM。没有恢复出厂即可验证真实 installer 安装链路；本次设备测试使用 USB 隔离防止重刷，
只验证安装与启动。完整 R2 刷写和 60 秒真实 GPU 推理的独立实机证明见 VALIDATION.md。
