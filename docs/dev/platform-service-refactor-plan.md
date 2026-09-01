# 平台能力服务重构方案

> 适用分支：`refactor/Win32-Cleanup`
>
> 目标：在 `app/platform` 建立低于 `utils/models/services` 的平台基础设施层，明确区分“程序能够导入/启动”和“当前平台支持某项功能”，逐步收拢散落在入口、任务与工具模块中的 OS 判断和 Win32 实现。

## 1. 背景

当前重构通过条件导入和 `sys.platform` 判断，解除了主程序对 `pywin32` 的启动期硬依赖，但平台支持语义仍分散在多个模块中：

- 有的功能在非 Windows 平台静默返回；
- 有的返回 `False` 或 `None`；
- 有的抛出普通 `RuntimeError`；
- 安全存储会退化为可逆 Base64 编码；
- 入口、定时器、MaaFW、OCR、进程管理、模拟器和配置层都需要了解当前操作系统。

因此，当前状态更准确的描述是“允许非 Windows 环境完成导入和部分启动”，还不能视为完整的多平台支持。

本方案不引入囊括所有系统操作的 `MultiPlatformBase`。平台差异按能力建模，由平台组合根选择具体实现；业务模块依赖能力接口，不依赖操作系统名称。

## 2. 设计目标

1. 所有平台识别和平台实现选择集中在 `app/platform/`。
2. 每个平台显式声明已实现的能力，并可在运行时查询。
3. 能力声明与实际提供者保持一致，避免“声明支持但调用时降级”。
4. 用户主动调用不支持的功能时，统一抛出可诊断异常，不静默成功。
5. Windows 现有行为和持久化格式保持兼容。
6. Linux、macOS 和未知平台能够明确表达部分支持或不支持。
7. 任务编排和 OCR 领域逻辑保留在原有归属层；低层进程能力和 OS 集成按本方案迁入平台层。
8. 通过渐进迁移控制变更范围，不在一轮中重写全部平台相关模块。

## 3. 非目标

1. 本轮不实现 Linux X11/Wayland 或 macOS 窗口控制。
2. 本轮不承诺所有脚本、模拟器和 PC 游戏可在非 Windows 平台运行。
3. 本轮不把 MaaEnd 登录、Arknights PC 工具等领域流程搬入平台层。
4. 本轮不新增面向前端的平台能力 API；需要按能力禁用设置项时另行做端到端设计。
5. 本轮不使用空实现伪装功能成功。

## 4. 目录与依赖设计

平台层按“通用默认实现”和“具体平台实现”拆分。Windows 是 MAS 的主维护路径；Linux 只保留已有且可验证的实现，不为了目录对称创建空模块：

```text
app/
└── platform/
    ├── __init__.py
    ├── runtime.py
    ├── capabilities.py
    ├── contracts.py
    ├── errors.py
    │
    ├── common/
    │   ├── process.py
    │   └── process_runner.py
    │
    ├── windows/
    │   ├── window.py
    │   ├── power.py
    │   ├── startup.py
    │   ├── hotkey.py
    │   ├── input.py
    │   ├── process.py
    │   └── secret.py
    │
    └── linux/
        ├── power.py
        └── process.py
```

不创建尚无真实实现的 `macos/` 目录。macOS 和未知平台由 `runtime.py` 声明缺失能力；出现经过验证的实现后再增加对应模块。

`common` 不是跨平台杂物箱，只放“已有且合理的通用默认实现”。普通文件读写继续归 `app/utils/io.py`，HTTP 和外部网络集成继续归 `app/services` 或具体业务服务。`process_runner.py` 不命名为 `subprocess.py`，避免与标准库同名。

### 4.1 依赖方向

平台层是新的底层基础设施边界：

```text
platform
   ↓
utils / models / services
   ↓
core / task / api
```

箭头表示上层可以依赖下层。明确禁止：

- `platform -> core`
- `platform -> task`
- `platform -> services`
- `platform -> app.utils.__init__`
- `platform -> Config` 或其他业务配置对象

