"""插件配置的命令分派与取消策略；普通配置沿用基础框架的 Trigger 行为。"""

from collections.abc import Callable
from typing import TypeVar

from app.config import ConfigEntry
from app.config import trigger_field as config_trigger_field

_F = TypeVar("_F", bound=Callable)


def trigger_field(path: str, *, cancellable: bool = True) -> Callable[[_F], _F]:
    """注册插件配置触发器，并声明 Operations 是否允许取消该命令。"""

    def decorate(func: _F) -> _F:
        """复用配置字段绑定，将取消策略附在业务处理方法上供插件操作管理读取。"""
        setattr(func, "__trigger_cancellable__", cancellable)
        return config_trigger_field(path)(func)

    return decorate


class PluginCommandEntry(ConfigEntry):
    """插件相关配置的公共上界，确保赋值和 update 触发的命令也纳入生命周期管理。"""

    def _dispatch_trigger(self, group: str, field: str, value: object = True) -> None:
        """将已通过配置字段校验的触发请求交给插件操作管理，配置更新不返回命令身份。"""
        from app.core.plugin.operations import Operations

        Operations.submit(self, group=group, field=field, value=value)
