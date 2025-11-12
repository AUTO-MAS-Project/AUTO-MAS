#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


from loguru import logger as _logger
import sys
from pathlib import Path

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


def get_logger(module_name: str):
    """
    获取一个绑定 module 名的日志器

    :param module_name: 模块名称, 如 "用户管理"
    :return: 绑定后的 logger
    """
    return _logger.bind(module=module_name)


__all__ = ["get_logger"]
