#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

from dataclasses import dataclass
from typing import Any, Callable, Final, Literal


EventScope = Literal["global", "instance"]
"""事件作用域：global 表示全局广播，instance 表示仅实例内可见。"""

EventErrorPolicy = Literal["continue", "raise"]
"""事件错误策略：continue 表示记录后继续，raise 表示向上抛出。"""

EVENT_METADATA_ATTR: Final[str] = "__mas_event_subscriptions__"
"""装饰器元数据在函数对象上的挂载属性名。"""


@dataclass(frozen=True)
class EventSubscription:
    """装饰器声明的监听元数据。"""

    event: str
    priority: int = 0
    scope: EventScope = "instance"
    once: bool = False
    error_policy: EventErrorPolicy | None = None


def on_event(
    event: object,
    *,
    priority: int = 0,
    scope: EventScope = "instance",
    once: bool = False,
    error_policy: EventErrorPolicy | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    声明函数或方法为插件事件监听器。

    Args:
        event (str): 监听的事件名。
        priority (int): 监听器优先级，数值越大越先执行。
        scope (EventScope): 监听作用域，可选 global 或 instance。
        once (bool): 是否只监听一次，触发后自动解绑。
        error_policy (EventErrorPolicy | None): 监听器级错误策略，None 表示继承事件默认策略。

    Returns:
        Callable[[Callable[..., Any]], Callable[..., Any]]: 装饰器函数。

    Raises:
        TypeError: `event` 不是字符串时抛出。
        ValueError: `event` 为空字符串时抛出。
        ValueError: `scope` 不在允许值集合时抛出。
        ValueError: `error_policy` 不在允许值集合且不为 None 时抛出。
    """
    if not isinstance(event, str):
        raise TypeError("event 必须是字符串")

    normalized_event = event.strip()
    if not normalized_event:
        raise ValueError("event 不能为空字符串")

    if scope not in {"global", "instance"}:
        raise ValueError("scope 仅支持 global 或 instance")

    if error_policy not in {None, "continue", "raise"}:
        raise ValueError("error_policy 仅支持 None、continue 或 raise")

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        subscriptions = list(getattr(func, EVENT_METADATA_ATTR, []))
        subscriptions.append(
            EventSubscription(
                event=normalized_event,
                priority=int(priority),
                scope=scope,
                once=bool(once),
                error_policy=error_policy,
            )
        )
        setattr(func, EVENT_METADATA_ATTR, subscriptions)
        return func

    return decorator


def get_event_subscriptions(target: Any) -> list[EventSubscription]:
    """
    读取目标对象上通过 `@on_event` 声明的监听元数据。

    Args:
        target (Any): 目标函数或绑定方法对象。

    Returns:
        list[EventSubscription]: 监听元数据列表；若不存在则返回空列表。
    """
    raw = getattr(target, EVENT_METADATA_ATTR, None)
    if not isinstance(raw, list):
        return []

    result: list[EventSubscription] = []
    for item in raw:
        if isinstance(item, EventSubscription):
            result.append(item)
    return result
