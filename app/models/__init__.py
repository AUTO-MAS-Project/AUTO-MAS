from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .common import EmulatorConfig, QueueConfig, QueueItem, TimeSet, Webhook
    from .general import GeneralConfig, GeneralUserConfig
    from .global_config import CLASS_BOOK, GlobalConfig, ToolsConfig
    from .maa import MaaConfig, MaaPlanConfig, MaaUserConfig
    from .maaend import MaaEndConfig, MaaEndUserConfig
    from .plugin import PluginInstanceConfig
    from .src import SrcConfig, SrcUserConfig


__all__ = [
    "EmulatorConfig",
    "Webhook",
    "QueueItem",
    "TimeSet",
    "QueueConfig",
    "MaaPlanConfig",
    "MaaUserConfig",
    "MaaConfig",
    "MaaEndUserConfig",
    "MaaEndConfig",
    "PluginInstanceConfig",
    "SrcUserConfig",
    "SrcConfig",
    "GeneralUserConfig",
    "GeneralConfig",
    "ToolsConfig",
    "GlobalConfig",
    "CLASS_BOOK",
]


def __getattr__(name: str):
    if name in {"emulator", "task"}:
        import importlib

        return importlib.import_module(f"{__name__}.{name}")

    if name in {
        "EmulatorConfig",
        "QueueConfig",
        "QueueItem",
        "TimeSet",
        "Webhook",
    }:
        from .common import EmulatorConfig, QueueConfig, QueueItem, TimeSet, Webhook

        return {
            "EmulatorConfig": EmulatorConfig,
            "QueueConfig": QueueConfig,
            "QueueItem": QueueItem,
            "TimeSet": TimeSet,
            "Webhook": Webhook,
        }[name]

    if name in {"GeneralConfig", "GeneralUserConfig"}:
        from .general import GeneralConfig, GeneralUserConfig

        return {
            "GeneralConfig": GeneralConfig,
            "GeneralUserConfig": GeneralUserConfig,
        }[name]

    if name in {"CLASS_BOOK", "GlobalConfig", "ToolsConfig"}:
        from .global_config import CLASS_BOOK, GlobalConfig, ToolsConfig

        return {
            "CLASS_BOOK": CLASS_BOOK,
            "GlobalConfig": GlobalConfig,
            "ToolsConfig": ToolsConfig,
        }[name]

    if name in {"MaaConfig", "MaaPlanConfig", "MaaUserConfig"}:
        from .maa import MaaConfig, MaaPlanConfig, MaaUserConfig

        return {
            "MaaConfig": MaaConfig,
            "MaaPlanConfig": MaaPlanConfig,
            "MaaUserConfig": MaaUserConfig,
        }[name]

    if name in {"MaaEndConfig", "MaaEndUserConfig"}:
        from .maaend import MaaEndConfig, MaaEndUserConfig

        return {
            "MaaEndConfig": MaaEndConfig,
            "MaaEndUserConfig": MaaEndUserConfig,
        }[name]

    if name == "PluginInstanceConfig":
        from .plugin import PluginInstanceConfig

        return PluginInstanceConfig

    if name in {"SrcConfig", "SrcUserConfig"}:
        from .src import SrcConfig, SrcUserConfig

        return {
            "SrcConfig": SrcConfig,
            "SrcUserConfig": SrcUserConfig,
        }[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
