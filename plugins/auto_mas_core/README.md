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

专项 `ScriptTypeDecl.prefetch_check` 接收脚本配置，异步返回 `list[DownloadRequest]`，空列表表示无需预下载。初查不取锁，L3 运行前取得配置锁后再复查。下载交由统一管理器，L3 从任务参数的专用 `prefetch_paths` 键读取完整的 URL 到路径映射；不自动传入 L4。脚本应复制共享文件再使用，L2 收尾释放引用。

迁移测试插件可通过 `auto_mas_core.host` 复用现有模拟器、MAA 共用工具等真实宿主能力；这些出口不提供独立宿主或旧任务框架。L2 在派发前向 `UserExpander.history` 绑定当前任务的实际 `TaskHistorySession`，供专项归档使用。

任务展开使用 `UserExpander` 与真实模式的 `ModeWorker` 子类：`AutoProxyWorker`、`ScriptConfigWorker`、`ScriptViewWorker`。插件提供实际执行、结果判定以及 `finish()` 所需的保存与恢复，不依赖未实现的历史写入协议。

展开类可以继承 `UserExpander[MyScriptEntry]`，使 `script_config` 保留专项配置类型。仓库的 `pyrightconfig.json` 已声明 SDK 源码路径；包内其他模块使用相对导入，独立插件工程则在自己的开发环境安装 SDK。

## 静态类型与开发环境

SDK 顶层及 `host.*`、`utils`、`services`、`plugin` 的静态导出直接引用宿主的真实类型；运行时仍按需加载宿主能力。配置继承、泛型、装饰器和单例方法的类型不应通过动态 `__getattr__` 退化为 `Any`。

当前 wheel 包含 `py.typed`，但没有携带 `app.*` 的类型桩。独立插件工程仅安装 wheel 仍不足以解析宿主类型；开发时需要同版本宿主源码，并将宿主根目录加入 Pyright/Pylance 的 `extraPaths`。使用源码版 SDK 时，同时加入 `plugins/auto_mas_core/src`。`py.typed` 只标记包提供类型信息，不会补齐这些外部定义。

在宿主仓库运行 `pyright tests/core/plugin_sdk_typing.py plugins/auto_mas_core/src/auto_mas_core`，验证配置构建、集合泛型、虚拟字段、响应模型和宿主单例的类型。该文件是静态契约，不作为 pytest 运行入口。独立 wheel 的类型桩发布尚未实现，不以仓库内检查结果代表独立安装场景已通过。

## 宿主服务与通知

`auto_mas_core.services` 导出真实的 `BackgroundTaskManager`、`Downloads`、`Operations` 和 `Notify`。跨插件服务总线位于 `auto_mas_core.plugin.services`；新插件优先使用实例绑定的 `self.services`。

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

插件自有配置继承 `PluginConfig`；独立的插件命令节点继承 `PluginCommandEntry`，游戏、设备、托管、用户和插件计划上界已包含这一适配。
从 SDK 导入的 `trigger_field(path, cancellable=...)` 复用配置触发器绑定并声明取消策略。属性赋值及 `update()` 触发的命令统一进入插件 Operations。
普通 `ConfigEntry` 沿用 dev 的精简触发语义；所有配置 `update()` 返回 `None`，不返回操作 ID。

需要跟踪结果时通过 `Operations.start(config_uid=配置自身UID, group=..., field=..., value=...)` 或 HTTP `/api/operations/start` 取得操作 ID。
插件自有配置 UID 与注册项 UID 各自独立；配置保存接口只返回保存结果。前端使用配置输出的 `ui.hints` 显隐及 `editable` 禁用按钮，不自行推断插件生命周期权限。
Operations 保留同一 Trigger 去重、查询、取消及插件停用协调；实际执行由背景任务组承担，具体资源清理由处理方法完成。

## 旧脚本更新桥接

`auto_mas_core.host.core_script_update`、`core_script_update_recovery` 和 `core_script_update_queue` 仅供临时复用旧 manager 的测试适配使用，不作为新插件更新协议。
预下载由 L2 的 `PrefetchSession` 统一处理；恢复汇总位于 `app/task/script_update.py`。检查、安装和恢复业务后续全部迁入 L2，再删除旧 manager 的兼容入口及这些桥接。
