#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

from collections import defaultdict
from typing import Any, Callable, DefaultDict, Dict, List

from app.utils import get_logger


logger = get_logger("插件事件总线")


class EventBus:
    """In-process event bus used by MAS core and plugins."""

    def __init__(self) -> None:
        self._handlers: DefaultDict[str, List[Callable[[Any], None]]] = defaultdict(list)

    def on(self, event: str, handler: Callable[[Any], None]) -> None:
        if handler not in self._handlers[event]:
            self._handlers[event].append(handler)

    def off(self, event: str, handler: Callable[[Any], None]) -> None:
        if event not in self._handlers:
            return
        try:
            self._handlers[event].remove(handler)
        except ValueError:
            return
        if not self._handlers[event]:
            del self._handlers[event]

    def emit(self, event: str, payload: Any = None) -> None:
        handlers = list(self._handlers.get(event, []))
        for handler in handlers:
            try:
                handler(payload)
            except Exception as e:
                logger.exception(f"事件处理失败: event={event}, handler={handler}, error={e}")

    def clear(self) -> None:
        self._handlers.clear()

    @property
    def handler_count(self) -> Dict[str, int]:
        return {event: len(handlers) for event, handlers in self._handlers.items()}
