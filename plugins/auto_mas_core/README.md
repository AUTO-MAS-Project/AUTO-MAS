# auto_mas_core

AUTO-MAS 插件协议包与开发者 SDK（发行名 `auto_mas_core`，import 名 `auto_mas_core`）。

## 使用

```python
from auto_mas_core import BasePlugin, Config, PLUGIN, plugin_route
from auto_mas_core.utils import get_logger, ProcessManager
from auto_mas_core.services import Notify  # 宿主业务服务
from auto_mas_core.plugin import services, http  # 跨插件总线 / HTTP 挂载


class PLUGIN(BasePlugin):  # 或顶层导出名为 PLUGIN 的子类
    async def on_enable(self) -> None:
        get_logger("demo").info("enabled, config=%s", self.config)
```

导入路径对照：

| 路径 | 含义 |
|------|------|
| `auto_mas_core.services` | 宿主 `Matomo` / `Notify` / `System` / `Updater` |
| `auto_mas_core.plugin.services` | 跨插件 `ServiceRegistry`（与 `Plugin.services` 同一实例） |
| `auto_mas_core.plugin.http` | 插件 HTTP 挂载表 |

插件依赖：

```toml
dependencies = [
  "auto_mas_core>=6,<7",
]
```

## 适配器与宿主接线

游戏和脚本适配器仍通过 `GameTypeDecl` / `ScriptTypeDecl` 声明类型。
类型登记、锁检查及失败回滚由宿主负责：`PluginManager` 在构造适配器后、
调用 `pre_enable` 前注入 `AdapterRuntime`。原有 `system_enable`、
`system_disable`、`system_rollback` 入口保留；覆写这些入口的插件仍需调用
`super()`，以执行宿主系统阶段。

- `self.instances()` 只提供该适配器类型的配置实例。返回的是配置节点，遵循已有锁与提交规则。
- `GameControl.runtime` 提供只读 `GameRuntime` 策略：`silent` 与 `block_ad`。
  宿主在创建控制器时绑定，每次读取都反映最新设置。
- 适配器与控制器的构造签名保持不变。直接构造测试替身时，须先调用
  `bind_runtime()` 注入实现，再使用依赖宿主的入口。

新适配逻辑应使用这些窄接口。SDK 的 `Config` / `Plugin` 等遗留导出仍保留，
外部脚本适配器及服务、worker 的依赖边界尚待后续迁移。

## 禁令

- 允许：`from auto_mas_core import …` / `auto_mas_core.utils` / `auto_mas_core.services` / `auto_mas_core.plugin`
- 禁止：`from app.plugin …` / `from app.core …`（仅本包再导出实现时可碰 `app.*`）

## 获取方式

- 主程序 / 本地开发：仓库根 `uv` workspace（`uv sync`）editable 安装本目录
- 已发布第三方插件：同一发行名 `auto_mas_core` 的发行依赖

## 协议版本

`PLUGIN_API_VERSION` 主版本现为 `"6"`；与框架不兼容时提升主版本，加载阶段拒绝主版本不一致的插件。

包内 `py.typed` 为 PEP 561 标记，须随 wheel 发布。

## Worker 历史写入

`HistoryWriter` 是模式执行器使用的窄协议，只提供与现有历史存储一致的
`save()` 写入契约。`ModeWorker.save_result()` 使用绑定的写入器；结果判定仍由
`build_history_data()` 提供，日志与统计的落盘参数保持原样。

宿主在启动任务前，通过 `bind_history_writer()` 绑定原历史存储，沿
`ScriptExpander → UserExpander → ModeWorker` 传递。各层构造签名不变，
子类沿用基类展开流程时自动获得同一个写入器。

直接构造 Worker 或展开层进行隔离执行时，须在运行前调用
`bind_history_writer()` 注入实现；覆写展开流程、自行创建下一层时也须传递该绑定。
写入器可以替换为测试实现，无需 Worker 访问宿主全局存储。

## 插件服务消费

插件通过宿主绑定的 `self.services` 查询跨插件服务，其类型为 SDK 导出的
`ServiceResolver`，只提供 `get(name, default=None)` 和 `require(name)`。
查询读取宿主现有注册表，提供者启停、重载及退出密封会即时反映，不缓存服务值。
服务仍通过 `provides_services` 声明，由宿主登记和注销。

宿主在 `pre_enable()` 前调用 `bind_services()` 完成绑定；`requires` 提供者仍按
原依赖顺序，在本插件的 `on_enable()` 前启用。`pre_enable()` 可查询现有服务，
不能据此假定尚未启用的提供者已可用。

```python
from auto_mas_core import BasePlugin


class PLUGIN(BasePlugin):
    requires = ("demo.lookup",)

    async def on_enable(self) -> None:
        lookup = self.services.require("demo.lookup")
        lookup("ready")
```

直接构造插件做隔离验证时，先 `bind_services()` 注入查询替身。
旧 `auto_mas_core.plugin.services` 与顶层 `Plugin` 导出继续保留兼容；
新服务消费逻辑使用实例查询接口。宿主业务服务 `auto_mas_core.services`
（通知、更新等）仍沿用原入口，属于后续迁移范围。

## 默认配置会话

脚本未指定账号的 `SCRIPT_CONFIG` 会话由 `UserExpander` 创建临时 `Default` 用户。
宿主 `ScriptExpander` 在启动展开层前调用
`bind_default_user_factory(decl.user_type.build)`；插件现有构造签名不变。
独立运行展开层时，也需绑定用户工厂；普通账号任务不使用该工厂。

工厂接收 `uid` 和 `payload` 两个关键字参数，返回尚未激活的用户配置节点。
展开层沿用 `uuid5(script_entry.uid, "Default")`、脚本配置来源和关闭常规配置覆写的设置，
随后激活节点；节点只进入本次任务树，不加入脚本的持久化账号集合。
