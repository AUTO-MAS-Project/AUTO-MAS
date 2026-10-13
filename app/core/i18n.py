"""全局 i18n 资源服务：读取主程序与插件包内的 monolingual JSON。"""

from __future__ import annotations

import asyncio
import importlib.resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

from app.core.config import Config
from app.utils import get_logger
from app.utils.io import read_file

logger = get_logger("国际化服务")


class I18nManager:
    """按需解析全局 i18n 资源，并提供 Vue I18n messages。"""

    FALLBACK_LOCALE = "en"

    def __init__(self) -> None:
        self._initialized = False
        self._revision = 0
        self._dirty = True
        self._catalogs: dict[str, dict[str, str]] = {}
        self._messages: dict[tuple[int, str], dict[str, Any]] = {}
        self._locales: tuple[str, ...] = ()
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """初始化全局服务；资源读取延迟到首次端口访问。"""
        if self._initialized:
            return

        # 配置信号按弱引用在接收者上挂属性，绑定方法挂不上；改挂函数并存到实例上保活
        async def on_change(*_: object) -> None:
            await self.invalidate()

        self._on_change = on_change
        Config.plugin_registry.connect(on_change, phase="runtime")
        Config.setting.connect(
            on_change, phase="runtime", group="language", field="locale"
        )
        self._initialized = True

    async def invalidate(self, *_: object) -> None:
        """标记资源缓存失效并发布一次统一变更通知。"""
        self._dirty = True
        self._revision += 1
        self._messages.clear()
        if not self._initialized:
            return
        try:
            from app.core.ws import Publisher, protocol

            await Publisher.send(
                id=protocol.ID_I18N,
                type=protocol.I18N_UPDATED,
                data={"revision": str(self._revision)},
            )
        except Exception as exc:
            logger.debug(f"i18n 变更消息发送失败: {exc}")

    async def get_messages(self, locale: str | None = None) -> dict[str, Any]:
        """返回指定语言的 Vue I18n 嵌套 messages。"""
        async with self._lock:
            await self._load()
            selected = locale or Config.setting.language.locale

            # 生成缓存 key 并尝试从缓存中获取
            cache_key = (self._revision, selected)
            cached = self._messages.get(cache_key)
            if cached is not None:
                return cached

            # 生成展平的 key-value 字典，优先使用当前语言，其次使用回退语言
            flat: dict[str, str] = {}
            keys = {key for catalog in self._catalogs.values() for key in catalog}
            selected_catalog = self._catalogs.get(selected, {})
            fallback_catalog = self._catalogs.get(self.FALLBACK_LOCALE, {})
            for key in sorted(keys):
                if key in selected_catalog:
                    flat[key] = selected_catalog[key]
                elif key in fallback_catalog:
                    flat[key] = fallback_catalog[key]
                else:
                    flat[key] = key

            # 生成嵌套的 messages 字典
            messages: dict[str, Any] = {}
            for key, value in flat.items():
                node = messages
                parts = key.split(".")
                for part in parts[:-1]:
                    current = node.get(part)
                    if current is None:
                        current = {}
                        node[part] = current
                    if not isinstance(current, dict):
                        logger.warning(f"i18n key 结构冲突，跳过: {key}")
                        node = {}
                        break
                    node = current
                else:
                    leaf = parts[-1]
                    if leaf not in node or isinstance(node.get(leaf), str):
                        node[leaf] = value

            # 缓存生成的 messages 并返回
            self._messages[cache_key] = messages
            return messages

    async def get_locales(self) -> dict[str, Any]:
        """返回当前语言、回退语言、可用语言和 revision。"""
        async with self._lock:
            await self._load()
            return {
                "current": Config.setting.language.locale,
                "fallback": self.FALLBACK_LOCALE,
                "available": list(self._locales),
                "revision": str(self._revision),
            }

    async def set_locale(self, locale: str) -> dict[str, Any]:
        """持久化当前语言并返回最新语言状态。"""
        async with self._lock:
            await self._load()
            if locale not in self._locales:
                raise ValueError(f"不支持的 locale: {locale}")
            if Config.setting.language.locale != locale:
                Config.setting.language.locale = locale
                await Config.setting.commit()
            return {
                "current": Config.setting.language.locale,
                "fallback": self.FALLBACK_LOCALE,
                "available": list(self._locales),
                "revision": str(self._revision),
            }

    async def _load(self) -> None:
        if not self._dirty:
            return

        catalogs: dict[str, dict[str, str]] = {}
        locale_names: set[str] = set()
        for path in sorted(Config.i18n_path.glob("*.json")):
            locale = path.stem
            catalog = self._read(path, prefix="core.")
            catalogs.setdefault(locale, {}).update(catalog)
            locale_names.add(locale)

        for record in sorted(
            Config.plugin_registry.values(),
            key=lambda item: item.info.plugin_name or "",
        ):
            plugin_name = record.info.plugin_name
            if not plugin_name:
                continue
            resource_dir: Path | Traversable | None = None
            if record._project_dir is not None and record.info.import_name:
                resource_dir = record._project_dir / record.info.import_name / "i18n"
            elif record.info.import_name:
                try:
                    resource_dir = (
                        importlib.resources.files(record.info.import_name) / "i18n"
                    )
                except Exception as exc:
                    logger.debug(f"插件 i18n 包资源不可用: {plugin_name}: {exc}")
            if resource_dir is None:
                continue
            try:
                paths = sorted(
                    (
                        item
                        for item in resource_dir.iterdir()
                        if item.name.endswith(".json")
                    ),
                    key=lambda item: item.name,
                )
            except Exception as exc:
                logger.debug(f"插件 i18n 目录不可读: {plugin_name}: {exc}")
                continue
            for resource_path in paths:
                locale = resource_path.name[:-5]
                catalog = self._read(resource_path, prefix=f"plugins.{plugin_name}.")
                catalogs.setdefault(locale, {}).update(catalog)
                locale_names.add(locale)

        self._catalogs = catalogs
        self._locales = tuple(sorted(locale_names | {self.FALLBACK_LOCALE}))
        self._dirty = False

    @staticmethod
    def _read(path: Any, *, prefix: str) -> dict[str, str]:
        try:
            raw = read_file(path, format=".json")
        except Exception as exc:
            logger.warning(f"i18n 文件读取失败，跳过 {path}: {exc}")
            return {}
        if not isinstance(raw, dict):
            logger.warning(f"i18n 文件必须是对象，跳过: {path}")
            return {}
        result: dict[str, str] = {}
        for key, value in raw.items():
            if not isinstance(key, str) or not key.startswith(prefix):
                logger.warning(f"i18n key 前缀非法，跳过: {path}: {key}")
                continue
            if not isinstance(value, str):
                logger.warning(f"i18n value 必须是字符串，跳过: {path}: {key}")
                continue
            result[key] = value
        return result


i18n = I18nManager()

__all__ = ["I18nManager", "i18n"]
