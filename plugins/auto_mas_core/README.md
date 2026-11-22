<!-- auto-mas:i18n
{
  "display_name_i18n": {
    "zh_CN": "AUTO-MAS 核心",
    "en": "AUTO-MAS Core"
  },
  "description_i18n": {
    "zh_CN": "AUTO-MAS 核心系统插件与开发者 SDK",
    "en": "AUTO-MAS core system plugin and developer SDK"
  },
  "tags_i18n": {
    "zh_CN": [
      "核心",
      "SDK"
    ],
    "en": [
      "core",
      "SDK"
    ]
  }
}
-->

# auto_mas_core

AUTO-MAS 插件基类、配置骨架与开发 SDK。运行时由宿主提供真实实现；SDK 不提供独立运行的宿主。

## 版本与安装

发行版本与宿主一致，由 `scripts/changelog.py` 从 `CHANGELOG.md` 生成，沿用发布 CI 的 PEP 440 版本转换。宿主依赖同时生成到 `host-dependencies.txt`，供 wheel 元数据、共享环境解析和升级预检对齐。修改宿主依赖后运行 `python scripts/changelog.py sync`。

`PLUGIN_API_VERSION = "6"` 是独立的插件协议版本，不能用作 SDK 发行版本。插件声明兼容的宿主发行范围，例如 `auto_mas_core>=5.8,<5.9`；加载器同时检查协议版本。

本地宿主直接加载本目录 `src/`，并在插件共享环境登记对应发行元数据，不要求 uv workspace。发布包使用 `uv build plugins/auto_mas_core`；`py.typed` 随 wheel 发布。

## 最小入口

插件使用普通包和 `src/` 布局，在 `pyproject.toml` 声明发行信息、SDK 依赖及插件门禁 keywords，包入口导出 `PLUGIN`：

```python
from auto_mas_core import BasePlugin, PLUGIN_API_VERSION
from auto_mas_core.utils import get_logger


class PLUGIN(BasePlugin):
    async def on_enable(self) -> None:
        get_logger("demo").info("插件已启用")
```

插件通过 SDK 导入公开能力，避免直接依赖宿主 `app.*` 内部模块。配置使用 `PluginConfig`、`ConfigEntry`、`ConfigGroup`、`collection` 和现有 stage/commit、锁与信号机制。宿主从构造时起跟踪配置根，保存成功后才注销。卸载删除该插件的全部所属配置。

## 生命周期与资源

宿主在 `pre_enable()` 前绑定 `self.services` 和 `self.background_tasks`。后台工作使用当前实例的任务组。停用、卸载和重载时，宿主关闭新调用准入，等待在途调用及真实背景工作结束；插件负责其外部进程、订阅和私有资源。

服务通过 `provides_services` 声明，使用 `self.services.get(name)` 或 `require(name)` 消费，提供者启用早于依赖它的插件。

**插件依赖插件。** 依赖别的插件时，在 `requires` 写对方提供的服务名，并在 `pyproject.toml` 的 `dependencies` 写对方的发行包。从插件中心安装时，宿主会把按 `Requires-Dist` 一起装上的新插件先加载（只加载、不启用），再加载或重载目标；启用目标时沿 `requires` 先启用上游，装完不用重启。插件注册表（`/api/plugin_registry/get`）的每条记录给出 `dependsOn`（直接上游）、`missingServices`（找不到提供者的服务）、`disableCascade`（停用或重载会一并拆掉的插件）和 `uninstallCascade`（卸载会一并卸掉的插件）；`disableImpact` 列出会被删除的配置领域，声明了 `plan_type` 的专项含 `plans`。

**失败原因。** 插件命令（启用、停用、重载、卸载、安装）失败时，界面显示 `PluginError`（及其子类）的消息，`payload` 一并返回。宿主自己的拒绝原因、钩子里抛出的 `PluginError`，以及生命周期执行阶段被宿主包成 `PluginOperationError` 的原异常文本都会原样显示，所以钩子里的异常消息要写给用户看，不要带密钥或隐私。不是 `PluginError` 的异常直接冒出命令时只报类名。依赖无法共同满足时，消息会列出 uv 诊断里涉及的包。HTTP 使用 `plugin_route` 声明，宿主在执行前绑定调用参数，业务异常不会触发二次调用。

