"""市场 refresh：写 Config.plugin_catalog，不装包。"""

from __future__ import annotations

import asyncio
from typing import Any, ClassVar
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.core.config as core_config
from app.config import ConfigCollection
from app.models.config import PluginMeta
from app.plugin.runtime import market as plugin_market
from app.plugin.runtime.metadata import parse_to_plugin_meta


class Catalog(ConfigCollection[PluginMeta]):
    _default_entry_types: ClassVar[tuple[type, ...]] = ()


async def _catalog() -> Catalog:
    col = Catalog()
    await col.activate()
    col.add_type(PluginMeta)
    await col.commit()
    return col


def _meta_payload(name: str = "automas-plugin-demo") -> dict[str, Any]:
    return {
        "info": {
            "name": name,
            "version": "1.0.0",
            "summary": '<!--{"zh_CN":"描述","en":"desc"}-->',
            "keywords": (
                '<!--{"zh_CN":["标签"],"en":["tag"]}-->'
                "auto-mas-plugin,auto-mas-id:demo"
            ),
            "project_urls": {
                "auto-mas-display-name": '<!--{"zh_CN":"演示","en":"Demo"}-->',
                "Documentation": "https://doc.example.com",
            },
            "requires_dist": [],
        }
    }


def _client_ok(package: str = "automas-plugin-demo") -> MagicMock:
    """Simple 流式一行 + JSON get 成功。"""
    stream_cm = MagicMock()
    stream_cm.__aenter__ = AsyncMock(
        return_value=MagicMock(
            raise_for_status=MagicMock(),
            aiter_lines=MagicMock(
                return_value=_async_iter(
                    [f'<a href="/simple/{package}/">{package}</a>']
                )
            ),
        )
    )
    stream_cm.__aexit__ = AsyncMock(return_value=None)

    resp = MagicMock()
    resp.status_code = 200
    resp.json = MagicMock(return_value=_meta_payload(package))

    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.stream = MagicMock(return_value=stream_cm)
    client.get = AsyncMock(return_value=resp)
    return client


def _client_empty() -> MagicMock:
    stream_cm = MagicMock()
    stream_cm.__aenter__ = AsyncMock(
        return_value=MagicMock(
            raise_for_status=MagicMock(),
            aiter_lines=MagicMock(return_value=_async_iter([])),
        )
    )
    stream_cm.__aexit__ = AsyncMock(return_value=None)
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.stream = MagicMock(return_value=stream_cm)
    client.get = AsyncMock(
        return_value=MagicMock(status_code=404, json=MagicMock(return_value={}))
    )
    return client


async def _async_iter(items: list[str]):
    for item in items:
        yield item


def test_refresh_writes_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        catalog = await _catalog()
        monkeypatch.setattr(core_config.Config, "plugin_catalog", catalog)
        monkeypatch.setattr(
            core_config.Config,
            "plugin_registry",
            type("R", (), {"values": staticmethod(lambda: [])})(),
        )

        with (
            patch.object(
                plugin_market,
                "candidates",
                return_value=["https://pypi.org/simple/"],
            ),
            patch.object(plugin_market, "mark_ok", new=AsyncMock()),
            patch.object(plugin_market.httpx, "AsyncClient", return_value=_client_ok()),
        ):
            await plugin_market.refresh()

        assert len(list(catalog.values())) == 1
        live = next(iter(catalog.values()))
        assert live.info.plugin_name == "demo"
        assert live.info.description_i18n["zh_CN"] == "描述"
        old_uid = live.uid

        # 再刷一次同包：删光再 add，uid 可变，HIDE 的 *_i18n 仍须落盘
        with (
            patch.object(
                plugin_market,
                "candidates",
                return_value=["https://pypi.org/simple/"],
            ),
            patch.object(plugin_market, "mark_ok", new=AsyncMock()),
            patch.object(plugin_market.httpx, "AsyncClient", return_value=_client_ok()),
        ):
            await plugin_market.refresh()
        assert len(list(catalog.values())) == 1
        again = next(iter(catalog.values()))
        assert again.info.description_i18n["zh_CN"] == "描述"
        assert again.uid != old_uid

        with (
            patch.object(
                plugin_market,
                "candidates",
                return_value=["https://pypi.org/simple/"],
            ),
            patch.object(plugin_market, "mark_ok", new=AsyncMock()),
            patch.object(
                plugin_market.httpx, "AsyncClient", return_value=_client_empty()
            ),
        ):
            await plugin_market.refresh()
        assert list(catalog.values()) == []

    asyncio.run(run())


def test_refresh_skips_package_without_i18n(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        catalog = await _catalog()
        monkeypatch.setattr(core_config.Config, "plugin_catalog", catalog)
        monkeypatch.setattr(
            core_config.Config,
            "plugin_registry",
            type("R", (), {"values": staticmethod(lambda: [])})(),
        )

        bad = {
            "info": {
                "name": "automas-plugin-demo",
                "version": "1.0.0",
                "summary": "no comment",
                "keywords": "auto-mas-plugin,auto-mas-id:demo",
                "project_urls": {},
            }
        }
        assert parse_to_plugin_meta(bad) is None

        client = _client_ok()
        client.get = AsyncMock(
            return_value=MagicMock(status_code=200, json=MagicMock(return_value=bad))
        )

        with (
            patch.object(
                plugin_market,
                "candidates",
                return_value=["https://pypi.org/simple/"],
            ),
            patch.object(plugin_market, "mark_ok", new=AsyncMock()),
            patch.object(plugin_market.httpx, "AsyncClient", return_value=client),
        ):
            await plugin_market.refresh()
        assert list(catalog.values()) == []

    asyncio.run(run())
