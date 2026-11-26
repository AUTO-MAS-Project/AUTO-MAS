# 发行版与源码共用开发后端

安装版默认使用发行后端、发行版 Python 环境与日常数据。通过环境变量 `AUTO_MAS_BACKEND_REPO` 启动时，安装版会直接加载本地开发源码，**复用同一个 Python 环境**并使用**独立的开发数据目录**，无需在源码目录另建 `.venv`。

## 启动方式

1. 先正常启动一次安装版完成初始化，然后退出。
2. 在**管理员 PowerShell** 中设置 `AUTO_MAS_BACKEND_REPO` 并启动安装版（Windows 安装版需要管理员权限，从普通终端启动会在 UAC 提权时丢失环境变量；应用不读取 `.env`）：

```powershell
$env:AUTO_MAS_BACKEND_REPO = '<AUTO-MAS 源码路径>'
& '<安装目录>\AUTO-MAS.exe'
```

也可用辅助脚本生成启动脚本；附加 `--copy-data` 会将日常配置与数据复制为独立测试副本（已有开发配置时拒绝覆盖）：

```powershell
python scripts/prepare-developer-backend.py --source . --base '<安装目录>' --copy-data
```

## 隔离与行为差异

- **数据与实例隔离**：使用源码侧独立配置和数据，开发端口默认 `36164`，浏览器数据、单实例锁和快捷键与日常实例分开。
- **自动调度默认暂停**：防止误触日常任务；如需测试自动调度，显式设置 `AUTO_MAS_DEVELOPER_AUTOMATION=1`。手动点击运行仍会执行配置里的真实脚本与账号。
- **Python 环境复用**：直接复用安装目录下的 `runtime/environment/venv`（不创建 `.venv`，不执行 `uv sync`），源码依赖须与发行环境兼容；插件依赖仍落在开发数据目录。
- **桌面更新与恢复日常模式**：开发模式下暂停桌面应用更新且禁报匿名统计。关闭开发实例后，从不含 `AUTO_MAS_BACKEND_REPO` 的环境正常启动即恢复日常模式。
- **未打包开发 Electron**：使用 `AUTO_MAS_BACKEND_RUNTIME_ROOT` 指定要复用的发行目录。

## 精简 worktree（可选）

新建 worktree 只检出源码。使用 PowerShell 7 和 PATH 中的 `uv` 进行检查或运行；以下入口不会调用 `uv sync`，也不会创建工作树 `.venv`。不使用共享环境的贡献者可以继续采用现有开发流程。AI 应先读 [mas-worktree](../.agents/skills/mas-worktree/SKILL.md)，在只读核对当前终端、Windows 用户与系统变量以及实际环境后再运行依赖相关命令；下面的准备示例不是 worktree 初始化步骤。若 AI 已误建 `.venv`，按 Skill 先验证保留环境及副本来源，再单独处理，默认不清理。

### 用一份专用测试包联调

准备一份包含 #2054 且打包时生成了 `resources/worktree-profile-isolation.json` 的完整 Windows 测试包。旧版测试包即使 Python 与 Runtime 兼容也不可用于这个入口，不要手工补该能力文件。把包存放在所有工作树和日常安装之外，在独立的 Windows 测试账号或虚拟机内完成首次正常启动和初始化后退出；随后手动创建专用测试包标记并登记：

```powershell
$testApp = 'D:\MAS-Test'
New-Item -ItemType File (Join-Path $testApp '.automas-dev-install')
git config --local automas.backendAppRoot $testApp
./scripts/dev-backend.ps1 Check
./scripts/dev-backend.ps1 Start
```

`-AppRoot` 可单次覆盖登记路径。仅 `Start` 需要管理员 PowerShell；工具不会自行提权、复制日常配置或打开自动任务开关。启动时才把 `AUTO_MAS_BACKEND_REPO` 传给子进程，Electron 在当前工作树的 `.automas-dev-electron/` 内取桌面锁并保存会话，不导入或回退到旧 `frontend-dev` 目录；后端使用该工作树的配置与数据库。不要将这些目录链接到其他工作树或日常安装，也不要把指向真实脚本的日常配置当作测试数据。开发后端使用 36164，`Start` 同一时间只允许一个实例；关闭前一个开发实例后再换工作树。若解释器或锁定的运行依赖不匹配，请另准备匹配的专用测试包；不要在现有包里同步依赖。

### 用独立共享环境运行 pytest

`AUTO_MAS_DEV_ENV_ROOT` 指向所有工作树和测试包之外的绝对目录（以下命令使用当前终端显式选定的值，不自动修改用户或系统设置；Windows 登记未继承时会明确提示，不使用本地环境替代）。`Check -Target Test` 会先输出由平台、架构、Python 版本和锁文件哈希生成的虚拟环境路径；没准备好会以非零退出。只有首次使用这个路径时，才由开发者显式同步依赖，不要把路径设为测试包中的运行环境：

```powershell
$env:AUTO_MAS_DEV_ENV_ROOT = 'D:\MAS-Test-Python'
./scripts/dev-backend.ps1 Check -Target Test

$previous = $env:UV_PROJECT_ENVIRONMENT
try {
    $env:UV_PROJECT_ENVIRONMENT = '<上一步输出的共享测试环境绝对路径>'
    uv sync --locked --group dev
    if ($LASTEXITCODE -ne 0) { throw '共享测试环境准备失败' }
} finally {
    $env:UV_PROJECT_ENVIRONMENT = $previous
}

./scripts/dev-backend.ps1 Test -PytestArgs @('tests/models/test_queue_config.py', '-q')
```

两个兼容工作树可复用上面同一解释器，`Test` 仍在当前工作树内运行；专项需要的插件 wheel 按 [测试文档](../tests/AGENTS.md) 使用该共享解释器准备，各工作树的 `.test-plugins` 不共用。锁文件变化后使用新的池路径，不迁移、不自动删除旧环境。不要把 `uv sync` 放进 worktree 初始化脚本。

已设置共享池时，可直接用 `python scripts/dev_doctor.py` 诊断；`python scripts/dev_doctor.py --init-vscode` 将同一预检确认的共享解释器写入调试配置。不兼容时不改配置、不建 `.venv`。该配置只启动独立开发后端；要用专用桌面测试包请走上面的 `Start`。

## 可选前端工具包

Developer Pro 前端工具包仅包含前端源码、Node、Yarn 与前端依赖，直接连接上述源码后端，不复制 Python 环境也不修改后端代码。
