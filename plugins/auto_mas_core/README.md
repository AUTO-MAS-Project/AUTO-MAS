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

AUTO-MAS 插件基类、配置骨架与开发 SDK。运行时由宿主提供真实实现，SDK 本身不包含独立宿主。

## 版本与构建

- **发行版本**：跟随主程序，由 `scripts/changelog.py` 从 `CHANGELOG.md` 同步生成（含 PEP 440 版本转换与 `host-dependencies.txt`）。修改宿主依赖后运行 `python scripts/changelog.py sync`。
- **协议版本**：`PLUGIN_API_VERSION = "6"` 独立表示插件协议兼容性。插件应在 `pyproject.toml` 中声明兼容的宿主发行范围（如 `auto_mas_core>=5.8,<5.9`），加载器会同时校验协议版本。
- **本地加载与打包**：本地宿主直接加载 `src/` 并在插件共享环境登记元数据；打包发行使用 `uv build plugins/auto_mas_core`（含 `py.typed`）。

## 最小插件入口

插件使用普通 Python 包 + `src/` 布局，在 `pyproject.toml` 中声明元数据、SDK 依赖与插件 keywords，并在包入口导出 `PLUGIN`：

```python
from auto_mas_core import BasePlugin, PLUGIN_API_VERSION
from auto_mas_core.utils import get_logger


class PLUGIN(BasePlugin):
    async def on_enable(self) -> None:
        get_logger("demo").info("插件已启用")
```

插件通过 SDK 导入公开能力，避免直接依赖宿主内部 `app.*` 模块。自有配置继承 `PluginConfig`，沿用 `ConfigEntry`、`ConfigGroup`、`collection` 与现有的 stage/commit、锁与信号机制。卸载插件会清除该插件所属的全部配置。

## 生命周期、服务与路由

- **资源绑定与停用**：宿主在 `pre_enable()` 前绑定 `self.services` 与 `self.background_tasks`。停用、卸载或重载时，宿主先关闭新调用准入并等待在途调用与后台任务结束；外部进程、订阅与私有资源由插件自行释放。
- **服务与 HTTP**：跨插件服务通过 `provides_services` 声明，使用 `self.services.get(name)` / `require(name)` 消费（提供者先于依赖者启用）。HTTP 路由使用 `plugin_route` 声明。
- **插件依赖插件**：在 `requires` 写对方提供的服务名，并在 `pyproject.toml` 的 `dependencies` 写对方的发行包。从插件中心安装时，宿主先加载（只加载、不启用）按 `Requires-Dist` 一起装上的新插件，再加载或重载目标；启用目标时沿 `requires` 先启用上游，装完不用重启。插件注册表（`/api/plugin_registry/get`）每条记录给出 `dependsOn`（直接上游）、`missingServices`（找不到提供者的服务）、`disableCascade`（停用或重载会一并拆掉的插件）和 `uninstallCascade`（卸载会一并卸掉的插件）；`disableImpact` 列出会被删除的配置领域，声明了 `plan_type` 的专项含 `plans`。
- **失败原因**：插件命令（启用、停用、重载、卸载、安装）失败时，界面显示 `PluginError`（及其子类）的消息，`payload` 一并返回。宿主自己的拒绝原因、钩子里抛出的 `PluginError`，以及生命周期执行阶段被宿主包成 `PluginOperationError` 的原异常文本都会原样显示，因此钩子里的异常消息要写给用户看，不要带密钥或隐私；不是 `PluginError` 的异常直接冒出命令时只报类名。依赖无法共同满足时，消息会列出 uv 诊断里涉及的包。
- **拆卸前的拒绝出口**：停用、重载、卸载、卸包和安装升级会连带拆掉依赖本插件的全部下游。宿主在动任何实例之前先对整棵要拆的树一起预检：适配器的托管被任务锁住，或任一插件的 `teardown_blockers()` 返回非空，整个操作被拒绝，界面显示每条原因，树上的插件和托管保持原样。有在途工作而又不对应托管锁的插件（运行、手动更新、准备环境等）覆写这个方法：

