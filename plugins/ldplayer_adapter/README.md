# 雷电模拟器游戏适配

贡献游戏类型 `ldplayer`。依赖 `auto_mas_core>=6,<7`：

```python
from auto_mas_core import GameAdapterPlugin, GameEntry, GameInstanceEntry
from auto_mas_core.utils import ProcessRunner, get_logger, get_setting
```

本插件自带 `manager` / `handle` / `schema` / `search`，无共享 sibling 库。
