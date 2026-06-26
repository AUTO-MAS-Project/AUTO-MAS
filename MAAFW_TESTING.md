# MaaFW 适配测试清单

本清单用于在测试机验证 MAS 的 MaaFW 项目适配、脚本页 Mirror 酱 CDK、运行前自动更新，以及 M9A / MAAbbb 实际目录兼容性。

模块原理和使用说明见 [MAAFW_MODULE_GUIDE.md](MAAFW_MODULE_GUIDE.md)。

## 测试前准备

1. 拉取当前分支并安装依赖。
2. 准备两个 MaaFW 项目目录：
   - `Maa_bbb-win-x86_64-v1.12.5`
   - `M9A-win-x86_64-v3.22.1`
3. 在 MAS 全局更新配置里填写 Mirror 酱 CDK；没有 CDK 时也要测空 CDK 的失败提示。
4. 准备一个可用的 ADB 模拟器或 PC 窗口环境，按项目实际 controller 选择。

## 基础回归

在仓库根目录运行：

```powershell
python -m pytest tests\test_maafw_interface_loader.py
python -m compileall app\task\MaaFW app\models\config.py app\models\schema.py app\core\config.py app\api\scripts.py app\core\task_manager.py
```

在 `frontend` 目录运行：

```powershell
yarn eslint src/views/EditView/Script/MaaFWScriptEdit.vue
yarn vite build
```

预期：

- MaaFW loader 单测通过。
- Python compileall 通过。
- MaaFW 脚本编辑页 eslint 通过。
- Vite build 通过。

## 脚本页 CDK

1. 新建 MaaFW 脚本。
2. 打开脚本编辑页，确认 `Mirror 酱 CDK` 默认带入全局更新 CDK。
3. 清空脚本自己的 CDK，保存后运行一次。
4. 填写一个脚本专用 CDK，保存后运行一次。

预期：

- 新建脚本时自动带入全局 CDK。
- 脚本 CDK 为空时，运行前更新使用全局 CDK。
- 脚本 CDK 不为空时，优先使用脚本 CDK。
- CDK 错误或网络失败时有日志提示，并继续使用当前项目目录运行。

## 实际项目加载

分别创建两个 MaaFW 脚本，项目路径指向 MAAbbb 和 M9A 目录。

MAAbbb 需要确认：

- controller 至少包含 `桌面端`、`安卓端`。
- resource 至少包含 `键鼠操作`。
- preset 至少有 3 个。
- 任务列表能加载并保存勾选状态。

M9A 需要确认：

- controller 至少包含 `ADB`、`PC`。
- resource 至少包含 `官服`。
- preset 至少有 4 个。
- 任务列表能加载并保存勾选状态。

## 运行前自动更新

对 MAAbbb 和 M9A 都测一轮：

1. 开启 `运行前自动更新 MaaFW 项目目录`。
2. 运行任务，观察日志顺序。
3. 关闭该开关，再运行任务。

预期：

- 开启时先检查项目更新，再重新读取 `interface.json`，最后加载 MaaFW resource。
- 关闭时不做更新检查。
- 更新失败时记录原因，并继续使用当前目录。

## M9A 资源热更时序

1. 使用 M9A 运行一次，观察 agent 日志是否提示 manifest 或资源更新。
2. 如果这次运行触发了资源更新，立刻再运行第二次。

预期：

- 第一次如果 agent 在启动后更新了 `resource/`，本次任务不保证使用新资源。
- 第二次运行应能使用更新后的资源。
- 这是当前已知时序风险：MAS 在 agent 启动前已经完成 `Resource.post_bundle()`。

## MAAbbb Agent 启动

1. 使用 MAAbbb 运行一次。
2. 观察 agent 启动日志和依赖检查日志。

重点观察：

- 当前 `Maa_bbb-win-x86_64-v1.12.5` 包内可能没有 `python\python.exe`。
- MAS 可能回退到 AUTO-MAS 当前 Python。
- 如果当前 Python 缺依赖，agent 启动或依赖检查可能失败。

这是当前 embedded agent 适配尚未完整对齐 MWU / MFW-PyQt6 的关键验证点。

## 测试记录

建议记录以下信息：

- MAS commit hash。
- 测试机系统版本。
- MAAbbb / M9A 包版本和路径。
- 是否填写 Mirror 酱 CDK。
- 自动更新开关状态。
- 运行日志中更新检查、资源加载、agent 启动的顺序。
- 失败时的完整错误日志。
