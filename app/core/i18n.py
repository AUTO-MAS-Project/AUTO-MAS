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
    signatures: tuple[tuple[int, int], ...]


class I18nManager:
    """缓存只读资源快照；读盘失败保留旧快照，但向本次请求报告失败。"""

    def __init__(self, directory: Path) -> None:
        # TODO(插件迁移)：由插件生命周期提供目录或包资源来源，替代单目录输入；
        # 本服务只汇总资源，不承担插件发现，也不依赖具体插件注册表。
        self._directory = directory
        self._snapshot: I18nSnapshot | None = None
        self._lock = asyncio.Lock()

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

        # TODO(插件迁移)：安装、启停、升级、卸载也须使快照失效；
        # 完成一致快照后复用此通知，不能只等待主程序资源文件变化。
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
        # TODO(插件迁移)：缓存签名与 revision 须包含启用的资源来源身份及内容，
        # 覆盖插件增删与包资源变化，不能仅比较本目录文件的时间和大小。
        paths = [self._directory / name for name in LOCALE_FILES.values()]
        stats = [path.stat() for path in paths]
        signatures = tuple((stat.st_mtime_ns, stat.st_size) for stat in stats)
        if previous is not None and previous.signatures == signatures:
            return previous

        catalogs: dict[AppLocale, dict[str, JsonValue]] = {}
        digest = hashlib.sha256()
        for (locale, filename), path in zip(LOCALE_FILES.items(), paths, strict=True):
            raw = path.read_bytes()
            digest.update(filename.encode())
            digest.update(b"\0")
            digest.update(raw)
            digest.update(b"\0")
            catalogs[locale] = self._parse_catalog(raw, filename=filename)

        # 编辑期间跨文件读取不能形成看似有效的混合快照，下次请求可以重试。
        final_stats = [path.stat() for path in paths]
        if signatures != tuple(
            (stat.st_mtime_ns, stat.st_size) for stat in final_stats
        ):
            raise ValueError("语言资源正在更新，请重试")
        return I18nSnapshot(
            revision=digest.hexdigest(), catalogs=catalogs, signatures=signatures
        )

    @staticmethod
    def _parse_catalog(raw: bytes, *, filename: str) -> dict[str, JsonValue]:
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
            # TODO(插件迁移)：按来源校验 core.* 或 plugins.<插件标识>.*，
            # 禁止跨插件写入及覆盖 core/bootstrap；同步调整前端命名空间校验。
            if not key.startswith("core.") or not isinstance(value, str):
                raise ValueError(f"语言资源必须使用 core.* 字符串词条：{filename}")
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
