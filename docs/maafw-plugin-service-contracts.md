# MaaFW 插件服务契约与调用示例

> 契约版本：v1  
> 对应 AUTO-MAS 合并：`AUTO-MAS-Project/AUTO-MAS#290`  
> 适用范围：MaaFW ProjectInterfaceV2 插件组及 M9A project pack

## 1. 目标与兼容原则

本文档描述 MaaFW 插件组向 AUTO-MAS 宿主及其他插件公开的服务名、方法、输入输出模型和调用方法。

兼容原则：

- 以服务注册表中的服务名作为跨插件边界，不依赖插件实例或内部模块。
- 带 `.v1` 后缀的服务名代表稳定契约版本；破坏性变更应注册新的 `.v2` 服务。
- 不以下划线开头的 service 方法属于公开调用面；`_` 开头的函数和 runner 内部类不保证兼容。
- 输入模型通常同时接受 Pydantic 模型和等价 `dict`，输出优先使用明确的 Pydantic 模型或 dataclass。
- 调用方必须处理服务未加载的情况，不能假定某个可选插件始终启用。
- 新增未知 ProjectInterface 字段时，已支持的 task、option 和 preset 应继续工作；未知字段只记录后台警告。

## 2. 通用服务获取方式

宿主或普通模块通过全局服务注册表获取服务：

```python
from typing import Any

from app.plugins.manager import PluginManager


def require_plugin_service(name: str) -> Any:
    service = PluginManager.service.get(name)
    if service is None:
        raise RuntimeError(f"插件服务未加载: {name}")
    return service
```

插件实例内部优先通过 `PluginContext` 获取：

```python
class Plugin:
    def __init__(self, ctx):
        self.ctx = ctx

    async def on_start(self) -> None:
        interface_service = self.ctx.get("maafw.interface.v1")
        if interface_service is None:
            raise RuntimeError("缺少 maafw.interface.v1")
```

服务调用属于进程内 Python 契约，不是 HTTP API。业务异常默认向调用方抛出，由 API 或任务边界转换为用户可见结果。

## 3. 插件与服务总览

| PyPI 包 | 当前版本 | 服务名 | 主要职责 |
|---|---:|---|---|
| `automas-maafw-interface` | 0.1.1 | `maafw.interface.v1` | PI 加载、校验、预览、任务快照和 option 归一化 |
| `automas-maafw-project-update` | 0.1.0 | `maafw.project_update.v1` | MirrorChyan/GitHub Release 检查与更新 |
| `automas-maafw-agent-env` | 0.1.0 | `maafw.agent_env.v1` | agent 运行方式识别、命令规划和 Python 环境准备 |
| `automas-maafw-controller-adb` | 0.1.0 | `maafw.controller.adb` | ADB provider 与设备参数构建 |
| `automas-maafw-controller-win32` | 0.1.0 | `maafw.controller.win32` | Win32 provider、窗口扫描与设备参数构建 |
| `automas-maafw-runner` | 0.1.1 | `maafw.runner.v1` | 运行计划、worker job、环境和结果模型 |
| `automas-script-maafw` | 0.1.1 | `maafw.registry.v1` | MaaFW 脚本适配与 controller/project pack 注册表 |
| `automas-script-maafw-pack-m9a` | 0.1.0 | `maafw.pack.m9a.v1` | M9A 默认约定、通知翻译和旧配置迁移草稿 |
| `automas-m9a` | 0.1.0 | 无 | 聚合安装上述 MaaFW/M9A 插件 |

## 4. `maafw.interface.v1`

### 4.1 公开方法

```python
load(path, *, force_reload=False) -> MaaFWInterface

preview(path, *, force_reload=False) -> MaaFWInterfacePreviewData

validate(interface) -> MaaFWInterfaceValidationReport

build_default_snapshot(
    interface,
    *,
    preset=None,
) -> MaaFWTaskPresetSnapshot

normalize_snapshot(
    interface,
    snapshot,
) -> MaaFWTaskPresetSnapshot

normalize_execution_payload(
    interface,
    tasks,
    options,
    *,
    controller=None,
    resource=None,
) -> tuple[list[str], dict[str, dict[str, Any]]]

rescan_option(path, option_name) -> list[dict[str, str]]
```

