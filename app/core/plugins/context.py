#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

from typing import Any, Dict


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