**拆卸前的拒绝出口。** 停用、重载、卸载、卸包和安装升级会连带拆掉依赖本插件的全部下游。宿主在动任何实例之前，先对整棵要拆的树一起预检：适配器的托管被任务锁住，或任一插件的 `teardown_blockers()` 返回非空，整个操作被拒绝，界面显示每条原因，树上的插件和托管都保持原样。有在途工作而又不对应托管锁的插件（运行、手动更新、准备环境等）覆写这个方法：

```python
async def teardown_blockers(self) -> list[str]:
    n = len(self._running)
    return [f"有 {n} 个运行未结束"] if n else []
```

调用时整棵树的调用准入已关闭、在途调用已结束。方法只读、要快，不得发起生命周期操作；抛出异常也按拒绝处理。默认返回空列表。`pre_disable()` 等钩子的调用时机不变：它们在级联途中才被调用，拒绝会落进上游的失败分支，需要整体拒绝时用本方法。

`on_teardown()` 用于程序退出清理，保留用户的启用选择。普通禁用沿用类型移除语义；适配器重载通过 `reload_type` 保留配置身份与引用。

## 游戏与专项适配

游戏和脚本通过 `GameTypeDecl` / `ScriptTypeDecl` 提交真实配置类型、控制器或展开类。宿主注入 `AdapterRuntime`；`GameControl.runtime` 提供当前 `silent` 和 `block_ad` 策略。覆写系统阶段入口时调用 `super()`。

专项 `ScriptTypeDecl.prefetch_check` 接收脚本配置，异步返回 `list[DownloadRequest]`，空列表表示无需预下载。初查不取锁，L3 运行前取得配置锁后再复查。下载交由统一管理器，L3 从任务参数的专用 `prefetch_paths` 键读取资源键到路径的映射；不自动传入 L4。资源键默认是原 URL，`DownloadRequest.key` 可用插件命名空间内的稳定键替代变化的下载地址。

资源键只定位资源；文件身份仍按 `rid`、`content_hash`、空身份的顺序确定。同一键和身份共享下载，URL 更新不会中止在用传输，后续重试使用最新地址；身份变化会另建文件，旧文件继续保留。查询、等待和释放必须使用同一资源键，Python 调用可用 `request.cache_key`，HTTP 释放可传 `key`，原 `url` 输入继续有效。

专项通过 `auto_mas_core.host.core_downloads.download_file()` 消费时传入相同的 `key` 与 `rid`／哈希；宿主只复制本 L2 已交付且身份匹配的缓存文件，文件缺失或身份不匹配则执行正常下载。脚本复制后使用自己的副本，L2 收尾释放引用；最后一次释放取消未完成下载，已完成缓存仍按容量规则回收。

**托管生命周期钩子。** 专项状态不全在 `data/<托管 uid>/` 下、或者保存前要改写账号数据时，覆盖 `ScriptAdapterPlugin` 的下列异步方法。宿主只接子类覆盖了的方法，一个都没覆盖的插件行为不变。

| 方法 | 调用时机 |
| --- | --- |
| `on_script_cloned(source, target)` | 复制托管：新托管配置已提交、宿主复制 `data/<来源 uid>` 之前 |
| `on_script_removed(script_id)` | 删除托管：删除已提交、宿主已删 `data/<uid>` 之后 |
| `prepare_user_read(script, user_ids)` | 读取账号配置前；`user_ids` 为 `None` 表示整个托管 |
| `on_user_added(script, user)` | 新账号已提交后；失败时账号保留，不撤回 |
| `prepare_user_update(script, user, data)` | 保存账号前原地改 `data`；在配置执行门外调用，返回的同步守卫在门内、写入前执行，守卫抛异常则不写入 |