### 4.2 ProjectInterface 主字段

`MaaFWInterface` 支持以下顶层字段：

```text
interface_version
languages
name / label / title / icon
mirrorchyan_rid / mirrorchyan_multiplatform
github / version / contact / license
welcome / description
controller
resource
group
pretask
agent
task
option
global_option
import
preset
```

`pretask` 字段：

```text
name
label
description
icon
exec
args
option
resource
controller
```

`MaaFWTaskPresetSnapshot` 字段：

```text
taskOrder: list[str]
taskChecked: dict[str, bool]
taskOptions: dict[str, dict[str, Any]]
```

校验和预览输出：

```text
MaaFWInterfaceValidationReport:
  ok: bool
  message: str

MaaFWInterfacePreviewData:
  path: str
  project: dict[str, Any]
  globalOption: list[str]
  controllers: list[dict[str, Any]]
  resources: list[dict[str, Any]]
  groups: list[dict[str, Any]]
  tasks: list[dict[str, Any]]
  options: list[dict[str, Any]]
  presets: list[dict[str, Any]]
  importCount: int
  agentCount: int
  controlCapabilities: dict[str, Any]
```

当前由 AUTO-MAS 配置界面支持的 option 类型：

```text
select
checkbox
input
switch
scan_select
```

`hotkey`、`setting` 和未来未知类型不进入前端配置界面，只记录后台警告，不阻断已支持任务的加载、编辑和执行。`hotkey` 应由用户在原项目或原应用中配置。

### 4.3 pretask 语义

- pretask 在用户手动加入任务队列后才执行，不是项目加载时自动执行。
- pretask 与普通 task 共用 `taskOrder` 和 `taskChecked`。
- 运行计划中转换为 `MaaFWPretaskRunPlan`。
- 桌面项目执行顺序为：根据 MAS `Game.Path` 启动应用，执行已选择的 pretask，再执行 MaaFW task。
- AUTO-MAS 不为 pretask 增加独立持久化页面。

### 4.4 调用示例：加载、校验和生成默认快照

```python
from pathlib import Path

interface_service = require_plugin_service("maafw.interface.v1")
project_path = Path(r"D:\MaaEnd")

interface = interface_service.load(project_path)
report = interface_service.validate(interface)
if not report.ok:
    raise ValueError(report.message)

snapshot = interface_service.build_default_snapshot(
    interface,
    preset="日常任务",
)

print(snapshot.taskOrder)
print(snapshot.taskChecked)
print(snapshot.taskOptions)
```

### 4.5 调用示例：归一化实际执行任务

```python
task_names, task_options = interface_service.normalize_execution_payload(
    interface,
    tasks=["StartUp", "Psychube"],
    options={
        "Psychube": {
            "difficulty": "hard",
        },
    },
    controller="adb",
    resource="resource",
)
```

### 4.6 调用示例：重新扫描 `scan_select`

```python
choices = interface_service.rescan_option(
    project_path,
    option_name="account",
)

# 返回示例：[{"name": "account-1", "label": "账号一"}]
```

校验失败或 `interface.json` 无法加载时可能抛出 `MaaFWInterfaceLoadError`；`validate()` 会把模型校验异常转换为 `ok=False` 的报告。

## 5. `maafw.project_update.v1`

### 5.1 公开方法

```python
list_providers() -> list[MaaFWUpdateProviderInfo]

await check_update(
    interface,
    *,
    current_version=None,
    source_config=None,
    proxy=None,
    send_log=None,
) -> MaaFWProjectUpdateCandidate | None

await apply_update(
    project_path,
    candidate,
    *,
    proxy=None,
    send_log=None,
) -> None

await update_if_needed(
    project_path,
    interface,
    *,
    mirror_cdk="",
    channel="stable",
    proxy=None,
    send_log=None,
    source_config=None,
) -> MaaFWProjectUpdateResult
```

