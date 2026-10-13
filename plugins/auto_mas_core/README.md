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