钩子都经本插件的调用门执行：插件停用或重载途中调用得到 `PluginBusyError`，配置不动；覆盖了钩子的插件不可用时，宿主拒绝对其托管的这些操作，不会绕开钩子直接写入。钩子抛出的其他异常原样传给发起操作的接口。需要钩子的插件应把 `auto-mas-core` 的下限设到带钩子的宿主版本，并在导入时检查 `hasattr(ScriptAdapterPlugin, "on_script_cloned")`，旧宿主上钩子不会被调用。

**MFW 专项用到的宿主出口。** 下列 `auto_mas_core.host` 模块只开放 `__all__` 里列出的名字，其余名字取不到；Windows 专属模块在取属性时才导入宿主模块，非 Windows 上导入 SDK 不出错。

| SDK 模块 | 宿主模块 | 开放的名字 |
| --- | --- | --- |
| `tools_common_ocr` | `app.tools.common.ocr` | `ocr_image`、`Box`、`OCRItem` |
| `tools_common_game_calendar` | `app.tools.common.game_calendar` | 子模块 `stella` |
| `utils_common_process_session` | `app.utils.common.process.session` | `desktop_process_target`、`DesktopProcessTarget` |
| `utils_windows_desktop_session_process_runner` | `app.utils.windows.desktop_session.process_runner` | `launch_desktop_process`、`open_in_desktop`、`run_desktop_action` |
| `task_desktop_session_worker` | `app.task.desktop_session_worker` | `request_desktop_action` |
| `task_run_flow` | `app.task.run_flow` | `point`、`begin_attempt`、`game_update_result`、`operation`、`observe_run`、`RunPoint`、`PointState`、`RunStage` |
| `task_game` | `app.task.game` | `game_device_id`、`game_is_emulator`、`game_target_id`、`current_game_session` |
| `task_client` | `app.task.client` | `client_executable_path`、`client_launcher_path`、`ClientProcess` |
| `utils_common_process_operations` | `app.utils.common.process.operations` | `iter_processes`、`managed_process`、`terminate_process` |
| `utils_common_zip_range` | `app.utils.common.zip_range` | `HealSkip`、`RangeHTTPReader`、`RangeReadCancelled`、`RangeSpeedGuard`、`format_size` |
| `models_notification_channel` | `app.models.notification.channel` | `DispatchResult`、`NotifyTarget` |
| `core_config_manager` | `app.core.config.manager` | `normalize_proxy_address` |

桌面分身里的动作由宿主写死的表分派，分身进程不导入插件包，所以插件只能用通用动作：`request_desktop_action(desktop, "list_windows", {})` 返回分身桌面上的全部窗口 `[[hwnd, 类名, 标题, pid], …]`（MaaFramework 的枚举顺序，已去掉失效句柄），窗口规则由调用方在本进程匹配；`request_desktop_action(desktop, "window_in_session", {"hwnd": "<句柄>"})` 返回这个窗口是否属于该分身。

迁移测试插件可通过 `auto_mas_core.host` 复用现有模拟器、MAA 共用工具等真实宿主能力；这些出口不提供独立宿主或旧任务框架。L2 在派发前向 `UserExpander.history` 绑定当前任务的实际 `TaskHistorySession`，供专项归档使用。

任务展开使用 `UserExpander` 与真实模式的 `ModeWorker` 子类：`AutoProxyWorker`、`ScriptConfigWorker`、`ScriptViewWorker`。插件提供实际执行、结果判定以及 `finish()` 所需的保存与恢复，不依赖未实现的历史写入协议。

**自动代理进度。** 不需要为专项绘制流程图或迁移用户配置。`auto_mas_core.adapters.script`
提供运行内的观察接口；宿主识别自动代理的执行、收尾及任务结果，未报告的步骤保持未知。
有细节的专项直接在已有动作、判定和规则的来源上报告：

```python
from auto_mas_core.adapters.script import begin_attempt, operation, point

begin_attempt(self, attempt_number)  # 从 1 起，只在真正开始下一次尝试时产生 retry
with operation(self, "start_script"):  # 只包住失败时抛异常的调用
    await launcher.start()
point(self, "special", state="matched", key="daily_reward")  # 在现有检测命中处
```

