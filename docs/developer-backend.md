# 发行版与源码共用开发后端

安装版默认使用发行后端、发行版 Python 环境与日常数据。通过环境变量 `AUTO_MAS_BACKEND_REPO` 启动时，安装版会直接加载本地开发源码，**复用同一个 Python 环境**并使用**独立的开发数据目录**，无需在源码目录另建 `.venv`。

## 启动方式

1. 先正常启动一次安装版完成初始化，然后从系统托盘退出。
2. 双击源码根目录的 `启动源码后端.cmd`，确认 Windows 的管理员提示，再选择要使用的发行版 `AUTO-MAS.exe`。

也可在**管理员 PowerShell** 中手动设置 `AUTO_MAS_BACKEND_REPO` 并启动安装版。先提权能让桌面程序继承当前终端里的环境变量。

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

## 可选前端工具包

Developer Pro 前端工具包仅包含前端源码、Node、Yarn 与前端依赖，直接连接上述源码后端，不复制 Python 环境也不修改后端代码。
