# Windows 通用进程游戏适配

贡献游戏类型 `general`。依赖 `auto_mas_core>=6,<7`：

```python
from auto_mas_core import GameAdapterPlugin, GameEntry, GameInstanceEntry
from auto_mas_core.utils import ProcessManager, get_logger
```

本插件自带 `manager` / `handle` / `schema`；`search` 恒返回空（需手动指定路径）。