脚本更新和游戏更新分别用 `script_update`、`game_update`，只在注册的更新动作真正进入时报告。
主动中止不是运行失败，后续收尾仍可成功；子任务完成不等于整轮成功。`observe_run(callback)` 在当前
执行上下文接收 `(执行器, RunPoint)`，不新增公共任务树字段、WebSocket 消息或磁盘格式。
只有收尾时才读取的规则在收尾交付，不伪装成实时监听。更新或关闭动作未由 MAS 接管时，不补报成功。

**按配置判定的游戏类型和桌面分身。** `ScriptTypeDecl` 末尾有两个可选的同步函数，都经插件调用门调用：

- `game_kind(script, patch)`：按托管当前配置和本次保存补丁（运行时选目标时补丁只含 `game`）返回 `"emulator"` 或 `"client"`，把 `game_kinds` 收窄成一项；返回 `None`、插件不可用或抛异常时按静态的 `game_kinds`。保存托管、保存账号和运行时选游戏目标都会用它校验绑定，判断不了时请返回 `None`，不要拦住运行。
- `desktop_session(script)`：这个托管能否在桌面分身里跑；未声明、插件不可用或抛异常时为不支持（即以前的行为）。

两个函数都会在事件循环里同步执行，只做轻量读取。

**托管级检查与良性跳过。** `UserExpander.check()` 返回字符串时整个托管记「异常」；返回 `ScriptSkip(reason)`（从 `auto_mas_core` 或 `auto_mas_core.adapters.script` 导入）表示这次不是故障、只是暂时不能跑（例如项目正在更新或被占用）：托管和尚未开始的账号记「跳过」，任务收到一条 warning 提示，不派发任何账号。返回 `None` 照常运行。

展开类可以继承 `UserExpander[MyScriptEntry]`，使 `script_config` 保留专项配置类型。仓库的 `pyrightconfig.json` 已声明 SDK 源码路径；包内其他模块使用相对导入，独立插件工程则在自己的开发环境安装 SDK。

## 托管配置的加载状态

专项插件没装上、没加载起来或没启用时，它的托管和计划表不会被删掉：宿主照常启动，把这些条目原样留在配置集合的旁挂区，照旧写回盘上，界面标「所属插件不可用」。插件之后在运行中落到已启用，宿主会把它们还原回原来的位置；下次启动插件正常时直接加载。旁挂区里的条目对 `Config.ScriptConfig` / `Config.PlanConfig` 的 `keys()`、`values()`、`get()`、`in` 都不可见，按 uid 取会抛继承 `KeyError` 的 `UnresolvedEntryError`。只读查询用集合的 `unresolved()` 和 `is_unresolved(uid)`。

凡是按「托管集合里有没有」来判断某样东西已经没人用、可以清理的（项目副本、环境、缓存目录等），必须先看 `Config.managed_configs_loaded()`：

```python
from auto_mas_core import Config

if not Config.managed_configs_loaded():
    return  # 托管没有完整加载，这一轮整轮跳过，不删任何东西
```

- 只有它为真时，按托管集合回答「不在了」才算数；为假时可能只是所属插件这次没加载起来。
- 它是瞬时值，每一轮清理开始前现取，不要缓存；还原或删掉最后一条旁挂托管后会自动变真。
- 没有变更通知：拿到假就跳过，等下一次触发（启动、删改托管）再判。

## 静态类型与开发环境

SDK 顶层及 `host.*`、`utils`、`services`、`plugin` 的静态导出直接引用宿主的真实类型；运行时仍按需加载宿主能力。配置继承、泛型、装饰器和单例方法的类型不应通过动态 `__getattr__` 退化为 `Any`。

当前 wheel 包含 `py.typed`，但没有携带 `app.*` 的类型桩。独立插件工程仅安装 wheel 仍不足以解析宿主类型；开发时需要同版本宿主源码，并将宿主根目录加入 Pyright/Pylance 的 `extraPaths`。使用源码版 SDK 时，同时加入 `plugins/auto_mas_core/src`。`py.typed` 只标记包提供类型信息，不会补齐这些外部定义。

