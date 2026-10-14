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

## 禁令

- 允许：`from auto_mas_core import …` / `auto_mas_core.utils` / `auto_mas_core.services` / `auto_mas_core.plugin`
- 禁止：`from app.plugin …` / `from app.core …`（仅本包再导出实现时可碰 `app.*`）

## 获取方式

- 主程序 / 本地开发：仓库根 `uv` workspace（`uv sync`）editable 安装本目录
- 已发布第三方插件：同一发行名 `auto_mas_core` 的发行依赖

## 协议版本

`PLUGIN_API_VERSION` 主版本现为 `"6"`；与框架不兼容时提升主版本，加载阶段拒绝主版本不一致的插件。

包内 `py.typed` 为 PEP 561 标记，须随 wheel 发布。

## 宿主通知能力

宿主在 `pre_enable` 前绑定 `BasePlugin.notifications`，插件构造签名不变。
插件使用注入接口提交内容；渠道选择、渲染、重试和签到摘要仍由宿主既有流程处理。

```python
from auto_mas_core import BasePlugin
from auto_mas_core.notify import NotifyPayload
from auto_mas_core.utils import get_logger


class PLUGIN(BasePlugin):
    async def send_notice(self) -> None:
        result = await self.notifications.send_global(
            NotifyPayload(title="通知标题", text="通知正文"), include_system=True
        )
        # attempted == 0 表示本次没有尝试投递，不能当作已送达。
        if result.failed:
            get_logger("demo").warning(f"通知投递失败: {result.failed}")
```

`send_user(payload, user_config)` 使用账号独立通知配置；
`send_statistics(payload, user_config)` 复用全局和账号统计开关；
`push_proxy_result(...)` 复用代理结果时机、模板、图片和签到摘要投递记录。
接口类型可从 `auto_mas_core.notify` 导入 `NotificationService`。
独立实例可调用 `bind_notifications()` 绑定替身。

旧 `auto_mas_core.notify` 全局函数与 `auto_mas_core.services.Notify` 保留兼容；
外部专项消费方的迁移另行处理。仅导入通知契约和消息类型不会初始化宿主通知实现。