### 5.2 输入字段

`source_config` 常用字段：

```text
source: mirrorchyan | github_release
channel
mirror_cdk / cdk
github_repo
github_tag
github_token
github_asset_pattern
sha256
```

### 5.3 输出模型

```text
MaaFWUpdateProviderInfo:
  name: str
  label: str
  description: str

MaaFWProjectUpdateCandidate:
  source: str
  version: str
  download_url: str | None
  sha256: str | None

MaaFWProjectUpdateResult:
  checked: bool
  updated: bool
  current_version: str
  latest_version: str | None
  source: str | None
  message: str
```

### 5.4 调用示例：检查并应用更新

```python
update_service = require_plugin_service("maafw.project_update.v1")

candidate = await update_service.check_update(
    interface,
    current_version="v2.19.0-beta.5",
    source_config={
        "source": "mirrorchyan",
        "channel": "stable",
        "mirror_cdk": "",
    },
    send_log=print,
)

if candidate is not None:
    await update_service.apply_update(
        project_path,
        candidate,
        send_log=print,
    )
```

简化调用：

```python
result = await update_service.update_if_needed(
    project_path,
    interface,
    channel="stable",
    source_config={"source": "mirrorchyan"},
    send_log=print,
)

if result.updated:
    print(f"已更新至 {result.latest_version}")
```

更新检查或应用失败抛出 `MaaFWProjectUpdateError`。调用方不得在更新失败后把项目版本写成候选版本。

## 6. `maafw.agent_env.v1`

### 6.1 公开方法

```python
classify(agent) -> str

build_command_plans(
    project_path,
    interface_or_agent,
    *,
    managed_env_root=None,
) -> list[MaaFWAgentCommandPlan]

prepare_env(
    project_path,
    interface_or_agent,
    *,
    managed_env_root=None,
    send_log=None,
    bootstrap_python=None,
    install_dependencies=True,
) -> MaaFWAgentEnvPrepareResult
```

运行类型：

```text
embedded
project_python
project_binary
isolated_venv
external
```

### 6.2 输出字段

```text
MaaFWAgentCommandPlan:
  childExec: str
  executable: str
  executableExists: bool | None
  fallbackReason: str | None
  runtimeKind: str | None
  isolatedVenvPath: str | None
  childArgs: list[str]
  command: list[str]
  cwd: str
  identifier: str | None
  embedded: bool

MaaFWAgentEnvPrepareResult:
  projectPath: str
  plans: list[MaaFWAgentCommandPlan]
  preparedVenvs: list[str]
  skipped: list[str]
  messages: list[str]
```

`interface_or_agent` 可以传完整 `MaaFWInterface`，也可以传单个 agent 或 agent 列表。单个 `MaaFWAgent` 的标准字段为：

```text
child_exec: str
child_args: list[str] | None
identifier: str | None
embedded: bool | None
```

### 6.3 调用示例

```python
agent_service = require_plugin_service("maafw.agent_env.v1")

plans = agent_service.build_command_plans(
    project_path,
    interface,
    managed_env_root=r"D:\AUTO-MAS\agent-envs",
)

for plan in plans:
    print(plan.runtimeKind, plan.command)

prepare_result = agent_service.prepare_env(
    project_path,
    interface,
    managed_env_root=r"D:\AUTO-MAS\agent-envs",
    bootstrap_python=r"C:\Python312\python.exe",
    install_dependencies=True,
    send_log=print,
)
```

只想预览命令时应调用 `build_command_plans()`，不要调用会创建环境和安装依赖的 `prepare_env()`。

## 7. `maafw.controller.adb`

### 7.1 Provider 契约

```text
key: adb
displayName: ADB
controllerTypes: ["Adb"]
capabilities:
  - device_spec
  - emulator_service_consumption
```

### 7.2 公开方法

```python
get_provider_definition() -> dict[str, Any]

build_device_spec(
    *,
    adb_path=None,
    address=None,
    screencap_methods=0,
    input_methods=0,
    config=None,
) -> dict[str, Any]
```

