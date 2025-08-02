from loguru import logger as _logger
import sys
import os
from app.utils.config import LogConfig

config = LogConfig()
LOG_DIR = config.log_dir
os.makedirs(LOG_DIR, exist_ok=True)


_logger.remove()

console_format = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green>| "
    "<level>{level: <8}</level> | "
    "<yellow>{extra[module]}</yellow>- {message}"
)

_logger.add(
    sink=sys.stderr,
    format=console_format,
    level=config.level,
    colorize=True,
    enqueue=True,
)




file_format = "{time:YYYY-MM-DD HH:mm:ss}| {level: <8} | {extra[module]}- {message}"

_logger.add(
    sink=os.path.join(LOG_DIR, "app_{time:YYYY-MM-DD}.log"),
    format=file_format,
    level=config.writelevel,
    rotation="00:00",
    retention="7 days",
    colorize=False,
    encoding="utf-8",
    enqueue=True,
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


if __name__ == "__main__":
    logger = get_logger("test1")
    logger.debug("调试信息（只在控制台显示）")
    logger.info("这是普通信息（控制台 + 文件）")
    logger.warning("这是警告")
    logger.error("发生错误")
    logger2 = get_logger("test2")
    logger2.error("发生错误")
    
    try:
        _ = 1 / 0
    except Exception:
        logger.exception("捕获异常")
