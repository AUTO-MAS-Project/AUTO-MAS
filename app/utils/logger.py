#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025-2026 AUTO-MAS Team

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

from collections.abc import Callable
from typing import Any, Protocol, TypeVar, overload

from loguru import logger as _logger
import sys
from pathlib import Path


F = TypeVar("F", bound=Callable[..., Any])


class LoggerLike(Protocol):
    def bind(self, *args: Any, **kwargs: Any) -> "LoggerLike": ...

    def debug(self, __message: object, *args: Any, **kwargs: Any) -> None: ...

    def info(self, __message: object, *args: Any, **kwargs: Any) -> None: ...

    def success(self, __message: object, *args: Any, **kwargs: Any) -> None: ...

    def warning(self, __message: object, *args: Any, **kwargs: Any) -> None: ...

    def error(self, __message: object, *args: Any, **kwargs: Any) -> None: ...

    def exception(self, __message: object, *args: Any, **kwargs: Any) -> None: ...

    def level(self, *args: Any, **kwargs: Any) -> Any: ...

    def opt(self, *args: Any, **kwargs: Any) -> "LoggerLike": ...

    def log(self, *args: Any, **kwargs: Any) -> None: ...

    @overload
    def catch(self, function: F, /) -> F: ...

    @overload
    def catch(
        self,
        exception: type[BaseException] = Exception,
        *,
        level: str = "ERROR",
        reraise: bool = False,
        onerror: Callable[[BaseException], Any] | None = None,
        exclude: Any | None = None,
        default: Any | None = None,
        message: str = "An error has been caught",
    ) -> Callable[[F], F]: ...

(Path.cwd() / "debug").mkdir(parents=True, exist_ok=True)


_logger.remove()


_logger.add(
    sink=Path.cwd() / "debug/app.log",
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{extra[module]}</cyan> | <level>{message}</level>",
    enqueue=True,
    backtrace=True,
    diagnose=True,
    rotation="1 week",
    retention="1 month",
    compression="zip",
)

_logger.add(
    sink=sys.stderr,
    level="DEBUG",
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{extra[module]}</cyan> | <level>{message}</level>",
    enqueue=True,
    backtrace=True,
    diagnose=True,
    colorize=True,
)


_logger = _logger.patch(lambda record: record["extra"].setdefault("module", "未知模块"))


def get_logger(module_name: str) -> LoggerLike:
    """
    获取指定模块名的日志记录器

    Args:
        module_name (str): 模块名称

    Returns:
        loguru.Logger: 日志记录器实例
    """
    return _logger.bind(module=module_name)


__all__ = ["LoggerLike", "get_logger"]
