#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

from pathlib import Path
from typing import Any, Dict

from .cache_store import PluginCacheManager


class PluginContext:
    """Plugin-facing context object that exposes controlled MAS capabilities."""

    def __init__(
        self,
        *,
        plugin_name: str,
        instance_id: str | None = None,
        config: Dict[str, Any],
        logger,
        events,
        runtime,
    ) -> None:
        self.plugin_name = plugin_name
        self.instance_id = instance_id or plugin_name
        self.config = config
        self.logger = logger
        self.events = events
        self.runtime = runtime
        self.cache = PluginCacheManager(
            plugin_name=self.plugin_name,
            instance_id=self.instance_id,
            data_root=Path.cwd() / "data",
            logger=self.logger,
        )
