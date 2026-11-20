"""按需提供 Weblate 单语 JSON，前端通过 Vue I18n 执行翻译与回退。"""

from __future__ import annotations

import asyncio
import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import JsonValue

from app.core import Config
from app.utils import get_logger

logger = get_logger("国际化资源")

type AppLocale = Literal["zh-CN", "en-US", "ja-JP"]

LOCALE_FILES: dict[AppLocale, str] = {
    "zh-CN": "zh_CN.json",
    "en-US": "en.json",
    "ja-JP": "ja.json",
}
_RESERVED_KEYS = frozenset({"__proto__", "prototype", "constructor"})


@dataclass(frozen=True)
class I18nSnapshot:
    """同一批资源的语言目录、消息与内容版本。"""

    revision: str
    catalogs: dict[AppLocale, dict[str, JsonValue]]
    signatures: tuple[tuple[str, int, int], ...]


class I18nManager:
    """缓存只读资源快照；读盘失败保留旧快照，但向本次请求报告失败。"""

    def __init__(self, directory: Path) -> None:
        """绑定 core 语言资源目录，初始化插件资源登记、快照缓存及刷新锁。"""
        self._directory = directory
        self._plugin_sources: dict[str, Path] = {}
        self._snapshot: I18nSnapshot | None = None
        self._lock = asyncio.Lock()

    def set_plugin_sources(self, sources: dict[str, Path]) -> None:
        """生命周期提供可读资源目录；禁用保留，卸载/来源消失时移除。"""
        self._plugin_sources = dict(sources)

    async def get_locales(self) -> tuple[list[AppLocale], str]:
        snapshot = await self._get_snapshot()
        return list(snapshot.catalogs), snapshot.revision

    async def get_messages(self, locale: AppLocale) -> tuple[dict[str, JsonValue], str]:
        snapshot = await self._get_snapshot()
        # API 调用者不能修改共享缓存；缺词和空译文均原样交给 Vue I18n。
        return deepcopy(snapshot.catalogs[locale]), snapshot.revision

    async def _get_snapshot(self) -> I18nSnapshot:
        async with self._lock:
            previous = self._snapshot
            snapshot = await asyncio.to_thread(self._read_snapshot, previous)
            self._snapshot = snapshot
            changed = previous is not None and previous.revision != snapshot.revision

        if changed:
            from app.core import Publisher
            from app.core.ws import protocol

            try:
                await Publisher.send(
                    id=protocol.ID_I18N,
                    type=protocol.I18N_UPDATED,
                    data={"revision": snapshot.revision},
                )
            except Exception as error:
                # 断开的客户端会在重连时主动刷新，通知失败不影响 HTTP 资源读取。
                logger.debug(f"语言资源变更通知发送失败：{error}")
        return snapshot

    def _read_snapshot(self, previous: I18nSnapshot | None) -> I18nSnapshot:
        """读取并合并 core 与已登记插件的语言文件，复用未变化资源并生成带内容修订号的新快照。"""
        files: list[tuple[AppLocale, str, Path]] = [
            (locale, "core", self._directory / filename)
            for locale, filename in LOCALE_FILES.items()
        ]
        sources = dict(self._plugin_sources)
        aliases = {
            "zh-CN": ("zh-CN.json", "zh_CN.json"),
            "en-US": ("en-US.json", "en.json"),
            "ja-JP": ("ja-JP.json", "ja.json"),
        }
        for name, directory in sorted(sources.items()):
            for locale, names in aliases.items():
                path = next(
                    (
                        directory / filename
                        for filename in names
                        if (directory / filename).is_file()
                    ),
                    None,
                )
                if path is not None:
                    files.append((locale, f"plugins.{name}", path))
        paths = [path for _, _, path in files]
        stats = [path.stat() for path in paths]
        source_signatures = tuple(
            (f"{name}:{directory}", 0, 0) for name, directory in sorted(sources.items())
        )
        signatures = source_signatures + tuple(
            (str(path), stat.st_mtime_ns, stat.st_size)
            for path, stat in zip(paths, stats, strict=True)
        )
        if previous is not None and previous.signatures == signatures:
            return previous

        catalogs: dict[AppLocale, dict[str, JsonValue]] = {}
        digest = hashlib.sha256()
        digest.update(repr(source_signatures).encode())
        for locale, prefix, path in files:
            raw = path.read_bytes()
            digest.update(f"{locale}:{prefix}:{path}".encode())
            digest.update(b"\0")
            digest.update(raw)
            digest.update(b"\0")
            messages = self._parse_catalog(raw, filename=str(path), prefix=prefix)
            catalog = catalogs.setdefault(locale, {})
            if prefix == "core":
                catalog.update(messages)
            else:
                plugins = catalog.setdefault("plugins", {})
                assert isinstance(plugins, dict)
                plugins.update(messages["plugins"])

        # 编辑期间跨文件读取不能形成看似有效的混合快照，下次请求可以重试。
        final_stats = [path.stat() for path in paths]
        if (
            signatures
            != source_signatures
            + tuple(
                (str(path), stat.st_mtime_ns, stat.st_size)
                for path, stat in zip(paths, final_stats, strict=True)
            )
            or sources != self._plugin_sources
        ):
            raise ValueError("语言资源正在更新，请重试")
        return I18nSnapshot(
            revision=digest.hexdigest(), catalogs=catalogs, signatures=signatures
        )

    @staticmethod
    def _parse_catalog(
        raw: bytes, *, filename: str, prefix: str = "core"
    ) -> dict[str, JsonValue]:
        """解析语言文件并为键添加来源命名空间，将扁平键展开为消息树，拒绝重复键与结构冲突。"""

        def unique_object(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
            result: dict[str, JsonValue] = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError(f"语言资源包含重复 key：{filename}: {key}")
                result[key] = value
            return result

        flat = json.loads(raw, object_pairs_hook=unique_object)
        if not isinstance(flat, dict) or not flat:
            raise ValueError(f"语言资源必须是非空对象：{filename}")
        messages: dict[str, JsonValue] = {}
        for key, value in flat.items():
            if not key.startswith(f"{prefix}.") or not isinstance(value, str):
                raise ValueError(f"语言资源必须使用 {prefix}.* 字符串词条：{filename}")
            parts = key.split(".")
            if any(not part or part in _RESERVED_KEYS for part in parts):
                raise ValueError(f"语言资源 key 无效：{filename}: {key}")
            node = messages
            for part in parts[:-1]:
                child = node.setdefault(part, {})
                if not isinstance(child, dict):
                    raise ValueError(f"语言资源 key 结构冲突：{filename}: {key}")
                node = child
            if parts[-1] in node:
                raise ValueError(f"语言资源 key 结构冲突：{filename}: {key}")
            node[parts[-1]] = value
        return messages


I18n = I18nManager(Config.resource_path / "i18n")

__all__ = ["I18n"]
