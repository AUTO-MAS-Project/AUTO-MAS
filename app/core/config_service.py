"""配置服务：统一配置入口。

根据 AUTO_MAS_CONFIG_V2_MODE 路由到 legacy 或 v2。
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import threading
from pathlib import Path
from typing import Any

from app.utils import get_logger

from app.configuration import (
    CONFIG_V2_MODE,
    CONFIG_V2_MODE_AUTHORITATIVE,
    CONFIG_V2_MODE_OFF,
    CONFIG_V2_MODE_SHADOW,
    WireDict,
    assert_config_v2_startup_mode_ready,
)
from app.configuration.compat import legacy_adapter
from app.configuration.runtime import configure_outbox_hooks, shutdown_runtime

logger = get_logger("配置服务")

type LegacyConfigRoot = Any


def configure_config_save_observer(observer: Any) -> None:
    """Lazy legacy hook shim kept patchable for lifecycle integrations."""

    from app.models.ConfigBase import (
        configure_config_save_observer as configure_legacy_observer,
    )

    configure_legacy_observer(observer)


_CONFIG_SERVICE_OWNER_GUARD = threading.Lock()
_CONFIG_SERVICE_OWNER: object | None = None


def _claim_config_service_owner(owner_token: object) -> None:
    """Claim the process-global Config v2 hooks without awaiting.

    The hooks, codec registry, and legacy save observer are process-global.
    A per-instance asyncio lock prevents duplicate work on one service while
    this small synchronous guard prevents a second service from stealing or
    tearing down the first service's registrations.
    """

    global _CONFIG_SERVICE_OWNER
    with _CONFIG_SERVICE_OWNER_GUARD:
        if _CONFIG_SERVICE_OWNER is None:
            _CONFIG_SERVICE_OWNER = owner_token
            return
        if _CONFIG_SERVICE_OWNER is owner_token:
            return
        raise RuntimeError(
            "another ConfigService instance owns the process-global config hooks"
        )


def _assert_config_service_owner(owner_token: object) -> None:
    with _CONFIG_SERVICE_OWNER_GUARD:
        if _CONFIG_SERVICE_OWNER is not owner_token:
            raise RuntimeError(
                "ConfigService cannot mutate process-global hooks without ownership"
            )


def _release_config_service_owner(owner_token: object) -> None:
    global _CONFIG_SERVICE_OWNER
    with _CONFIG_SERVICE_OWNER_GUARD:
        if _CONFIG_SERVICE_OWNER is not owner_token:
            raise RuntimeError(
                "ConfigService cannot release process-global hooks owned elsewhere"
            )
        _CONFIG_SERVICE_OWNER = None


def _legacy_path_key(path: Path) -> str:
    return os.path.normcase(str(Path(path).resolve(strict=False)))


def _legacy_root_owns_collection(
    root: Any,
    collection: Any,
) -> bool:
    """Return whether a nested collection persists as part of this root.

    A legacy ``MultipleConfig`` can appear in a parent ``ConfigBase`` while
    being connected to a different JSON file.  GameSign accounts are the
    production example: the parent is ``ToolsConfig.json`` but the collection
    is authoritative in ``GameSignAccounts.json``.  Projecting it into both
    Config v2 roots would create two owners and make rollback ambiguous.
    """

    if collection.file is None:
        return True
    if root.file is None:
        return False
    return _legacy_path_key(collection.file) == _legacy_path_key(root.file)


def _snapshot_legacy_config(root: LegacyConfigRoot) -> dict[str, Any]:
    """Return the exact schema-owned ciphertext shape without async I/O."""
    from app.models.ConfigBase import MultipleConfig as LegacyMultipleConfig

    if isinstance(root, LegacyMultipleConfig):
        payload: dict[str, Any] = {
            "instances": [
                {"uid": str(uid), "type": type(root.data[uid]).__name__}
                for uid in root.order
            ]
        }
        for uid in root.order:
            payload[str(uid)] = _snapshot_legacy_config(root.data[uid])
        return payload

    payload = {}
    for group, items in root._config_item_index.items():
        payload[group] = {
            name: item.getValue(if_decrypt=False) for name, item in items.items()
        }

    owned_collections = {
        name: collection
        for name, collection in root._multiple_config_index.items()
        if _legacy_root_owns_collection(root, collection)
    }
    if owned_collections:
        payload["SubConfigsInfo"] = {
            name: _snapshot_legacy_config(collection)
            for name, collection in owned_collections.items()
        }
    return payload


class _SchemaBoundLegacyCodec:
    """Canonicalize one loaded legacy root before the TOML preflight."""

    def __init__(self, root: LegacyConfigRoot) -> None:
        self._root = root

    def encode(self, legacy_data: dict[str, Any]) -> WireDict:
        # Deliberately do not copy unknown input keys into Wire.  Preflight
        # compares this schema snapshot with ``legacy_data`` and refuses a
        # write on any missing, extra, stale, or normalized value.
        del legacy_data
        return _snapshot_legacy_config(self._root)

    def decode(self, wire_data: WireDict) -> dict[str, Any]:
        return copy.deepcopy(wire_data)


class ConfigService:
    """配置服务统一入口。

    根据 AUTO_MAS_CONFIG_V2_MODE 路由：
    - off：完全使用 legacy Config
    - shadow：legacy 为权威源，v2 影子写入
    - canary：v2 可写，legacy 仍为权威
    - authoritative：八个原生生产根作为唯一运行时权威

    legacy Config 对象只能服务于 off/shadow/canary。它们不能作为
    authoritative 的读取 fallback、迁移解析器或保存备份，否则会形成
    同一进程内的混合权威。
    """

    def __init__(self) -> None:
        self._initialized = False
        self._lifecycle_state = "idle"
        self._lifecycle_lock = asyncio.Lock()
        self._owner_token = object()
        self._observer_registered = False
        self._outbox_hooks_registered = False
        self._registered_codec_files: set[str] = set()

    @property
    def mode(self) -> str:
        return CONFIG_V2_MODE

    @property
    def is_v2_active(self) -> bool:
        return CONFIG_V2_MODE != CONFIG_V2_MODE_OFF

    @property
    def uses_legacy_runtime(self) -> bool:
        return CONFIG_V2_MODE != CONFIG_V2_MODE_AUTHORITATIVE

    def assert_startup_mode_ready(self) -> None:
        """Validate the selected process mode before global side effects."""
        assert_config_v2_startup_mode_ready(CONFIG_V2_MODE)

    async def initialize(self) -> None:
        """初始化配置服务。"""
        async with self._lifecycle_lock:
            if self._initialized:
                _assert_config_service_owner(self._owner_token)
                return

            if self._lifecycle_state != "idle":
                raise RuntimeError(
                    f"ConfigService cannot initialize from {self._lifecycle_state}"
                )

            self.assert_startup_mode_ready()
            _claim_config_service_owner(self._owner_token)
            self._lifecycle_state = "initializing"
            logger.info(f"配置服务初始化, mode={CONFIG_V2_MODE}")

            try:
                # Core owns the transport.  Config v2 receives narrow
                # transaction-ID hooks and therefore never imports app.core.
                from app.core.ws.publisher import ws_publisher

                configure_outbox_hooks(
                    enqueue=ws_publisher.enqueue,
                    flush=ws_publisher.flush_outbox,
                    discard=ws_publisher.discard_outbox,
                )
                self._outbox_hooks_registered = True

                if self.is_v2_active and self.uses_legacy_runtime:
                    self._register_legacy_codecs()
                    if CONFIG_V2_MODE == CONFIG_V2_MODE_SHADOW:
                        await self._shadow_migrate_existing()

                if self.uses_legacy_runtime:
                    configure_config_save_observer(self.save_config)
                    self._observer_registered = True
                self._initialized = True
                self._lifecycle_state = "initialized"
            except BaseException:
                try:
                    if self._observer_registered:
                        configure_config_save_observer(None)
                        self._observer_registered = False
                    if self._outbox_hooks_registered:
                        configure_outbox_hooks(
                            enqueue=None,
                            flush=None,
                            discard=None,
                        )
                        self._outbox_hooks_registered = False
                    self._unregister_legacy_codecs()
                finally:
                    self._initialized = False
                    self._lifecycle_state = "idle"
                    _release_config_service_owner(self._owner_token)
                raise

    @staticmethod
    def _legacy_config_roots() -> tuple[LegacyConfigRoot, ...]:
        """Return only roots connected by ``AppConfig.init_config``."""
        from app.core.config import Config

        return (
            Config,
            Config.EmulatorConfig,
            Config.PlanConfig,
            Config.ScriptConfig,
            Config.QueueConfig,
            Config.ToolsConfig,
            Config.PluginConfig,
            Config.ToolsConfig.GameSign_Accounts,
        )

    def _register_legacy_codecs(self) -> None:
        for root in self._legacy_config_roots():
            if root.file is None:
                logger.warning(
                    "legacy v2 codec skipped for an unconnected config root: %s",
                    type(root).__name__,
                )
                continue
            file_name = root.file.name
            legacy_adapter.register_codec(
                file_name,
                _SchemaBoundLegacyCodec(root),
                secrets_protected=True,
            )
            self._registered_codec_files.add(file_name)

    def _unregister_legacy_codecs(self) -> None:
        for file_name in self._registered_codec_files:
            legacy_adapter.unregister_codec(file_name)
        self._registered_codec_files.clear()

    async def _shadow_migrate_existing(self) -> None:
        """shadow 模式下对现有 legacy JSON 做 round-trip。"""
        if CONFIG_V2_MODE != CONFIG_V2_MODE_SHADOW:
            return

        # 查找 legacy 配置文件
        config_dir = Path.cwd() / "config"
        if not config_dir.exists():
            return

        for json_path in config_dir.glob("*.json"):
            try:
                raw = json_path.read_text(encoding="utf-8")
                if not raw.strip():
                    logger.debug(f"跳过空 legacy 配置: {json_path}")
                    continue
                data = json.loads(raw)
                if not isinstance(data, dict):
                    logger.warning(f"跳过非对象 legacy 配置: {json_path}")
                    continue
                legacy_adapter.shadow_write(json_path, data)
            except Exception as exc:
                logger.warning(f"shadow 迁移失败: {json_path}, error: {exc}")

    async def _authoritative_load(self) -> None:
        """Reject the removed legacy-backed authoritative projection."""
        self.assert_startup_mode_ready()
        raise RuntimeError(
            "authoritative configuration is initialized by NativeConfigFacade"
        )

    async def save_config(
        self,
        legacy_path: Path,
        legacy_data: dict[str, Any],
    ) -> None:
        """保存配置。

        - shadow 模式：旧 JSON 为权威源；有安全 codec 时写 shadow TOML
        - canary：有安全 codec 时写 v2 TOML，旧 JSON 仍为权威源
        - authoritative：拒绝 legacy JSON-first 保存
        - off：只写旧 JSON
        """
        self.assert_startup_mode_ready()
        if not self.uses_legacy_runtime:
            raise RuntimeError(
                "authoritative runtime rejects legacy JSON-first saves"
            )
        if self.is_v2_active and not legacy_adapter.is_off:
            try:
                output_path = legacy_adapter.shadow_write(legacy_path, legacy_data)
                if output_path and legacy_adapter.is_authoritative:
                    logger.debug(
                        "authoritative 保存: v2 TOML 已写入 %s"
                        "（legacy JSON 仅作备份）",
                        output_path.name,
                    )
            except Exception as exc:
                # JSON remains authoritative in shadow/canary and has already
                # been durably replaced.  Do not report that primary save as
                # failed merely because its auxiliary evidence write failed.
                logger.error(
                    "legacy v2 auxiliary write failed for %s (%s)",
                    legacy_path.name,
                    type(exc).__name__,
                )

    async def shutdown(self) -> None:
        """关闭配置服务，等待 config flush。"""
        async with self._lifecycle_lock:
            if not self._initialized:
                return

            _assert_config_service_owner(self._owner_token)
            self._lifecycle_state = "shutting_down"
            try:
                await shutdown_runtime()
            finally:
                try:
                    if self._observer_registered:
                        configure_config_save_observer(None)
                        self._observer_registered = False
                    if self._outbox_hooks_registered:
                        configure_outbox_hooks(
                            enqueue=None,
                            flush=None,
                            discard=None,
                        )
                        self._outbox_hooks_registered = False
                    self._unregister_legacy_codecs()
                finally:
                    self._initialized = False
                    self._lifecycle_state = "idle"
                    _release_config_service_owner(self._owner_token)
            logger.info("配置服务已关闭")


# 全局单例
config_service = ConfigService()
