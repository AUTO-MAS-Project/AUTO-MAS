#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright 漏 2024-2025 DLmaster361
#   Copyright 漏 2025 MoeSnowyFox
#   Copyright 漏 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

import sys
from pathlib import Path
from typing import Any

from loguru import logger as _logger

LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{extra[module]}</cyan> | "
    "<level>{message}</level>"
)

(Path.cwd() / "debug").mkdir(parents=True, exist_ok=True)

_logger.remove()


def _add_logger_sink(*, sink: Any, level: str, colorize: bool = False, **kwargs: Any) -> None:
    """添加日志输出，队列不可用时自动降级。"""

    add_kwargs = {
        "sink": sink,
        "level": level,
        "format": LOG_FORMAT,
        "enqueue": True,
        "backtrace": True,
        "diagnose": True,
        "colorize": colorize,
        **kwargs,
    }

    try:
        _logger.add(**add_kwargs)
    except (PermissionError, OSError):
        add_kwargs["enqueue"] = False
        _logger.add(**add_kwargs)


_add_logger_sink(
    sink=Path.cwd() / "debug/app.log",
    level="INFO",
    rotation="1 week",
    retention="1 month",
    compression="zip",
)

_add_logger_sink(
    sink=sys.stderr,
    level="DEBUG",
    colorize=True,
)

_logger = _logger.patch(lambda record: record["extra"].setdefault("module", "未知模块"))


def get_logger(module_name: str):
    """
    获取指定模块名称的日志记录器。

    Args:
        module_name (str): 模块名称。

    Returns:
        loguru.Logger: 绑定模块字段后的日志记录器。
    """

    return _logger.bind(module=module_name)


__all__ = ["get_logger"]
