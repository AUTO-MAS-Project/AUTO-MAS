"""Config v2 八个生产根的唯一注册表与纯转换边界。"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from types import MappingProxyType
from typing import cast

from .compat import LEGACY_ROOT_FILE_NAMES
from .roots.config import (
    GlobalConfig,
    config_wire_to_legacy,
    legacy_config_to_wire,
)
from .roots.emulator import (
    Emulator,
    Emulators,
    emulators_wire_to_legacy,
    legacy_emulators_to_wire,
)
from .roots.game_sign import (
    GameSignAccounts,
    game_sign_accounts_wire_to_legacy,
    legacy_game_sign_accounts_to_wire,
)
from .roots.plan import (
    Plans,
    legacy_plans_to_wire,
    plans_wire_to_legacy,
)
from .roots.plugin_config import (
    PluginConfig,
    legacy_plugin_config_to_wire,
    plugin_config_wire_to_legacy,
)
from .roots.queue import (
    Queues,
    legacy_queues_to_wire,
    queues_wire_to_legacy,
)
from .roots.script import (
    EMULATOR_COLLECTION_NAME,
    PLAN_COLLECTION_NAME,
    SCRIPT_COLLECTION_NAME,
    Scripts,
    legacy_scripts_to_wire,
    scripts_wire_to_legacy,
)
from .roots.tools import (
    ToolsConfig,
    legacy_tools_to_wire,
    tools_wire_to_legacy,
)
from .v2.manager import config_manager
from .v2.entry import ConfigEntry
from .v2.node import ConfigNode
from .v2.node_state import NodeState
from .v2.wire import WireDict

CONFIG_ROOT_NAME = "Config"
EMULATOR_ROOT_NAME = "EmulatorConfig"
PLAN_ROOT_NAME = "PlanConfig"
SCRIPT_ROOT_NAME = "ScriptConfig"
QUEUE_ROOT_NAME = "QueueConfig"
TOOLS_ROOT_NAME = "ToolsConfig"
PLUGIN_ROOT_NAME = "PluginConfig"
GAME_SIGN_ROOT_NAME = "GameSignAccounts"

PRODUCTION_ROOT_NAMES = (
    CONFIG_ROOT_NAME,
    EMULATOR_ROOT_NAME,
    PLAN_ROOT_NAME,
    SCRIPT_ROOT_NAME,
    QUEUE_ROOT_NAME,
    TOOLS_ROOT_NAME,
    PLUGIN_ROOT_NAME,
    GAME_SIGN_ROOT_NAME,
)

PRODUCTION_ROOT_FILES = MappingProxyType(
    {
        CONFIG_ROOT_NAME: "Config.json",
        EMULATOR_ROOT_NAME: "EmulatorConfig.json",
        PLAN_ROOT_NAME: "PlanConfig.json",
        SCRIPT_ROOT_NAME: "ScriptConfig.json",
        QUEUE_ROOT_NAME: "QueueConfig.json",
        TOOLS_ROOT_NAME: "ToolsConfig.json",
        PLUGIN_ROOT_NAME: "PluginConfig.json",
        GAME_SIGN_ROOT_NAME: "GameSignAccounts.json",
    }
)

PRODUCTION_ROOT_SCHEMA = MappingProxyType(
    {
        CONFIG_ROOT_NAME: GlobalConfig,
        EMULATOR_ROOT_NAME: Emulators,
        PLAN_ROOT_NAME: Plans,
        SCRIPT_ROOT_NAME: Scripts,
        QUEUE_ROOT_NAME: Queues,
        TOOLS_ROOT_NAME: ToolsConfig,
        PLUGIN_ROOT_NAME: PluginConfig,
        GAME_SIGN_ROOT_NAME: GameSignAccounts,
    }
)

_ACTIVATION_ORDER = (
    CONFIG_ROOT_NAME,
    EMULATOR_ROOT_NAME,
    PLAN_ROOT_NAME,
    SCRIPT_ROOT_NAME,
    QUEUE_ROOT_NAME,
    TOOLS_ROOT_NAME,
    PLUGIN_ROOT_NAME,
    GAME_SIGN_ROOT_NAME,
)


class ProductionRootSetError(RuntimeError):
    """生产根集合不完整、重复注册或激活失败。"""


def _require_exact_mapping(
    value: object,
    *,
    expected: tuple[str, ...],
    label: str,
) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} 必须是根名称到对象的映射")
    if not all(isinstance(key, str) for key in value):
        raise TypeError(f"{label} 的根名称必须是字符串")
    if len(value) != len(expected) or set(value) != set(expected):
        raise ProductionRootSetError(f"{label} 不包含精确的八个生产根")
    return {name: copy.deepcopy(value[name]) for name in expected}


def legacy_production_roots_to_wire(
    legacy_roots: Mapping[str, object | None],
) -> Mapping[str, WireDict]:
    """把八个冻结 legacy JSON 根纯转换为八个原生 Wire 根。

    ``None`` 表示原文件不存在并按空根迁移。秘密值必须已经为空或为
    DPAPI 密文；旧明文的显式一次性加密属于上层迁移预处理，不允许在本
    纯转换函数中隐式发生。
    """

    legacy = _require_exact_mapping(
        legacy_roots,
        expected=LEGACY_ROOT_FILE_NAMES,
        label="legacy_roots",
    )

    def payload(file_name: str) -> object:
        value = legacy[file_name]
        return {} if value is None else value

    game_sign_legacy = payload("GameSignAccounts.json")
    converted: dict[str, WireDict] = {
        CONFIG_ROOT_NAME: legacy_config_to_wire(payload("Config.json")),
        EMULATOR_ROOT_NAME: legacy_emulators_to_wire(
            payload("EmulatorConfig.json")
        ),
        PLAN_ROOT_NAME: legacy_plans_to_wire(payload("PlanConfig.json")),
        SCRIPT_ROOT_NAME: legacy_scripts_to_wire(payload("ScriptConfig.json")),
        QUEUE_ROOT_NAME: legacy_queues_to_wire(payload("QueueConfig.json")),
        TOOLS_ROOT_NAME: legacy_tools_to_wire(
            payload("ToolsConfig.json"),
            standalone_game_sign_accounts_legacy=game_sign_legacy,
        ),
        PLUGIN_ROOT_NAME: legacy_plugin_config_to_wire(
            payload("PluginConfig.json")
        ),
        GAME_SIGN_ROOT_NAME: legacy_game_sign_accounts_to_wire(
            game_sign_legacy
        ),
    }
    return MappingProxyType(converted)


def production_wire_roots_to_legacy(
    wire_roots: Mapping[str, WireDict],
) -> Mapping[str, dict[str, object]]:
    """把完整 generation 纯转换为可供 r6 回滚的八个 JSON 形状。"""

    wire = _require_exact_mapping(
        wire_roots,
        expected=PRODUCTION_ROOT_NAMES,
        label="wire_roots",
    )
    converted: dict[str, dict[str, object]] = {
        "Config.json": config_wire_to_legacy(wire[CONFIG_ROOT_NAME]),
        "EmulatorConfig.json": emulators_wire_to_legacy(
            wire[EMULATOR_ROOT_NAME]
        ),
        "PlanConfig.json": plans_wire_to_legacy(wire[PLAN_ROOT_NAME]),
        "ScriptConfig.json": scripts_wire_to_legacy(wire[SCRIPT_ROOT_NAME]),
        "QueueConfig.json": queues_wire_to_legacy(wire[QUEUE_ROOT_NAME]),
        "ToolsConfig.json": tools_wire_to_legacy(wire[TOOLS_ROOT_NAME]),
        "PluginConfig.json": plugin_config_wire_to_legacy(
            wire[PLUGIN_ROOT_NAME]
        ),
        "GameSignAccounts.json": game_sign_accounts_wire_to_legacy(
            wire[GAME_SIGN_ROOT_NAME]
        ),
    }
    return MappingProxyType(converted)


class ProductionRoots:
    """八个生产根的精确内存集合。

    构造不注册全局 collection，也不执行 I/O。``activate()`` 先注册
    Emulator/Script 两个引用目标，再在一个 ConfigManager 事务内激活
    全部根；任一失败都会撤销注册且不会留下部分 ACTIVE 根。
    """

    def __init__(self, wires: Mapping[str, WireDict]) -> None:
        raw = _require_exact_mapping(
            wires,
            expected=PRODUCTION_ROOT_NAMES,
            label="wires",
        )
        for name, value in raw.items():
            if not isinstance(value, dict):
                raise TypeError(f"生产根 Wire 必须是对象: root={name}")

        self._roots: dict[str, ConfigNode] = {
            CONFIG_ROOT_NAME: GlobalConfig.build(
                wire=cast(WireDict, raw[CONFIG_ROOT_NAME])
            ),
            EMULATOR_ROOT_NAME: Emulators.build(
                wire=cast(WireDict, raw[EMULATOR_ROOT_NAME])
            ),
            PLAN_ROOT_NAME: Plans.build(
                wire=cast(WireDict, raw[PLAN_ROOT_NAME])
            ),
            SCRIPT_ROOT_NAME: Scripts.build(
                wire=cast(WireDict, raw[SCRIPT_ROOT_NAME])
            ),
            QUEUE_ROOT_NAME: Queues.build(
                wire=cast(WireDict, raw[QUEUE_ROOT_NAME])
            ),
            TOOLS_ROOT_NAME: ToolsConfig.build(
                wire=cast(WireDict, raw[TOOLS_ROOT_NAME])
            ),
            PLUGIN_ROOT_NAME: PluginConfig.build(
                wire=cast(WireDict, raw[PLUGIN_ROOT_NAME])
            ),
            GAME_SIGN_ROOT_NAME: GameSignAccounts.build(
                wire=cast(WireDict, raw[GAME_SIGN_ROOT_NAME])
            ),
        }
        self._collections_registered = False
        self._active = False
        self._disposed = False

    @property
    def roots(self) -> Mapping[str, ConfigNode]:
        return MappingProxyType(self._roots)

    @property
    def config(self) -> GlobalConfig:
        return cast(GlobalConfig, self._roots[CONFIG_ROOT_NAME])

    @property
    def emulators(self) -> Emulators:
        return cast(Emulators, self._roots[EMULATOR_ROOT_NAME])

    @property
    def plans(self) -> Plans:
        return cast(Plans, self._roots[PLAN_ROOT_NAME])

    @property
    def scripts(self) -> Scripts:
        return cast(Scripts, self._roots[SCRIPT_ROOT_NAME])

    @property
    def queues(self) -> Queues:
        return cast(Queues, self._roots[QUEUE_ROOT_NAME])

    @property
    def tools(self) -> ToolsConfig:
        return cast(ToolsConfig, self._roots[TOOLS_ROOT_NAME])

    @property
    def plugins(self) -> PluginConfig:
        return cast(PluginConfig, self._roots[PLUGIN_ROOT_NAME])

    @property
    def game_sign_accounts(self) -> GameSignAccounts:
        return cast(GameSignAccounts, self._roots[GAME_SIGN_ROOT_NAME])

    async def activate(self) -> None:
        if self._disposed:
            raise RuntimeError("已最终释放的生产根不可再次 activate")
        if self._active:
            return
        states = {
            root.activation_state for root in self._roots.values()
        }
        if states == {NodeState.ACTIVE}:
            self._register_reference_collections()
            self._active = True
            return
        if states != {NodeState.INACTIVE}:
            raise ProductionRootSetError(
                "生产根激活前已处于不一致的生命周期状态"
            )
        self._register_reference_collections()
        try:
            async with config_manager.transaction():
                for name in _ACTIVATION_ORDER:
                    await self._roots[name].activate()
        except BaseException:
            self._unregister_reference_collections()
            if any(
                root.activation_state != NodeState.INACTIVE
                for root in self._roots.values()
            ):
                raise ProductionRootSetError(
                    "生产根激活失败后留下了部分活动状态"
                ) from None
            raise
        self._active = True

    def close(self) -> None:
        """可逆地撤销引用目标注册；仅允许在没有活动事务时调用。

        ``close()`` 后可由 ``activate()`` 恢复同一组 ACTIVE 根，故不能在此
        断开其 ref 订阅。进程级最终关闭请使用 ``dispose()``。
        """

        if config_manager.in_transaction:
            raise RuntimeError("活动配置事务中不能关闭生产根")
        self._unregister_reference_collections()
        self._active = False

    def dispose(self) -> None:
        """最终释放生产根持有的 ref 订阅并注销引用集合。

        该操作不可逆，供权威运行时结束时使用。显式断连不能依赖 GC 回收弱
        receiver，否则 Blinker 在后续事务复制 signal 时可能并发清理其映射。
        """

        if config_manager.in_transaction:
            raise RuntimeError("活动配置事务中不能释放生产根")
        if self._disposed:
            return
        self._disconnect_reference_receivers()
        self._unregister_reference_collections()
        self._active = False
        self._disposed = True

    def _disconnect_reference_receivers(self) -> None:
        """遍历全部仍可达节点，先于 registry 注销精确断连 ref receiver。"""

        pending = list(self._roots.values())
        while pending:
            node = pending.pop()
            if node.deleted:
                continue
            if isinstance(node, ConfigEntry):
                node._disconnect_ref_receivers()
            pending.extend(node.iter_children())

    def _register_reference_collections(self) -> None:
        if self._collections_registered:
            return
        registered: list[str] = []
        try:
            config_manager.register_collection(
                EMULATOR_COLLECTION_NAME,
                self.emulators,
            )
            registered.append(EMULATOR_COLLECTION_NAME)
            config_manager.register_collection(
                PLAN_COLLECTION_NAME,
                self.plans,
            )
            registered.append(PLAN_COLLECTION_NAME)
            config_manager.register_collection(
                SCRIPT_COLLECTION_NAME,
                self.scripts,
            )
            registered.append(SCRIPT_COLLECTION_NAME)
        except BaseException:
            for name in reversed(registered):
                config_manager.unregister_collection(name)
            raise
        self._collections_registered = True

    def _unregister_reference_collections(self) -> None:
        if not self._collections_registered:
            return
        for name, expected in (
            (SCRIPT_COLLECTION_NAME, self.scripts),
            (PLAN_COLLECTION_NAME, self.plans),
            (EMULATOR_COLLECTION_NAME, self.emulators),
        ):
            try:
                actual = config_manager.get_collection(name)
            except LookupError:
                continue
            if actual is expected:
                config_manager.unregister_collection(name)
        self._collections_registered = False


__all__ = [
    "CONFIG_ROOT_NAME",
    "EMULATOR_ROOT_NAME",
    "GAME_SIGN_ROOT_NAME",
    "PLAN_ROOT_NAME",
    "PLUGIN_ROOT_NAME",
    "PRODUCTION_ROOT_FILES",
    "PRODUCTION_ROOT_NAMES",
    "PRODUCTION_ROOT_SCHEMA",
    "ProductionRootSetError",
    "ProductionRoots",
    "QUEUE_ROOT_NAME",
    "SCRIPT_ROOT_NAME",
    "TOOLS_ROOT_NAME",
    "legacy_production_roots_to_wire",
    "production_wire_roots_to_legacy",
]