设备输出字段：

```text
type: "Adb"
adbPath
address
screencapMethods
inputMethods
config
```

### 7.3 调用示例

```python
adb_service = require_plugin_service("maafw.controller.adb")

device_spec = adb_service.build_device_spec(
    adb_path=r"C:\Android\platform-tools\adb.exe",
    address="127.0.0.1:5555",
    screencap_methods=0,
    input_methods=0,
    config={
        "extras": {
            "mumu": {},
        },
    },
)
```

## 8. `maafw.controller.win32`

### 8.1 Provider 契约

```text
key: win32
displayName: Win32
controllerTypes: ["Win32"]
capabilities:
  - window_scan
  - device_spec
```

### 8.2 公开方法

```python
get_provider_definition() -> dict[str, Any]

list_windows() -> list[MaaFWWin32Window]

match_controller_windows(
    controller,
    windows=None,
) -> list[MaaFWWindowMatch]

build_device_spec(
    *,
    h_wnd=None,
    screencap_method=0,
    mouse_method=0,
    keyboard_method=0,
) -> dict[str, Any]
```

输出字段：

```text
MaaFWWin32Window:
  hWnd: int
  className: str
  windowName: str

MaaFWWindowMatch:
  hWnd: int
  className: str
  windowName: str
  controllerName: str
  controllerType: str
```

### 8.3 调用示例：按 PI controller 匹配窗口

```python
win32_service = require_plugin_service("maafw.controller.win32")

matches = win32_service.match_controller_windows(
    {
        "name": "endfield",
        "label": "终末地",
        "type": "Win32",
        "win32": {
            "class_regex": ".*",
            "window_regex": ".*Endfield.*",
        },
    }
)

if not matches:
    raise RuntimeError("未找到匹配的游戏窗口")

device_spec = win32_service.build_device_spec(
    h_wnd=matches[0].hWnd,
    screencap_method=0,
    mouse_method=0,
    keyboard_method=0,
)
```

`list_windows()` 仅支持 Windows。窗口正则有长度和嵌套量词限制，非法或高风险表达式会抛出 `RuntimeError`。

## 9. `maafw.runner.v1`

### 9.1 公开方法

```python
build_plan(
    project_path,
    interface,
    *,
    controller_name=None,
    resource_name=None,
    selected_preset=None,
    task_snapshot=None,
    task_names=None,
    task_options=None,
    managed_env_root=None,
) -> MaaFWRunPlan

create_job_payload(
    plan,
    device_config,
) -> MaaFWRunnerJobPayload

prepare_environment(
    project_path,
    *,
    managed_env_root=None,
    import_paths=None,
    send_log=None,
) -> MaaFWRunnerEnvironment

write_job_file(
    payload,
    work_dir,
    *,
    job_name=None,
) -> Path

run_worker(
    payload,
    *,
    work_dir,
    worker_command=None,
    send_log=None,
    timeout=None,
) -> MaaFWRunResult
```

### 9.2 运行计划字段

```text
MaaFWRunPlan:
  path: str
  projectName: str
  projectLabel: str | None
  controllerName: str
  controllerType: str
  resourceName: str
  resource: MaaFWResourceBundlePlan
  agents: list[MaaFWAgentCommandPlan]
  pretasks: list[MaaFWPretaskRunPlan]
  piEnv: dict[str, str]
  tasks: list[MaaFWTaskRunPlan]
  skippedTasks: list[MaaFWSkippedTaskPlan]

MaaFWResolvedPath:
  raw: str
  resolved: str
  exists: bool
  isFile: bool
  isDir: bool

MaaFWResourceBundlePlan:
  name: str
  label: str | None
  paths: list[MaaFWResolvedPath]
  attachedPaths: list[MaaFWResolvedPath]

MaaFWPretaskRunPlan:
  name: str
  label: str | None
  executable: str
  args: list[str]
  options: dict[str, Any]

MaaFWTaskRunPlan:
  name: str
  label: str | None
  entry: str
  options: dict[str, Any]
  pipelineOverride: dict[str, Any]
  logOptions: dict[str, Any]
  overrideNodes: list[str]

MaaFWSkippedTaskPlan:
  name: str
  label: str | None
  entry: str | None
  reason: str
```