在宿主仓库运行 `pyright tests/core/plugin_sdk_typing.py plugins/auto_mas_core/src/auto_mas_core`，验证配置构建、集合泛型、虚拟字段、响应模型和宿主单例的类型。该文件是静态契约，不作为 pytest 运行入口。按项目开发方式，插件调试和类型检查依托匹配的宿主源码，不单独交付宿主类型桩。

## 宿主服务与通知

`auto_mas_core.services` 导出真实的 `BackgroundTaskManager`、`Downloads`、`Notify` 和 `run_in_worker`。跨插件服务总线位于 `auto_mas_core.plugin.services`；新插件优先使用实例绑定的 `self.services`。

从 `auto_mas_core.notify` 获取宿主的实际 `Notify` 单例及消息类型，直接沿用渠道、模板、统计和签到摘要；没有插件专用通知协议或绑定：

```python
from auto_mas_core.notify import Notify, NotifyPayload

# 位于插件异步方法内
result = await Notify.send_global(
    NotifyPayload(title="通知标题", text="通知正文"), include_system=True
)
```

`send_user()`、`send_statistics()` 和 `push_proxy_result()` 分别复用账号通知、统计策略和代理结果流程。`attempted == 0` 不表示已投递。通知服务统一读取新用户的 `notify` 配置和来源专项保留的 `Notify` 分组；调用方直接传入用户配置。

## 界面与多语言

插件市场的名称、简介和标签统一在 README 开头的 `<!-- auto-mas:i18n … -->` 注释内声明，
使用 `display_name_i18n`、`description_i18n`、`tags_i18n` 三个语言映射。
这份 README 经 `project.readme` 进入发行包 METADATA 正文及 PyPI JSON 的 `info.description`，
本地源码、已安装插件和未安装的市场条目共用同一解析方式。
`project.description` 使用普通简介，`keywords` 保留普通关键词和插件身份标记，
`project.urls` 只保存真实链接，不再用 URL 或 Keywords 携带多语言 JSON。
此处仅描述市场展示元数据；插件业务界面的语言资源仍按下述资源机制提供。

宿主提供插件中心、市场和声明式配置页面。插件语言资源放在包内 `i18n/`，键使用 `plugins.<plugin_id>.*`；core 与插件资源由同一个后端快照提供。当前 SDK 不声明任意 iframe、自定义元素或动态前端资源加载器。

## 插件配置命令

插件自有配置继承 `PluginConfig`。在配置分组声明 `field: Trigger = None`，用 `@trigger_field("group.field")` 绑定无参同步或异步实例方法。

用 `entry.write_trigger(group, field, value)` 写入命令。传 `None` 跳过，传 `True` 启动或返回当前任务 UUID，传 `False` 请求取消当前任务。配置 `update()` 也接受同样的命令值，仍返回 `None`。属性读取返回 `UUID | None`。接口使用配置自身 UID，可通过 `/api/config/triggers/write` 写入，并通过 `/api/config/triggers/result` 查任务结果。触发器字段和 UUID 从配置文件及备份中省略。

配置管理器托管执行和回收。同步处理器进入独立线程池，异步处理器通过事件循环运行。异步处理器中的阻塞调用应使用 `run_in_worker`。默认超时 15 分钟。可在字段声明时使用 `field: Trigger = trigger(timeout=120, description="刷新资源")` 覆盖，单位秒。取消或超时后，已经开始的线程调用须实际退出才清除字段占用。插件方法若有必须完整收尾的副作用，可以声明 `finish_on_cancel=True`，让已经开始的处理器安全完成后再结束任务。可中断的异步方法应使用 `finally` 清理资源。


## 旧脚本更新桥接

`auto_mas_core.host.core_script_update`、`core_script_update_recovery` 和 `core_script_update_queue` 仅供临时复用旧 manager 的测试适配使用，不作为新插件更新协议。
预下载由 L2 的 `PrefetchSession` 统一处理；恢复汇总位于 `app/task/script_update.py`。检查、安装和恢复业务后续全部迁入 L2，再删除旧 manager 的兼容入口及这些桥接。
