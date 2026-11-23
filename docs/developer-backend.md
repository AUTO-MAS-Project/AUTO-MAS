# 发行版与源码共用开发后端

正常启动时，MAS 使用发行后端、发行版 Python 环境和日常数据。设置 `AUTO_MAS_BACKEND_REPO` 启动时，使用开发源码、同一个 Python 环境和独立的开发数据。前端开发工具按需单独安装。

## 只开发后端

先正常启动发行版完成初始化。随后退出，并在管理员 PowerShell 中设置环境变量启动：

```powershell
$env:AUTO_MAS_BACKEND_REPO = 'D:\src\AUTO-MAS'
& 'D:\Apps\AUTO-MAS\AUTO-MAS.exe'
```

必须使用包含本改动的新安装版。旧发行包不识别源码路径，不能只更新 Python 后端获得此能力。应用不自动读取 `.env`。Windows 安装版要求管理员权限，须在管理员终端中设置变量并启动，避免 UAC 重新启动后丢失变量。

使用源码自己的配置和数据，开发端口默认 36164，浏览器数据、单实例和快捷键与日常实例分开。默认暂停自动调度；需要测试自动任务时显式设置 `AUTO_MAS_DEVELOPER_AUTOMATION=1`。手动执行仍会操作配置里的真实脚本及账号。

## 共用环境与数据隔离

开发启动使用安装目录下已经存在的 `runtime/environment/venv`，启动时不创建源码 `.venv`，也不执行 `uv sync`。源码使用的依赖必须与已初始化的发行环境兼容。插件仍按已有流程使用开发数据目录下的插件依赖，首次可能需要联网。

可选的准备命令会生成启动脚本。带 `--copy-data` 时将当前配置和数据复制为独立的测试副本；已有开发配置时拒绝覆盖。

```powershell
python scripts/prepare-developer-backend.py --source . --base D:\Apps\AUTO-MAS --copy-data
```

共用 Runtime 根的实例按顺序启动。关闭开发实例后，从未设置 `AUTO_MAS_BACKEND_REPO` 的终端启动原程序，即恢复日常模式。

开发后端模式暂停桌面应用更新。需要更新安装包时，先退出开发模式，再正常启动发行版进行更新。

直接使用未打包的开发 Electron 时，工具包通过 `AUTO_MAS_BACKEND_RUNTIME_ROOT` 指定要复用的发行目录。

## 可选前端工具

Developer Pro 的前端工具包只携带前端源码、Node、Yarn 和前端依赖。它连接/启动这里定义的源码后端，既不复制 Python 环境，也不附带 Python 开发依赖或修改后端代码。后端环境准备与数据隔离归主仓库负责。

开发模式不采集使用统计，正常模式仍沿用现有统计开关。后端启动成功、失败、关闭继续由既有 Runtime 监督链路确认，不新增路径、环境内容或源码标识的采集。
