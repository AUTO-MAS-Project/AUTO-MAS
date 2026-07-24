"""AUTO-MAS 原生 Config v2 生产根。"""

from .config import (
    CustomWebhooks,
    GlobalConfig,
    Webhook,
    config_wire_to_legacy,
    legacy_config_to_wire,
)
from .emulator import (
    Emulator,
    Emulators,
    emulators_wire_to_legacy,
    legacy_emulators_to_wire,
)
from .game_sign import (
    GameSignAccount,
    GameSignAccounts,
    GameSignAccountsOwnershipConflictError,
    assert_game_sign_accounts_ownership_consistent,
    game_sign_accounts_wire_to_legacy,
    get_embedded_game_sign_accounts,
    legacy_game_sign_accounts_to_wire,
)
from .plan import (
    MaaPlan,
    Plans,
    legacy_plans_to_wire,
    plans_wire_to_legacy,
)
from .plugin_config import (
    PluginConfig,
    PluginInstance,
    PluginInstanceCollection,
    legacy_plugin_config_to_wire,
    plugin_config_wire_to_legacy,
)
from .queue import (
    Queue,
    QueueItem,
    QueueItemCollection,
    Queues,
    TimeSet,
    TimeSetCollection,
    legacy_queues_to_wire,
    queues_wire_to_legacy,
)
from .tools import (
    ToolsConfig,
    legacy_tools_to_wire,
    tools_wire_to_legacy,
)

__all__ = [
    "Emulator",
    "Emulators",
    "CustomWebhooks",
    "GlobalConfig",
    "GameSignAccount",
    "GameSignAccounts",
    "GameSignAccountsOwnershipConflictError",
    "MaaPlan",
    "Plans",
    "PluginConfig",
    "PluginInstance",
    "PluginInstanceCollection",
    "Queue",
    "QueueItem",
    "QueueItemCollection",
    "Queues",
    "TimeSet",
    "TimeSetCollection",
    "ToolsConfig",
    "Webhook",
    "assert_game_sign_accounts_ownership_consistent",
    "config_wire_to_legacy",
    "emulators_wire_to_legacy",
    "game_sign_accounts_wire_to_legacy",
    "get_embedded_game_sign_accounts",
    "legacy_emulators_to_wire",
    "legacy_config_to_wire",
    "legacy_game_sign_accounts_to_wire",
    "legacy_plans_to_wire",
    "legacy_plugin_config_to_wire",
    "legacy_queues_to_wire",
    "legacy_tools_to_wire",
    "plans_wire_to_legacy",
    "plugin_config_wire_to_legacy",
    "queues_wire_to_legacy",
    "tools_wire_to_legacy",
]