平台层只回答“当前环境能不能做”和“底层如何执行”，不能读取配置后决定 MAS 是否启用某项功能。平台实现如需日志，不得为了方便导入 `app.utils` 聚合入口；应使用无反向依赖的最小日志入口或由上层传入日志能力。

### 4.2 三条强制架构规则

1. `sys.platform` 只允许出现在 `app/platform/runtime.py` 和极少数确有必要的平台实现内部。
2. 业务层依赖 `contracts` 或 `runtime` 暴露的类型化能力，不直接依赖 `windows.*`；明确标注且仅在 Windows 加载的专项适配器除外。
3. `common` 只接纳真实通用默认实现，不接纳因为“暂时不知道放哪”而迁入的代码。

## 5. 能力模型

### 5.1 平台与能力

```python
from enum import StrEnum


class PlatformName(StrEnum):
    WINDOWS = "windows"
    LINUX = "linux"
    DARWIN = "darwin"
    UNKNOWN = "unknown"


class PlatformCapability(StrEnum):
    WINDOW_CONTROL = "window_control"
    DESKTOP_AUTOMATION = "desktop_automation"
    GLOBAL_HOTKEY = "global_hotkey"
    PREVENT_SLEEP = "prevent_sleep"
    AUTOSTART = "autostart"
    POWER_CONTROL = "power_control"
    SECURE_STORAGE = "secure_storage"
    MAAFW_WIN32 = "maafw_win32"
```

进程创建、进程查询、ADB、HTTP 等通用功能不应为了凑矩阵而声明为平台能力。

### 5.2 电源动作

不同系统支持的电源动作并不完全相同，应在 `POWER_CONTROL` 之下继续声明动作集合：

```python
class PowerAction(StrEnum):
    SHUTDOWN = "shutdown"
    FORCE_SHUTDOWN = "force_shutdown"
    REBOOT = "reboot"
    HIBERNATE = "hibernate"
    SUSPEND = "suspend"
    LOGOFF = "logoff"
```

平台服务需要同时回答：

- 是否提供电源控制能力；
- 是否支持某一个具体 `PowerAction`。

### 5.3 Contract 约束

`contracts.py` 只定义真正具有跨平台业务语义、并需要由通用调用方消费的契约，例如：

- `PowerController`
- `StartupManager`
- `ProcessPlatformOps`
- 后续经过兼容设计的 `SecretStore`

不为了形式统一给每个 Windows 模块创建 Protocol。纯 Win32 HWND 查找、消息投递和焦点控制如果当前没有跨平台业务语义，可以只存在于 `windows/window.py`。只有出现第二个平台实现，或通用调用方确实需要稳定语义时，才提炼对应 contract。

### 5.4 统一异常

```python
class UnsupportedPlatformError(RuntimeError):
    def __init__(
        self,
        capability: PlatformCapability,
        platform: PlatformName,
    ) -> None:
        self.capability = capability
        self.platform = platform
        ...
```

异常表达的是“能力在当前平台不可用”，而不是笼统地否定整个平台。标准消息示例：

```text
Capability 'global_hotkey' is not supported on linux
```

规则：

1. 用户主动请求某项不支持的操作时抛出该异常。
2. API 层负责将异常转换为用户可理解的响应。
3. 初始化阶段可以根据能力跳过不适用组件，但必须记录明确日志。
4. 查找型接口仅在“未找到”时返回 `None`；“平台不支持查找”不能伪装成未找到。
5. 不使用 `False` 同时表达“操作失败”和“平台不支持”。

### 5.5 类型化平台组合对象

`runtime.py` 负责平台识别、实现装配和能力声明，但不能演化成字符串式 service locator。平台对象使用明确属性，不提供 `platform.get("xxx")` 一类动态查找：

```python
class PlatformRuntime:
    name: PlatformName
    capabilities: frozenset[PlatformCapability]
    power: PowerController | None
    startup: StartupManager | None
    process: ProcessPlatformOps

    def supports(self, capability: PlatformCapability) -> bool:
        ...
```

稳定公共入口为：

```python
from app.platform import platform

platform.capabilities
platform.power
platform.startup
platform.process
```

