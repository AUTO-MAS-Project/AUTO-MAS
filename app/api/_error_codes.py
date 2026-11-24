from pydantic import ValidationError

from app.config.errors import ConfigAggregateError

_CONFLICT_HINTS = ("已锁定", "锁定", "locked", "busy", "正在运行", "冲突")


def config_error_code(exc: Exception) -> int:
    """将配置写操作异常归类为稳定业务状态码（409 锁定/冲突、422 校验错误、500 内部异常）。"""
    message = str(exc).lower()
    if isinstance(exc, (ValueError, RuntimeError)) and any(
        hint in message for hint in _CONFLICT_HINTS
    ):
        return 409
    if isinstance(exc, (ValidationError, ConfigAggregateError, ValueError, KeyError)):
        return 422
    return 500
