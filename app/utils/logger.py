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


import os

# Sentry 的 Loguru 集成会自行 ``logger.add(...)`` 且不传 diagnose，
# 该 sink 会吃下 Loguru 的全局默认值并把局部变量值渲染进日志正文随事件外发。
# 本文件是后端唯一导入 Loguru 的位置，在导入前收紧默认值即可覆盖该 sink；
# 下方本项目自有的 sink 均显式传入 diagnose=False，不受影响。
os.environ.setdefault("LOGURU_DIAGNOSE", "NO")

from loguru import logger as _logger
import sys
from pathlib import Path

from .security import sanitize_log_message

(Path.cwd() / "debug").mkdir(parents=True, exist_ok=True)


_logger.remove()


def _sanitize_record(record):
    """在每个 Loguru sink 写出前过滤敏感字段。"""

    record["message"] = sanitize_log_message(str(record["message"]))
    return True


_logger.add(
    sink=Path.cwd() / "debug/app.log",
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{extra[module]}</cyan> | <level>{message}</level>",
    filter=_sanitize_record,
    enqueue=True,
    backtrace=True,
    diagnose=False,
    rotation="1 week",
    retention="1 month",
    compression="zip",
)

_logger.add(
    sink=sys.stderr,
    level="DEBUG",
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{extra[module]}</cyan> | <level>{message}</level>",
    filter=_sanitize_record,
    enqueue=True,
    backtrace=True,
    diagnose=False,
    colorize=True,
)


_logger = _logger.patch(lambda record: record["extra"].setdefault("module", "未知模块"))


def get_logger(module_name: str):
    """
    获取指定模块名的日志记录器

    Args:
        module_name (str): 模块名称

    Returns:
        loguru.Logger: 日志记录器实例
    """
    return _logger.bind(module=module_name)


__all__ = ["get_logger"]