设备模型：

```text
MaaFWDeviceConfig:
  type: Adb | Win32
  adbPath: str | None
  address: str | None
  hWnd: int | None
  screencapMethods: int
  inputMethods: int
  screencapMethod: int
  mouseMethod: int
  keyboardMethod: int
  config: dict[str, Any]
```

运行结果：

```text
MaaFWRunResult:
  success: bool
  projectName: str
  controllerName: str
  resourceName: str
  completedTasks: list[str]
  failedTask: str | None
  errorMessage: str | None
```

`prepare_environment()` 返回：

```text
MaaFWRunnerEnvironment:
  python_executable: Path
  venv_path: Path
  env: dict[str, str]
  packages: tuple[str, ...]
  maafw_version: str | None
```

### 9.3 调用示例：构建并执行 worker job

```python
runner_service = require_plugin_service("maafw.runner.v1")
adb_service = require_plugin_service("maafw.controller.adb")

plan = runner_service.build_plan(
    project_path,
    interface,
    controller_name="adb",
    resource_name="resource",
    task_snapshot={
        "taskOrder": ["StartUp", "Psychube"],
        "taskChecked": {
            "StartUp": True,
            "Psychube": True,
        },
        "taskOptions": {},
    },
)

device_config = adb_service.build_device_spec(
    adb_path=r"C:\Android\platform-tools\adb.exe",
    address="127.0.0.1:5555",
)

payload = runner_service.create_job_payload(
    plan,
    device_config,
)

result = runner_service.run_worker(
    payload,
    work_dir=r"D:\AUTO-MAS\runtime",
    send_log=print,
    timeout=3600,
)

if not result.success:
    raise RuntimeError(result.errorMessage or "MaaFW 运行失败")
```

### 9.4 worker JSON Lines 协议

```json
{"type": "log", "message": "正在连接设备"}
{"type": "result", "data": {"success": true}}
{"type": "error", "message": "运行异常"}
```

退出码：

```text
0  正常成功
2  worker 正常结束，但任务结果失败
1  worker 未处理异常
64 参数错误
```

PI 环境变量：

```text
PI_INTERFACE_VERSION=v2.8.1
PI_CLIENT_NAME
PI_CLIENT_VERSION
PI_CLIENT_LANGUAGE=zh_cn
PI_CLIENT_MAAFW_VERSION
PI_VERSION
PI_CONTROLLER
PI_RESOURCE
```

## 10. `maafw.registry.v1`

该服务由 `automas-script-maafw` 提供，用于动态组合 controller provider 和 project pack。

### 10.1 公开方法

```python
register_controller_provider(definition) -> None
unregister_controller_provider(key) -> None
list_controller_providers() -> list[dict[str, Any]]
get_controller_provider(key) -> dict[str, Any] | None

register_project_pack(definition) -> None
unregister_project_pack(key) -> None
list_project_packs() -> list[dict[str, Any]]
get_project_pack(key) -> dict[str, Any] | None
```

### 10.2 调用示例：读取已注册能力

```python
registry = require_plugin_service("maafw.registry.v1")

for provider in registry.list_controller_providers():
    print(provider["key"], provider["capabilities"])

m9a_pack = registry.get_project_pack("m9a")
if m9a_pack is not None:
    print(m9a_pack["default_controller"])
```

### 10.3 调用示例：插件注册 controller provider

```python
class CustomControllerPlugin:
    def __init__(self, ctx):
        self.ctx = ctx
        self.key = "custom-controller"

    async def on_start(self) -> None:
        registry = self.ctx.get("maafw.registry.v1")
        if registry is None:
            return

        registry.register_controller_provider(
            {
                "key": self.key,
                "displayName": "Custom Controller",
                "controllerTypes": ["Custom"],
                "capabilities": ["device_spec"],
            }
        )

    async def on_stop(self, reason: str) -> None:
        registry = self.ctx.get("maafw.registry.v1")
        if registry is not None:
            registry.unregister_controller_provider(self.key)
```