```python
async def teardown_blockers(self) -> list[str]:
    n = len(self._running)
    return [f"有 {n} 个运行未结束"] if n else []
```

  每次操作调用两遍：第一遍在暂停之前，调用准入还开着、可能有调用在途，这时拒绝就一个调用门都不关，在跑的工作不受打扰；第二遍在整棵树的调用准入已关闭、在途调用已结束之后。暂停时等在途调用收尾最多 15 秒，到时还有调用没结束就以 `PluginBusyError`（「插件系统忙，请稍后重试」）拒绝本次操作、恢复调用准入，在途调用照常完成。方法只读、要快，不得发起生命周期操作；抛出异常也按拒绝处理；默认返回空列表。`pre_disable()` 等钩子的调用时机不变：它们在级联途中才被调用，拒绝会落进上游的失败分支，需要整体拒绝时用本方法。
- **退出与重载**：`on_teardown()` 用于应用退出清理（保留启用状态）。退出时宿主先只封外部入口（插件 HTTP 与新的生命周期操作），停完任务之后才封服务注册表和调用门，再按下游优先调 `on_teardown()`，任务收尾期间插件之间的服务调用照常可用；服务调用被拒时抛 `PluginBusyError`（`PluginError` 的子类，SDK 顶层导出）。普通禁用会移除类型及关联配置；适配器重载通过 `reload_type` 保留配置身份与引用。

## 游戏与专项适配

- **类型声明**：通过 `GameTypeDecl` / `ScriptTypeDecl` 提交配置类型、控制器或展开类；宿主注入 `AdapterRuntime`（`GameControl.runtime` 提供当前 `silent` / `block_ad` 策略）。覆写系统阶段入口时须调用 `super()`。
- **任务展开**：继承 `UserExpander[MyScriptEntry]` 与具体模式 Worker（`AutoProxyWorker`、`ScriptConfigWorker`、`ScriptViewWorker`）。L2 派发前自动绑定 `UserExpander.history`（`TaskHistorySession`）。
- **预下载与缓存键**：`ScriptTypeDecl.prefetch_check` 异步返回 `list[DownloadRequest]`（初查不取锁，L3 持锁后复查）。资源键默认是 URL，可用 `DownloadRequest.key` 指定插件命名空间内的稳定键；文件身份按 `rid` → `content_hash` → 空身份确定。消费时通过 `auto_mas_core.host.core_downloads.download_file()` 传入相同的 `key` 与身份信息，复制缓存后使用自身副本，L2 收尾释放引用。
- **自动代理进度上报**：`auto_mas_core.adapters.script` 提供运行期进度接口（`observe_run(callback)` 接收 `(执行器, RunPoint)`，不改公共任务树或 WS 协议）：

```python
from auto_mas_core.adapters.script import begin_attempt, operation, point

begin_attempt(self, attempt_number)  # 从 1 起，真正开始重试时触发 retry
with operation(self, "start_script"):  # 包裹失败时抛异常的调用
    await launcher.start()
point(self, "special", state="matched", key="daily")  # 在现有检测命中处上报
```

脚本更新与游戏更新分别使用 `script_update` / `game_update`，仅在受管更新真正进入时报告。

- **按配置判定的游戏类型和桌面分身**：`ScriptTypeDecl` 末尾有两个可选的同步函数，都经插件调用门调用，在事件循环里同步执行，只做轻量读取：
  - `game_kind(script, patch)`：按托管当前配置和本次保存补丁（运行时选目标时补丁只含 `game`）返回 `"emulator"` 或 `"client"`，把 `game_kinds` 收窄成一项；返回 `None`、插件不可用或抛异常时按静态的 `game_kinds`。保存托管、保存账号和运行时选游戏目标都会用它校验绑定，判断不了时请返回 `None`，不要拦住运行。
  - `desktop_session(script)`：这个托管能否在桌面分身里跑；未声明、插件不可用或抛异常时为不支持（即以前的行为）。
- **托管级检查与良性跳过**：`UserExpander.check()` 返回字符串时整个托管记「异常」；返回 `ScriptSkip(reason)`（从 `auto_mas_core` 或 `auto_mas_core.adapters.script` 导入）表示这次不是故障、只是暂时不能跑（例如项目正在更新或被占用）：托管和尚未开始的账号记「跳过」，任务收到一条 warning 提示，不派发任何账号。返回 `None` 照常运行。
- **停止通知**：用户停止任务时，L2 在送出取消之前同步调用当前托管 L3 的 `UserExpander.on_stop_requested()`（默认什么都不做）。`finish()` 等收尾受保护、收不到取消，收尾里有要提前结束的长动作（运行后更新、环境确认）时覆盖它置停止标记。它在事件循环里同步执行，只做轻量动作、不要抛出，可能被调用不止一次。整轮交给旧专项管理器的外壳可以这样转给管理器：