具体字段按真实跨平台契约逐步加入。`supports()` 主要用于初始化、配置展示和组件加载，不替代具体操作自身的错误处理。纯 Windows 专项模块由 `runtime` 的能力声明控制加载，不通过字符串键从 runtime 取出。

## 6. 初始能力矩阵

| 能力 | Windows | Linux | macOS | 未知平台 |
|---|---:|---:|---:|---:|
| 窗口查找、显隐和激活 | 是 | 否 | 否 | 否 |
| 桌面截图与输入模拟 | 是 | 否 | 否 | 否 |
| 全局热键 | 是 | 否 | 否 | 否 |
| 阻止系统休眠 | 是 | 否 | 否 | 否 |
| 开机自启 | 是 | 否 | 否 | 否 |
| 电源控制 | 是 | 部分 | 否 | 否 |
| 安全存储 | DPAPI | 否 | 否 | 否 |
| MaaFW Win32 Controller | 是 | 否 | 否 | 否 |

Linux 当前已有的电源动作包括关机、重启、休眠、挂起和注销，不包括 Windows 强制关机语义。能力矩阵必须由测试固定，新增实现时同步更新。

## 7. 迁移边界

### 7.1 `ProcessManager`

`app/platform/common/process.py` 负责可由 psutil 等现有依赖稳定提供的通用语义：

- 按 PID 或进程名查询；
- psutil `Process` 封装；
- wait 和生命周期跟踪；
- 通用进程树遍历；
- psutil 能够提供的通用递归终止能力。

`app/platform/common/process_runner.py` 负责：

- 通用同步、异步子进程创建；
- stdout/stderr 读取与结果模型；
- 超时和取消语义；
- 接收平台 `ProcessPlatformOps` 提供的 creation flags 等差异参数。

`app/platform/windows/process.py` 只负责 Windows 特殊语义：

- `CREATE_NO_WINDOW`；
- `DETACHED_PROCESS`；
- `HIGH_PRIORITY_CLASS`；
- Windows Job Object；
- Windows 特殊进程树终止；
- 其他 Windows-specific creation flags。

“进程树终止”不能默认全部放入 Windows 实现。优先使用 `common/process.py` 的通用递归遍历和终止；只有 psutil 无法表达或 Windows 行为确有差异的部分才进入 `windows/process.py`。

迁移到平台窗口能力：

- `get_window_handles`；
- `get_main_window_handle`；
- `is_visible`；
- `show_window`；
- `hide_window`；
- `minimize_window`；
- `activate_window`。

为降低调用方改动，原 `app.utils` 可以在迁移期保留兼容导出，但不能保留第二份实现。窗口方法先委托 Windows 专项实现；随后再把只在 Windows 业务中成立的接口从通用进程对象中移除。

### 7.2 `OCRTool`

保留在 OCR 模块：

- OCR 引擎；
- 图片预处理；
- 模板匹配；
- 文本识别；
- ADB 截图；
- 基于识别结果的高层点击流程。

迁移到 Windows 平台实现或明确的跨平台能力：

- DPI 查询；
- 窗口枚举和查找；
- 窗口激活；
- 窗口区域计算；
- 桌面区域截图所需的 OS 集成。

`OCRTool` 应组合已有稳定能力，而不是继承平台基类。纯 HWND 方法在尚无跨平台语义时直接留在 `windows/window.py`，不为它创建假 Protocol。

### 7.3 `System`

保留在 `app/services/system.py`：

- 电源任务倒计时；
- 电源任务取消；
- `KillSelf` 应用生命周期；
- WebSocket 关闭通知；
- 业务级模拟器清理；
- 通用进程结束编排。

迁移到平台能力：

- Windows/Linux 关机、重启、休眠、挂起和注销命令；
- Windows `SetThreadExecutionState`；
- Windows 任务计划自启动；
- 对应的状态查询。

`System.set_power()` 保留为兼容门面，将 OS 动作委托给 `platform.power`；`KillSelf` 不进入平台实现。

### 7.4 模拟器