注册项必须有非空 `key`；相同 `key` 的后一次注册会覆盖前一次定义。插件卸载时必须注销自己注册的 provider 或 pack。

## 11. MaaFW 脚本配置契约

`automas-script-maafw` 注册脚本类型 `MaaFW`，适配器生命周期为：

```python
await check(runtime) -> str
await prepare(runtime) -> None
run_auto_proxy(runtime) -> TaskExecuteBase
await finalize(runtime) -> None
await on_crash(runtime, error) -> None
```

脚本配置字段：

```text
Info:
  Name, ProjectLabel, Path, Controller, Resource

Emulator:
  Id, Index

Device:
  AdbPath, AdbAddress
  AdbScreencapMethods, AdbInputMethods
  HWnd
  Win32ScreencapMethod, Win32MouseMethod, Win32KeyboardMethod
  GamepadType
  PlayCoverAddress, PlayCoverUuid

Game:
  Path, Arguments, WaitTime, CloseOnFinish

Update:
  IfAutoUpdate, Source, Channel
  MirrorChyanCDK
  GitHubRepo, GitHubTag, GitHubAssetPattern

Run:
  ProxyTimesLimit, RunTimesLimit, RunTimeLimit
  DailyOnceTasks, WeeklyOnceTasks, MonthlyOnceTasks
```

用户配置字段：

```text
Info:
  Name, Status, RemainedDay
  IfScriptBeforeTask, ScriptBeforeTask
  IfScriptAfterTask, ScriptAfterTask
  Notes, Account, Password
  Controller, Resource

Task:
  SelectedPreset, TaskSnapshot

Device:
  AdbAddress, HWnd
  PlayCoverAddress, PlayCoverUuid

Data:
  LastProxyDate, ProxyTimes, IfPassCheck
  LastProxyStatus, PeriodTaskRecords

Notify:
  Enabled, IfSendStatistic
  IfSendMail, ToAddress
  IfServerChan, ServerChanKey
  CustomWebhooks
```

脚本适配器通常由 AUTO-MAS 的任务管理器创建，其他插件不应直接实例化内部 `MaaFWPluginAutoProxyTask`。

## 12. `maafw.pack.m9a.v1`

### 12.1 公开方法

```python
get_definition() -> M9APackDefinition

translate_notification(
    result,
    *,
    script_name="M9A",
    user_name="",
    started_at=None,
    ended_at=None,
) -> M9ANotificationContent

create_migration_draft(
    old_script_config,
    old_user_configs=None,
    *,
    script_name="M9A",
) -> M9AMigrationDraft
```

### 12.2 Pack 字段

```text
M9APackDefinition:
  key
  display_name
  project_repo
  interface_path
  supported_controllers
  default_controller
  default_resource
  default_preset
  default_task_queue
  period_rules
  reserved_task_semantics
  icon
  notes
  framework
  capabilities
```

默认周期规则：

```text
Psychube: daily
SleepDream: monthly
```

通知输出：

```text
M9ANotificationContent:
  title: str
  text: str
  html: str | None
```

迁移输出：

```text
M9AMigrationDraft:
  script: dict[str, Any]
  users: list[dict[str, Any]]
  warnings: list[str]
```

### 12.3 调用示例：读取 M9A 默认约定

```python
m9a_service = require_plugin_service("maafw.pack.m9a.v1")
definition = m9a_service.get_definition()

print(definition.project_repo)
print(definition.default_task_queue)
print(definition.period_rules)
```

### 12.4 调用示例：生成通知内容

```python
notification = m9a_service.translate_notification(
    {
        "success": False,
        "completedTasks": ["StartUp"],
        "failedTask": "Psychube",
        "errorMessage": "任务执行失败",
    },
    script_name="M9A 日常",
    user_name="账号一",
    started_at="2026-07-11 09:00:00",
    ended_at="2026-07-11 09:05:00",
)

print(notification.title)
print(notification.text)
```

