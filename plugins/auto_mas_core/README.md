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

服务通过 `provides_services` 声明，使用 `self.services.get(name)` 或 `require(name)` 消费，提供者启用早于依赖它的插件。HTTP 使用 `plugin_route` 声明，宿主在执行前绑定调用参数，业务异常不会触发二次调用。

`on_teardown()` 用于程序退出清理，保留用户的启用选择。普通禁用沿用类型移除语义；适配器重载通过 `reload_type` 保留配置身份与引用。

## 游戏与专项适配

游戏和脚本通过 `GameTypeDecl` / `ScriptTypeDecl` 提交真实配置类型、控制器或展开类。宿主注入 `AdapterRuntime`；`GameControl.runtime` 提供当前 `silent` 和 `block_ad` 策略。覆写系统阶段入口时调用 `super()`。

专项 `ScriptTypeDecl.prefetch_check` 接收脚本配置，异步返回 `list[DownloadRequest]`，空列表表示无需预下载。初查不取锁，L3 运行前取得配置锁后再复查。下载交由统一管理器，L3 从任务参数的专用 `prefetch_paths` 键读取资源键到路径的映射；不自动传入 L4。资源键默认是原 URL，`DownloadRequest.key` 可用插件命名空间内的稳定键替代变化的下载地址。

资源键只定位资源；文件身份仍按 `rid`、`content_hash`、空身份的顺序确定。同一键和身份共享下载，URL 更新不会中止在用传输，后续重试使用最新地址；身份变化会另建文件，旧文件继续保留。查询、等待和释放必须使用同一资源键，Python 调用可用 `request.cache_key`，HTTP 释放可传 `key`，原 `url` 输入继续有效。

专项通过 `auto_mas_core.host.core_downloads.download_file()` 消费时传入相同的 `key` 与 `rid`／哈希；宿主只复制本 L2 已交付且身份匹配的缓存文件，文件缺失或身份不匹配则执行正常下载。脚本复制后使用自己的副本，L2 收尾释放引用；最后一次释放取消未完成下载，已完成缓存仍按容量规则回收。

迁移测试插件可通过 `auto_mas_core.host` 复用现有模拟器、MAA 共用工具等真实宿主能力；这些出口不提供独立宿主或旧任务框架。L2 在派发前向 `UserExpander.history` 绑定当前任务的实际 `TaskHistorySession`，供专项归档使用。

任务展开使用 `UserExpander` 与真实模式的 `ModeWorker` 子类：`AutoProxyWorker`、`ScriptConfigWorker`、`ScriptViewWorker`。插件提供实际执行、结果判定以及 `finish()` 所需的保存与恢复，不依赖未实现的历史写入协议。

展开类可以继承 `UserExpander[MyScriptEntry]`，使 `script_config` 保留专项配置类型。仓库的 `pyrightconfig.json` 已声明 SDK 源码路径；包内其他模块使用相对导入，独立插件工程则在自己的开发环境安装 SDK。

## LogFlow 日志节点

在现有专项插件类的 `log_flows` 中加一条具名声明即可使用 MAS 原生日志和默认通知排版。下面片段沿用专项已有的 `script_type_key`、`decl` 和执行逻辑。专项通过 `auto_mas_core.log_flow.LogMonitor` 创建监控器。`execute()` 在启动日志生产进程时启动该监控器，并继续负责执行结果和进程清理。

```python
from contextlib import AsyncExitStack

from auto_mas_core import ScriptAdapterPlugin
from auto_mas_core.log_flow import (
    LineRule,
    LogMonitor,
    PluginFlowDeclaration,
    ReportMode,
    SimpleFlowDeclaration,
    open_log_flow,
)


class Adapter(ScriptAdapterPlugin):
    # 保留专项现有的 script_type_key 和 decl。
    log_flows = {
        "progress": PluginFlowDeclaration(
            rules=SimpleFlowDeclaration(
                rules=(LineRule(match=r"^完成：", node_type="步骤", status="success"),),
            ),
        ),
    }


async def execute_with_nodes(
    plugin,
    user_run,
    monitor: LogMonitor,
    task_report,
    execute,
    *,
    collect_nodes: bool,
    mode: ReportMode = "汇总",
):
    async with AsyncExitStack() as stack:
        if collect_nodes:
            await stack.enter_async_context(
                open_log_flow(
                    plugin,
                    "progress",
                    run=user_run,
                    monitor=monitor,
                    task_report=task_report,
                    mode=mode,
                )
            )
        try:
            return await execute()
        finally:
            await monitor.stop()
```

托管执行侧为当前 `TaskScriptItem` 创建一个 `LogFlowTaskReport`，各账号的会话传入同一个报告对象。托管定稿后调用 `task_report.send(title=..., report=...)` 交由 Notify 投递。`mode` 支持 `"逐条"`、`"汇总"` 和 `"关闭"`，绑定报告且省略模式时使用 `"汇总"`。采集使用本次运行的开关，通知关闭时仍可查询节点。将 `monitor.stop()` 放在 Flow 退出前，让正常结束和取消都能先交接缓冲日志，再冻结报告。

在 `AutoProxyWorker` 内，可以调用 `self.open_log_flow(plugin, "progress", monitor=monitor, task_report=task_report)` 打开当前账号的会话，运行身份由执行器传入。托管级和带本次运行文件的接入继续由 `open_log_flow` 绑定具体运行节点。

专项可以在单行、多行和主动上报中声明 `status`，取 `success`、`failed`、`exception`、`running`、`skipped`、`warning` 或 `info`。 `node_type` 可自行定义业务分类。默认报告省略进行中的节点。专项自定义布局时，可用 `task_report.details_for(user_run, statuses={"failed", "exception"})` 选择状态，再调用 `task_report.send(title=..., report=..., append_details=False)`。后置归并接收及返回 `list[ReportEntry]`，由条目携带状态。

报告默认按节点首次出现的顺序取当前状态。旧专项若按最后一次任务结果排序，可在 `SimpleFlowDeclaration` 设置 `report_order="last_updated"`。报告和后置归并器将按最后更新的事件序号接收当前节点，实时快照及游标的顺序保持原口径。

在上下文中用 `as flow` 取得 `FlowAccess`。`snapshot_nodes()` 返回当前有效节点和游标，`read_nodes(after=cursor)` 继续读取新增、修订和撤回。每页使用返回的新游标，收到 `close_reason` 后仍按 `has_more` 读完余下节点。MAS 执行结果由任务状态独立提供。

只采集专项文件时，可声明 `use_mas_log=False` 和 `use_run_file=True`，打开会话时传 `file_input=FileInput(path=...)`。脚本需提前启动时，在启动前 `await FileInput(path=...).capture_start()`，将返回值传入会话。已有结构化结果可在声明中启用 `accept_push`，通过 `flow.reporter` 上报。`accepted` 表示已入队，可用节点查询确认产出。`backpressure` 时只重试本次未入队的记录。自定义来源、处理器、sink 和表达式函数在采集进程中加载，工厂引用自己的插件包，运行参数使用 JSON 值。[设计与迁移验收](../../docs/logbox-runstream-plan.md)

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
