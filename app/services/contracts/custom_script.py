"""脚本启动命令契约；执行、等待、错误报告归共享服务。"""

from pathlib import Path
from typing import Protocol


class ScriptCommandAPI(Protocol):
    def build(self, script_path: Path) -> list[str] | None: ...
