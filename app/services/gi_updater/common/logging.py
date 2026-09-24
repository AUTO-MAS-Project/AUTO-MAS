#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""引擎的日志出口：把 ``%`` 风格的调用转接到宿主的 loguru。

引擎内部按 ``logger.info("已迁移 %d 个文件：%s", count, path)`` 这种惰性格式写日志，
而 loguru 用 ``{}`` 占位，两者不能直接混用。本模块是唯一做这条转换的地方，
调用方不需要改写法。

级别只用到 ``debug`` / ``info`` / ``warning`` / ``error``，与 loguru 同名方法一一对应。
"""

from __future__ import annotations

from typing import Any

__all__ = ["get_logger"]


class PercentStyleLogger:
    """把 ``%`` 惰性格式化转发给 loguru 的薄壳。"""

    def __init__(self, name: str = "原神更新") -> None:
        """绑定一个宿主 logger。

        Args:
            name: loguru 的模块名（进日志的 ``extra[module]`` 列）。
        """
        from app.utils import get_logger as host_get_logger

        self._logger = host_get_logger(name)

    def _emit(self, level: str, message: Any, args: tuple[Any, ...]) -> None:
        """按 ``level`` 输出一条消息，参数缺失或格式不匹配时降级为拼接。

        Args:
            level: loguru 的方法名。
            message: 日志正文，可能是 ``%`` 模板。
            args: 位置参数；为空表示不做格式化。
        """
        if not args:
            text = message if isinstance(message, str) else str(message)
        else:
            try:
                text = str(message) % args
            except (TypeError, ValueError):
                # 模板与参数对不上是日志本身的问题，不能让它掀掉正在跑的流程
                text = " ".join([str(message), *[repr(a) for a in args]])
        getattr(self._logger, level)(text)

    def debug(self, message: Any, *args: Any) -> None:
        """输出 DEBUG 级日志。"""
        self._emit("debug", message, args)

    def info(self, message: Any, *args: Any) -> None:
        """输出 INFO 级日志。"""
        self._emit("info", message, args)

    def warning(self, message: Any, *args: Any) -> None:
        """输出 WARNING 级日志。"""
        self._emit("warning", message, args)

    def error(self, message: Any, *args: Any) -> None:
        """输出 ERROR 级日志。"""
        self._emit("error", message, args)


_CACHE: dict[str, PercentStyleLogger] = {}


def get_logger(name: str = "原神更新") -> PercentStyleLogger:
    """取引擎用的 logger（按名字复用同一个实例）。

    Args:
        name: loguru 的模块名，默认整包共用「原神更新」。

    Returns:
        :class:`PercentStyleLogger` 实例。
    """
    cached = _CACHE.get(name)
    if cached is None:
        cached = _CACHE[name] = PercentStyleLogger(name)
    return cached
