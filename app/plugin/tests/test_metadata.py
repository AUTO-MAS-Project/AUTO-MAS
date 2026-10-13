"""发布元数据双解析与市场 ``*_i18n`` Virtual。"""

from __future__ import annotations

import asyncio
from email.message import Message

import pytest

import app.core.config as core_config
from app.models.config import PluginMeta, Setting
from app.plugin.runtime.metadata import parse_to_plugin_meta, parse_to_plugin_record


def _market_message(
    *,
    summary: str,
    keywords: str,
    display_url: str,
) -> Message:
    msg = Message()
    msg["Name"] = "automas-plugin-demo"
    msg["Version"] = "1.2.3"
    msg["Summary"] = summary
    msg["Keywords"] = keywords
    msg.add_header("Project-URL", "Documentation, https://doc.example.com/demo")
    msg.add_header("Project-URL", f"auto-mas-display-name, {display_url}")
    msg.add_header("Project-URL", "Homepage, https://example.com")
    msg["Requires-Dist"] = "httpx>=0.27"
    return msg


async def _noop(*args: object, **kwargs: object) -> None:
    """替掉带系统副作用的服务方法。"""


def test_parse_meta_ok_and_virtual_locale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        # Setting 激活会热化 if_self_start / if_allow_sleep 两个订阅，
        # 它们直连 schtasks 与电源 API：本用例只关心 i18n Virtual，把系统副作用挡掉
        from app.services import System

        monkeypatch.setattr(System, "set_SelfStart", _noop)
        monkeypatch.setattr(System, "set_Sleep", _noop)

        setting = Setting()
        await setting.activate()
        setting.language.locale = "zh_CN"
        monkeypatch.setattr(core_config.Config, "setting", setting)

        summary = '<!--{"zh_CN":"中文说明","en":"English blurb"}-->'
        keywords = (
            '<!--{"zh_CN":["自动化"],"en":["automation"]}-->'
            " auto-mas-plugin, auto-mas-id:demo, maa"
        )
        display = '<!--{"zh_CN":"演示插件","en":"Demo Plugin"}-->'
        draft = parse_to_plugin_meta(
            _market_message(
                summary=summary, keywords=keywords, display_url=display
            )
        )
        assert draft is not None
        assert draft.info.plugin_name == "demo"
        assert draft.info.homepage == "https://example.com"
        assert draft.info.requires_dist == ["httpx>=0.27"]
        assert draft.info.display_name_i18n["zh_CN"] == "演示插件"
        assert draft.info.description_i18n["en"] == "English blurb"
        assert draft.info.tags_i18n["en"] == ["automation"]

        live = PluginMeta.build(info=draft.info.model_dump(mode="python"))
        await live.activate()
        assert live.info.display_name == "演示插件"
        assert live.info.description == "中文说明"
        assert live.info.tags == ["自动化"]

        setting.language.locale = "en"
        await setting.commit()
        assert live.info.display_name == "Demo Plugin"
        assert live.info.description == "English blurb"
        assert live.info.tags == ["automation"]

    asyncio.run(run())


def test_parse_meta_rejects_missing_i18n() -> None:
    msg = Message()
    msg["Name"] = "automas-plugin-demo"
    msg["Version"] = "1.0.0"
    msg["Summary"] = "plain summary"
    msg["Keywords"] = "auto-mas-plugin, auto-mas-id:demo"
    assert parse_to_plugin_meta(msg) is None


def test_parse_record_skips_display_i18n() -> None:
    msg = Message()
    msg["Name"] = "automas-plugin-demo"
    msg["Version"] = "1.0.0"
    msg["Summary"] = "plain"
    msg["Keywords"] = "auto-mas-plugin, auto-mas-id:demo"
    draft = parse_to_plugin_record(msg, import_name="demo_pkg", source="local")
    assert draft is not None
    assert draft.info.plugin_name == "demo"
    assert "description" not in type(draft.info).model_fields
    assert "tags" not in type(draft.info).model_fields
    assert "display_name" not in type(draft.info).model_fields


def test_parse_pypi_json_info() -> None:
    payload = {
        "info": {
            "name": "automas-plugin-demo",
            "version": "9.0.0",
            "summary": '<!--{"zh_CN":"摘要","en":"Summary"}-->',
            "keywords": (
                '<!--{"zh_CN":["标签"],"en":["tag"]}-->'
                "auto-mas-plugin,auto-mas-id:demo"
            ),
            "project_urls": {
                "Documentation": "https://doc.example.com",
                "auto-mas-display-name": '<!--{"zh_CN":"名","en":"Name"}-->',
            },
            "requires_dist": ["foo"],
        }
    }
    meta = parse_to_plugin_meta(payload)
    assert meta is not None
    assert meta.info.version == "9.0.0"
    assert meta.info.display_name_i18n["en"] == "Name"
    record = parse_to_plugin_record(payload, import_name="x", source="installed")
    assert record is not None
    assert record.info.docs_url == "https://doc.example.com"