### 12.5 调用示例：生成旧配置迁移草稿

```python
draft = m9a_service.create_migration_draft(
    old_script_config={
        "Info": {
            "Name": "旧 M9A",
            "Path": r"D:\M9A",
        },
        "Run": {
            "IfAutoUpdateAfterQueue": True,
            "WeeklyOnceTasks": [],
            "MonthlyOnceTasks": ["SleepDream"],
        },
    },
    old_user_configs=[
        {
            "Info": {"Name": "账号一"},
            "Task": {"Queue": ["StartUp", "Psychube"]},
            "Notify": {"Enabled": True},
        }
    ],
    script_name="M9A 插件版",
)

# draft 只用于创建新 PluginScriptConfig/PluginUserConfig，不能覆盖旧配置。
print(draft.script)
print(draft.users)
print(draft.warnings)
```

## 13. `automas-m9a` 聚合包

`automas-m9a` 没有运行时代码、插件 entry point 或独立服务。它只用于一次安装完整的 M9A 依赖集合。

发布到 PyPI 后可通过聚合包安装：

```powershell
python -m pip install automas-m9a
```

当前 pretask 支持相关的最低版本应为：

```text
automas-maafw-interface >= 0.1.1
automas-maafw-runner >= 0.1.1
automas-script-maafw >= 0.1.1
```

## 14. 完整调用示例

以下示例串联 PI 加载、项目更新、agent 环境、运行计划和 worker：

```python
from pathlib import Path

from app.plugins.manager import PluginManager


def require_service(name: str):
    service = PluginManager.service.get(name)
    if service is None:
        raise RuntimeError(f"插件服务未加载: {name}")
    return service


async def run_maafw_project() -> None:
    project_path = Path(r"D:\MaaEnd")

    interface_service = require_service("maafw.interface.v1")
    update_service = require_service("maafw.project_update.v1")
    agent_service = require_service("maafw.agent_env.v1")
    adb_service = require_service("maafw.controller.adb")
    runner_service = require_service("maafw.runner.v1")

    interface = interface_service.load(project_path)
    validation = interface_service.validate(interface)
    if not validation.ok:
        raise ValueError(validation.message)

    update_result = await update_service.update_if_needed(
        project_path,
        interface,
        channel="stable",
        source_config={"source": "mirrorchyan"},
        send_log=print,
    )
    if update_result.updated:
        interface = interface_service.load(
            project_path,
            force_reload=True,
        )

    agent_service.prepare_env(
        project_path,
        interface,
        install_dependencies=True,
        send_log=print,
    )

    snapshot = interface_service.build_default_snapshot(interface)
    plan = runner_service.build_plan(
        project_path,
        interface,
        controller_name="adb",
        resource_name="resource",
        task_snapshot=snapshot.model_dump(mode="json"),
    )

    device_spec = adb_service.build_device_spec(
        adb_path=r"C:\Android\platform-tools\adb.exe",
        address="127.0.0.1:5555",
    )
    payload = runner_service.create_job_payload(plan, device_spec)
    result = runner_service.run_worker(
        payload,
        work_dir=r"D:\AUTO-MAS\runtime",
        send_log=print,
        timeout=3600,
    )

    if not result.success:
        raise RuntimeError(result.errorMessage or "MaaFW 运行失败")
```

## 15. 变更规则

以下改动可以保留当前服务版本：

- 为返回模型增加有默认值的可选字段。
- 增加新的公开方法。
- 增加新的 provider capability。
- 支持新的 ProjectInterface 字段，同时保留未知字段容错。

以下改动必须升级服务版本：

- 删除或重命名公开方法。
- 修改现有参数含义、必填性或返回类型。
- 删除现有模型字段。
- 改变 worker JSON Lines 事件结构或退出码语义。
- 将原本只警告的未知 PI 字段改为阻断加载。

调用方迁移到新版本前，可以同时注册并保留旧服务，例如同时提供 `maafw.interface.v1` 和 `maafw.interface.v2`。
