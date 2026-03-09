#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

from pathlib import Path
from typing import Any, Dict

from app.utils import get_logger

from .event_bus import EventBus
from .loader import PluginLoader


logger = get_logger("插件管理器")


class _PluginManager:
    """Coordinates plugin lifecycle and exposes event APIs for MAS core."""

    def __init__(self) -> None:
        self.started = False
        self.events = EventBus()
        self.runtime: Dict[str, Any] = {}
        self.loader = PluginLoader(
            events=self.events,
            runtime=self.runtime,
            plugins_dir=Path.cwd() / "plugins",
        )

    async def start(self) -> None:
        if self.started:
            logger.warning("插件系统已启动，忽略重复启动")
            return

        await self.loader.load_all()
        self.started = True
        logger.info("插件系统启动完成")

    async def stop(self) -> None:
        if not self.started:
            return

        await self.loader.unload_all()
        self.events.clear()
        self.started = False
        logger.info("插件系统已关闭")

    def on(self, event: str, handler) -> None:
        self.events.on(event, handler)

    def off(self, event: str, handler) -> None:
        self.events.off(event, handler)

    def emit(self, event: str, payload: Any = None) -> None:
        self.events.emit(event, payload)

    def list_plugins(self) -> Dict[str, str]:
        return {name: record.status for name, record in self.loader.records.items()}


PluginManager = _PluginManager()