`DeviceBase` 当前强制所有设备实现 `setVisible()`，但窗口显隐不是所有设备和平台共有的生命周期能力。

迁移策略：

1. `open/close/getStatus/list_devices/getInfo` 继续作为设备基础契约。
2. 将窗口显隐建模为可选能力，而不是平台无关的强制抽象方法。
3. MuMu 自带 CLI 的 `show_window/hide_window` 可以作为模拟器自身能力保留。
4. 依赖 Win32 窗口或全局老板键的 General、LDPlayer 实现改为请求平台能力。
5. 调用方在展示或触发“显示窗口”操作前检查设备能力，不在调用后猜测异常原因。

### 7.5 模拟器发现

本方案暂不把模拟器注册表发现塞入 `windows/process.py`，也不为单一调用方提前建立通用 contract。它继续留在 `app/utils/emulator/tools.py`，待确认“注册表能力”或“模拟器发现能力”的真实复用边界后单独迁移。

这一延期是有意的边界控制，不代表注册表访问已经成为跨平台通用代码。后续迁移时仍需满足 `winreg` 只存在于 Windows 平台实现的目标。

### 7.6 MaaEnd 登录

登录流程继续属于 `app/task/MaaEnd/tools/login.py`，包括：

- 登录页面状态机；
- OCR 结果归行；
- 账号匹配；
- 超时和错误上下文；
- 点击顺序与登录确认。

仅将以下 OS 集成迁入 Windows 专项实现：

- 窗口查找和激活；
- DPI 上下文；
- 客户区坐标转换；
- 桌面截图；
- 鼠标和键盘输入。

平台层不得了解终末地窗口标题、账号匹配规则或登录步骤。该登录模块本身是 Windows 专项调用方，可以在确认能力并按平台加载后使用 `windows/window.py` 和 `windows/input.py`；不应为了这一条调用链制造伪跨平台 contract。

### 7.7 MaaFW 专项适配器

`ArknightWin32.py` 继续作为明确的 Windows 专项适配器存在，不搬入通用平台服务。

入口通过以下方式决定是否加载：

```python
if platform.supports(PlatformCapability.MAAFW_WIN32):
    ...
```

专项适配器只在受支持平台导入，因此其内部无需继续散布非 Windows 空分支。

### 7.8 安全存储

`sanitize_log_message()` 和 `format_exception_reason()` 继续保留在通用安全工具中。

`dpapi_encrypt()` 和 `dpapi_decrypt()` 迁入 Windows 安全存储实现，`EncryptValidator` 改为依赖 `platform.secret_store`。

安全存储不是纯位置迁移，必须单独处理兼容问题：

1. Windows 已有 DPAPI 密文必须继续可读。
2. 非 Windows 不再以 Base64 伪装加密。
3. 已写入的 `AUTOMAS-PLAINTEXT:` 数据需要明确迁移或拒绝策略。
4. 非 Windows 在没有合格安全存储实现时应明确报告能力缺失。
5. 不在本轮临时引入未经评估的新密钥文件格式。

## 8. EndFieldPC 死链清理

当前 `app/MaaFW/EndFieldPCWin32.py` 会被 `main.py` 导入，并在导入时注册 `CheckForm`、`CheckComboxBox` 和 `CheckAccount`。这些识别器仅被 `res/MaaFW/pipeline/EndFieldPC.json` 引用。

当前 MaaEnd 切号已经改由 `app/task/MaaEnd/tools/login.py` 完成，仓库内没有其他代码提交任何 `EndFieldPC` pipeline 根任务。因此这组代码在仓库内部调用图中属于“完成注册但不可达”的死链。

计划删除：

- `app/MaaFW/EndFieldPCWin32.py`；
- `app/MaaFW/__init__.py` 中相关导出；
- `main.py` 中对应显式导入；
- `res/MaaFW/pipeline/EndFieldPC.json`。

`res/MaaFW/image/EndFieldPC/` 不能整体删除。新登录流程仍复用其中部分模板，删除 pipeline 后需要按实际引用清理剩余图片。

删除前最后确认：不存在仓库外插件、调试入口或用户脚本按 pipeline 名称动态调用这些任务。

