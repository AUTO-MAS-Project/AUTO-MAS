"""框架内部共享常量。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

DEFAULT_DATETIME = datetime.strptime("2000-01-01 00:00:00", "%Y-%m-%d %H:%M:%S")
"""日期/时间校验失败时的默认回退时刻。"""

DEFAULT_FILE_PATH = Path("")
"""文件路径纠正失败 / 未设置时的默认回退（空路径，落盘为 ``\"\"``）。"""

ENCRYPTED_PREFIX = "DPAPI:"
"""加密密文落盘前缀。"""