```python
def on_stop_requested(self) -> None:
    if self._manager is not None:
        self._manager.stopped_manually = True
        self._manager._on_finalize_cancel_requested()
```

- **确认有账号之后再选定游戏**：默认 L2 在派发 L3 之前选定托管绑定的游戏会话（可能要排队等串行游戏或设备）。L3 类属性 `defer_game_session = True` 表示「由我在确认有可运行账号之后选定」：L2 不提前选定，L3 在确认之后 `await self.select_game_session()`；没有可运行账号就不调，不占游戏、不排队。`select_game_session(config=None)` 的参数不使用，可以直接交给旧专项管理器当 `after_config_lock` 回调（`manager.after_config_lock = self.select_game_session`）。选定失败照原样抛出，由调用方按托管级检查失败处理。没声明的插件行为不变；没声明时 L2 选定失败，托管记「异常」、发 error 提示，尚未开始的账号记「异常」。这两项在旧宿主上不存在，插件要兼容旧宿主时用 `hasattr(UserExpander, "select_game_session")` 判断，旧宿主上 L2 仍会提前选定。
- **托管生命周期钩子**：专项状态不全在 `data/<托管 uid>/` 下、或者保存前要改写账号数据时，覆盖 `ScriptAdapterPlugin` 的下列异步方法。宿主只接子类覆盖了的方法，一个都没覆盖的插件行为不变。

| 方法 | 调用时机 |
| --- | --- |
| `on_script_cloned(source, target)` | 复制托管：新托管配置已提交、宿主复制 `data/<来源 uid>` 之前 |
| `on_script_removed(script_id)` | 删除托管：删除已提交、宿主已删 `data/<uid>` 之后 |
| `prepare_user_read(script, user_ids)` | 读取账号配置前；`user_ids` 为 `None` 表示整个托管 |
| `on_user_added(script, user)` | 新账号已提交后；失败时账号保留，不撤回 |
| `prepare_user_update(script, user, data)` | 保存账号前原地改 `data`；在配置执行门外调用，返回的同步守卫在门内、写入前执行，守卫抛异常则不写入 |

  钩子都经本插件的调用门执行：插件停用或重载途中调用得到 `PluginBusyError`，配置不动；覆盖了钩子的插件不可用时，宿主拒绝对其托管的这些操作，不会绕开钩子直接写入。钩子抛出的其他异常原样传给发起操作的接口。需要钩子的插件应把 `auto-mas-core` 的下限设到带钩子的宿主版本，并在导入时检查 `hasattr(ScriptAdapterPlugin, "on_script_cloned")`，旧宿主上钩子不会被调用。
- **MFW 专项用到的宿主出口**：下列 `auto_mas_core.host` 模块只开放 `__all__` 里列出的名字，其余名字取不到；Windows 专属模块在取属性时才导入宿主模块，非 Windows 上导入 SDK 不出错。

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
| `core_notify_formats_maafw` | `app.core.notify.formats.maafw` | `build_statistics_payload` |
| `core_notify_lifecycle` | `app.core.notify.lifecycle` | `NotificationTaskBase`（宿主自己的类，可直接继承） |
| `utils_common_game_resolution` | `app.utils.common.game_resolution` | `UnityGameResolutionOverride`、`parse_resolution_option` |

  整包再导出的 `utils`、`services`、`services_common_update` 同样给出宿主按需加载的子模块，例如 `process_platform`、`telemetry`、`transport`，取到的就是宿主那一份模块对象，不用再直接导入 `app.*`。
- **桌面分身里的动作**：由宿主写死的表分派，分身进程不导入插件包，所以插件只能用通用动作：`request_desktop_action(desktop, "list_windows", {})` 返回分身桌面上的全部窗口 `[[hwnd, 类名, 标题, pid], …]`（MaaFramework 的枚举顺序，已去掉失效句柄），窗口规则由调用方在本进程匹配；`request_desktop_action(desktop, "window_in_session", {"hwnd": "<句柄>"})` 返回这个窗口是否属于该分身。

