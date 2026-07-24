"""框架内部日志工具。"""

from __future__ import annotations

import logging


def get_logger(module_name: str) -> logging.Logger:
    """获取 ``app.configuration.<module_name>`` 命名空间的 Logger。"""
    logger = logging.getLogger(f"app.configuration.{module_name}")
    root = logging.getLogger("app.configuration")
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(levelname)s | %(name)s | %(message)s")
        )
        root.addHandler(handler)
        root.setLevel(logging.WARNING)
    return logger
