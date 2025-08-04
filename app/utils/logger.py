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
    :param module_name: 模块名称，如 "用户管理"
    :return: 绑定后的 logger
    """
    return _logger.bind(module=module_name)


__all__ = ["get_logger"]