## 9. 实施阶段

### 阶段一：删除死链并建立平台骨架

- [ ] 删除 EndFieldPC MaaFW 不可达链路。
- [ ] 新增 `app/platform`、平台名、能力枚举和 `UnsupportedPlatformError`。
- [ ] 新增 `runtime.py`，集中识别平台并使用类型化属性装配能力。
- [ ] 只为 `PowerController`、`StartupManager`、`ProcessPlatformOps` 等真实跨平台语义建立 contract。
- [ ] 新增 Windows 和 Linux 当前已有的实现；macOS 与未知平台只声明能力缺失。
- [ ] 固定初始能力矩阵。
- [ ] 将 `main.py` 和 `timer.py` 的 Win32 加载判断改为能力查询。
- [ ] 写入平台层依赖禁令和三条强制架构规则。
- [ ] 保持现有 Windows 功能行为不变。

预计：新增 7～10 个文件，修改 3～5 个文件；另删除约 670 行死代码和资源定义。

### 阶段二：迁移窗口和桌面能力

- [ ] 将通用进程查询、生命周期和树遍历迁入 `common/process.py`。
- [ ] 将通用子进程执行迁入 `common/process_runner.py`。
- [ ] 将 creation flags、优先级和特殊终止语义迁入 `windows/process.py`。
- [ ] 从 `ProcessManager` 提取 Win32 窗口实现。
- [ ] 保留 `ProcessManager` 兼容门面。
- [ ] 从 `OCRTool` 提取窗口、DPI、激活和桌面截图集成。
- [ ] MaaEnd 登录在能力门禁后使用 Windows 专项窗口和输入实现。
- [ ] General、LDPlayer 等模拟器显隐改用能力接口。
- [ ] 去除迁移文件中的 Win32 条件导入。

预计：修改 8～12 个文件，约 400～700 行迁移和接口调整。

### 阶段三：迁移系统能力

- [ ] 拆出 Windows/Linux 电源执行器。
- [ ] 拆出 Windows 休眠抑制和自启动实现。
- [ ] 保留 `System` 的应用级编排职责。
- [ ] 统一不支持错误，不再静默成功。

预计：修改 4～7 个文件，约 200～400 行迁移和接口调整。

### 阶段四：安全存储

- [ ] 定义 `SecretStore` 能力契约。
- [ ] 迁移 Windows DPAPI 实现。
- [ ] 制定遗留 Base64 明文标记处理策略。
- [ ] 修改 `EncryptValidator` 的依赖和错误语义。
- [ ] 验证已有 Windows 配置兼容。

安全存储应独立评审，不与机械迁移混为一轮。

### 阶段五：收尾

- [ ] 清理无效惰性导入与重复平台判断。
- [ ] 复核依赖方向和循环导入。
- [ ] 更新 `res/version.json` 下一个未发布版本条目。
- [ ] 按最小受影响范围运行测试。
- [ ] 更新能力矩阵和实现说明。

## 10. 测试方案

平台层形成独立基础设施边界后，测试放入 `tests/platform/`，并同步更新 `tests/AGENTS.md` 的目录归属说明；专项 MaaEnd 回归仍放入 `tests/task/`，不在测试根目录堆放专项脚本。

### 平台服务

- 平台名到实现的选择正确；
- Windows/Linux/macOS/未知平台能力集合正确；
- 不支持能力统一抛出 `UnsupportedPlatformError`；
- `UnsupportedPlatformError` 保存 `capability` 与 `platform`，消息明确指出缺失能力；
- Linux 电源动作集合与实现一致；
- 平台模块保持惰性导入，非 Windows 测试环境不导入 `pywin32`；
- `PlatformRuntime` 只提供类型化属性，不存在字符串 service locator。

### 进程与窗口

- `common/process.py` 的查询、wait、生命周期和通用树遍历行为保持稳定；
- `common/process_runner.py` 不重复平台创建参数实现；
- Windows 特殊 flags、优先级和 Job Object 只存在于 `windows/process.py`；
- Windows 窗口门面正确委托平台服务；
- 不支持窗口能力时不会被解释为“窗口不存在”；
- 现有调用方无需因迁移改变进程管理接口。

