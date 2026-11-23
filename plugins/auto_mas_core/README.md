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
- **退出与重载**：`on_teardown()` 用于应用退出清理（保留启用状态）；普通禁用会移除类型及关联配置；适配器重载通过 `reload_type` 保留配置身份与引用。

## 游戏与专项适配

- **类型声明**：通过 `GameTypeDecl` / `ScriptTypeDecl` 提交配置类型、控制器或展开类；宿主注入 `AdapterRuntime`（`GameControl.runtime` 提供当前 `silent` / `block_ad` 策略）。覆写系统阶段入口时须调用 `super()`。
- **任务展开**：继承 `UserExpander[MyScriptEntry]` 与具体模式 Worker（`AutoProxyWorker`、`ScriptConfigWorker`、`ScriptViewWorker`）。L2 派发前自动绑定 `UserExpander.history`（`TaskHistorySession`）。
- **预下载与缓存键**：`ScriptTypeDecl.prefetch_check` 异步返回 `list[DownloadRequest]`（初查不取锁，L3 持锁后复查）。资源键默认是 URL，可用 `DownloadRequest.key` 指定插件命名空间内的稳定键；文件身份按 `rid` → `content_hash` → 空身份确定。消费时通过 `auto_mas_core.host.core_downloads.download_file()` 传入相同的 `key` 与身份信息，复制缓存后使用自身副本，L2 收尾释放引用。
- **自动代理进度上报**：`auto_mas_core.adapters.script` 提供运行期进度接口（`observe_run(callback)` 接收 `(执行器, RunPoint)`，不改公共任务树或 WS 协议）：

```python
from auto_mas_core.adapters.script import begin_attempt, operation, point

begin_attempt(self, attempt_number)                     # 从 1 起，真正开始重试时触发 retry
with operation(self, "start_script"):                   # 包裹失败时抛异常的调用
    await launcher.start()
point(self, "special", state="matched", key="daily")    # 在现有检测命中处上报
```

脚本更新与游戏更新分别使用 `script_update` / `game_update`，仅在受管更新真正进入时报告。

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
