"""OK-WW script adapter plugin."""

from .plugin import Plugin
from .schema import Config, OkwwConfig, OkwwUserConfig, PluginConfig

__all__ = ["Plugin", "Config", "PluginConfig", "OkwwConfig", "OkwwUserConfig"]