## 托管配置的加载状态

- **旁挂保留**：启动时专项插件没装上、没加载起来或没启用，它的托管和计划表不会被删掉（运行中停用、卸载仍按上面的类型移除语义删除）。宿主照常启动，把这些条目原样留在配置集合的旁挂区，照旧写回盘上，界面标「所属插件不可用」；插件之后在运行中落到已启用，宿主会把它们还原回原来的位置，下次启动插件正常时直接加载。
- **可见性**：旁挂区里的条目对 `Config.ScriptConfig` / `Config.PlanConfig` 的 `keys()`、`values()`、`get()`、`in` 都不可见，按 uid 取会抛继承 `KeyError` 的 `UnresolvedEntryError`。只读查询用集合的 `unresolved()` 和 `is_unresolved(uid)`。
- **清理前先判加载完整**：凡是按「托管集合里有没有」来判断某样东西已经没人用、可以清理的（项目副本、环境、缓存目录等），必须先看 `Config.managed_configs_loaded()`：

```python
from auto_mas_core import Config

if not Config.managed_configs_loaded():
    return  # 托管没有完整加载，这一轮整轮跳过，不删任何东西
```

  只有它为真时，按托管集合回答「不在了」才算数，为假时可能只是所属插件这次没加载起来；它是瞬时值，每一轮清理开始前现取，不要缓存，还原或删掉最后一条旁挂托管后会自动变真；没有变更通知，拿到假就跳过，等下一次触发（启动、删改托管）再判。

## 宿主服务与通知

- `auto_mas_core.services` 导出宿主的 `BackgroundTaskManager`、`Downloads`、`Notify` 与 `run_in_worker`。
- `auto_mas_core.notify` 直接复用宿主通知渠道、模板、统计与签到摘要：

```python
from auto_mas_core.notify import Notify, NotifyPayload

result = await Notify.send_global(
    NotifyPayload(title="通知标题", text="通知正文"),
    include_system=True,
)
```

`send_user()`、`send_statistics()`、`push_proxy_result()` 分别复用账号通知、统计策略与代理结果流程；`attempted == 0` 不代表已投递。

## 静态类型与开发环境

- SDK 顶层及 `host.*`、`utils`、`services`、`plugin` 均静态引用宿主真实类型；wheel 含 `py.typed`，但不打包 `app.*` 类型桩。
- 独立插件工程开发时需配合同版本宿主源码，并将宿主根目录（源码版 SDK 另加 `plugins/auto_mas_core/src`）加入 Pyright / Pylance 的 `extraPaths`。
- 在主仓库中可通过 `pyright tests/core/plugin_sdk_typing.py plugins/auto_mas_core/src/auto_mas_core` 校验 SDK 静态类型契约。

## 市场元数据与界面多语言

- **市场展示信息**：在插件 README 顶部使用 `<!-- auto-mas:i18n ... -->` 声明 `display_name_i18n`、`description_i18n`、`tags_i18n`（随 `project.readme` 进入发行包 METADATA，本地源码与市场共用解析）。
- **界面词表**：放在包内 `i18n/` 目录，键名以 `plugins.<plugin_id>.*` 为前缀，与 core 词表由同一后端快照下发。

## 插件配置触发器（Trigger）

- 在 `PluginConfig` 分组中声明 `field: Trigger = None`（或 `trigger(timeout=120, description="...")`，默认超时 15 分钟），并用 `@trigger_field("group.field")` 绑定无参同步或异步方法。
- 通过 `entry.write_trigger(group, field, value)` 或 `/api/config/triggers/write` 写入（`True` 启动/返回当前任务 UUID，`False` 请求取消，`None` 跳过），通过 `/api/config/triggers/result` 查询结果；触发器字段不写入配置文件和备份。
- 同步处理器在独立线程池运行，异步处理器中的阻塞调用应使用 `run_in_worker`；需确保副作用完整收尾时可声明 `finish_on_cancel=True`。

## 临时桥接说明

`auto_mas_core.host.core_script_update`、`core_script_update_recovery` 与 `core_script_update_queue` 仅用于旧 manager 过渡期复用，不作为新插件的更新协议；后续将统一迁入 L2 后移除。