### OCR 与专项流程

- ADB OCR 路径不依赖桌面窗口能力；
- PC OCR 在缺少桌面能力时产生明确错误；
- MaaEnd 登录保留原有账号匹配、超时和取消语义；
- 删除 EndFieldPC pipeline 后 MaaEnd 当前登录入口仍完整。

### 安全存储

- 现有 Windows DPAPI 密文可继续解密；
- 新写入值仍使用 DPAPI；
- 非 Windows 不生成 Base64 伪密文；
- 遗留明文标记按最终迁移策略处理。

## 11. 验收条件

1. `sys.platform` 只存在于 `app/platform/runtime.py` 和极少数确有必要的平台实现内部；与遥测展示等无关的稳定信息采集可例外。
2. 本轮迁移覆盖的 `win32gui`、`win32con`、`win32api`、`win32process`、`win32crypt` 仅存在于 `app/platform/windows` 和名称明确的 Win32 专项适配器中；`winreg` 作为已记录的后续边界任务单独处理。
3. 非 Windows 环境导入主程序不需要安装 `pywin32`。
4. “未找到”“操作失败”“平台不支持”三种状态具有不同且稳定的语义。
5. Windows 现有进程、窗口、OCR、模拟器、电源和 DPAPI 行为保持兼容。
6. Linux、macOS 和未知平台的能力可以直接查询，并由测试固定。
7. 不存在静默成功或 Base64 冒充安全存储的降级路径。
8. 平台层不包含终末地登录、Arknights 战斗操作或模拟器业务规则。
9. 没有新增反向依赖或循环导入。
10. `contracts.py` 不包含只有单一 Windows 调用方、没有跨平台业务语义的假抽象。
11. `runtime.py` 不提供字符串式能力查找。
12. `common` 中不存在普通文件 IO、HTTP 集成或无明确归属的杂项代码。
13. 平台层不导入 `core`、`task`、`services`、`app.utils.__init__` 或 `Config`。

## 12. 风险与控制

| 风险 | 控制方式 |
|---|---|
| 迁移窗口代码导致大量调用方变化 | 先保留 `ProcessManager` 兼容门面，内部委托 |
| 能力集合与真实实现不一致 | 能力矩阵测试；平台实现和声明同文件维护 |
| `contracts.py` 演化为大接口集合 | 只为已有跨平台业务语义建立 contract，单平台细节留在实现模块 |
| `runtime.py` 演化为 service locator | 只暴露类型化属性，禁止字符串式 `get()` |
| 不支持异常破坏启动流程 | 初始化路径先查询能力；主动操作才抛异常 |
| Linux 电源能力被过度概括 | 单独声明 `PowerAction` 集合 |
| MaaEnd 领域逻辑泄漏进平台层 | 平台层只接收窗口句柄、坐标和输入参数 |
| DPAPI 迁移导致凭据损坏 | 安全存储独立阶段、兼容测试、禁止自动清空 |
| 删除 EndFieldPC 影响动态调用 | 删除前确认仓库外扩展约定，并审计资源引用 |
| `common` 变成第二个 `utils` | 只接纳真实通用默认实现，filesystem/network 保留原归属 |

## 13. 改动量估计

整体约七成为实现迁移和调用委托，主要设计成本集中在能力契约、不支持语义、设备可选能力和安全存储兼容。

| 范围 | 预计文件数 | 预计改动量 |
|---|---:|---:|
| EndFieldPC 死链清理 | 4～6 | 约 670 行删除 |
| 平台骨架与能力声明 | 7～10 | 约 200～350 行 |
| 窗口与桌面能力迁移 | 8～12 | 约 400～700 行 |
| 系统能力迁移 | 4～7 | 约 200～400 行 |
| 安全存储迁移 | 4～6 | 约 150～300 行，另含兼容决策 |

建议当前分支优先完成阶段一和阶段二。系统能力可紧随其后；安全存储保持独立评审和实施。
