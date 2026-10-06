"""发布元数据解析：同文件分产 ``PluginMeta`` / ``PluginRecord``。

门禁与公共非展示字段由 ``_view`` 解析一次，两对外函数复用；
市场展示 ``*_i18n`` 仅 ``parse_to_plugin_meta`` 填写。
"""

from __future__ import annotations

import json
import re
from email.message import Message
from typing import Any, Literal

import importlib.metadata as importlib_metadata

from app.models.config import PluginMeta, PluginRecord
from app.plugin.types import (
    CORE_PLUGIN_NAME,
    MARKET_GATE_TAG,
    PLUGIN_ID_TAG_PREFIX,
    PluginState,
)

# 描述段 / 固定元信息值文首：<!--{...}-->
_I18N_COMMENT = re.compile(r"^\s*<!--\s*(.*?)\s*-->", re.DOTALL)
_DISPLAY_NAME_URL = "auto-mas-display-name"


def _view(
    meta: Message[Any, Any] | importlib_metadata.PackageMetadata | dict[str, Any],
) -> dict[str, Any] | None:
    """统一中间视图；门禁失败返回 None。供 meta / record 两路复用。"""
    # ── 展平 Name / Version / Summary / Keywords / URLs / Requires-Dist ──
    if isinstance(meta, dict):
        info = meta.get("info") if isinstance(meta.get("info"), dict) else meta
        assert isinstance(info, dict)
        name = str(info.get("name") or "")
        version = str(info.get("version") or "")
        summary = str(info.get("summary") or info.get("description") or "")
        raw_kw = info.get("keywords")
        raw_urls: object = info.get("project_urls") or {}
        raw_requires = info.get("requires_dist") or []
        requires = (
            [str(item) for item in raw_requires if item]
            if isinstance(raw_requires, list)
            else []
        )
    else:
        name = str(meta.get("Name") or "")
        version = str(meta.get("Version") or "")
        summary = str(meta.get("Summary") or "")
        raw_kw = meta.get("Keywords")
        get_all = getattr(meta, "get_all", None)
        raw_urls = (get_all("Project-URL") if callable(get_all) else None) or []
        raw_requires = get_all("Requires-Dist") if callable(get_all) else None
        requires = (
            [str(item) for item in raw_requires if item]
            if isinstance(raw_requires, list)
            else []
        )

    # ── Keywords：可选文首 tags_i18n 注释 + 门禁 token ──
    if isinstance(raw_kw, list):
        kw_text = ", ".join(str(item).strip() for item in raw_kw if str(item).strip())
    else:
        kw_text = str(raw_kw or "").strip()
    tags_i18n: dict[str, list[str]] | None = None
    kw_match = _I18N_COMMENT.match(kw_text)
    if kw_match:
        try:
            parsed_tags = json.loads(kw_match.group(1))
        except (json.JSONDecodeError, TypeError):
            parsed_tags = None
        if isinstance(parsed_tags, dict) and parsed_tags:
            cleaned: dict[str, list[str]] = {}
            for locale, labels in parsed_tags.items():
                if not isinstance(locale, str) or not locale:
                    continue
                if isinstance(labels, list) and all(isinstance(x, str) for x in labels):
                    cleaned[locale] = list(labels)
            if cleaned:
                tags_i18n = cleaned
        kw_text = kw_text[kw_match.end() :].strip()
    if "," in kw_text:
        tokens = [item.strip() for item in kw_text.split(",") if item.strip()]
    else:
        tokens = [item.strip() for item in kw_text.split() if item.strip()]

    # ── 门禁：auto-mas-plugin + 唯一合法 auto-mas-id: ──
    if MARKET_GATE_TAG not in tokens:
        return None
    ids = [
        item[len(PLUGIN_ID_TAG_PREFIX) :]
        for item in tokens
        if item.startswith(PLUGIN_ID_TAG_PREFIX)
    ]
    if len(ids) != 1 or not ids[0] or "/" in ids[0] or " " in ids[0]:
        return None
    plugin_name = ids[0]

    # ── Project-URL → label→url；抽 docs / homepage ──
    urls: dict[str, str] = {}
    if isinstance(raw_urls, dict):
        for label, url in raw_urls.items():
            if label and url:
                urls[str(label).strip()] = str(url).strip()
    else:
        items = (
            [str(item) for item in raw_urls]
            if isinstance(raw_urls, list)
            else ([str(raw_urls)] if raw_urls else [])
        )
        for item in items:
            if "," in item:
                label, url = item.split(",", 1)
                urls[label.strip()] = url.strip()
    docs_url = next(
        (
            str(urls[key])
            for key in ("Documentation", "Docs", "documentation", "docs")
            if urls.get(key)
        ),
        "",
    )
    homepage = next(
        (
            str(urls[key])
            for key in ("Homepage", "Home", "homepage", "home")
            if urls.get(key)
        ),
        "",
    )

    return {
        "package_name": name,
        "plugin_name": plugin_name,
        "version": version,
        "summary": summary,
        "docs_url": docs_url,
        "homepage": homepage,
        "requires_dist": requires,
        "urls": urls,
        "tags_i18n": tags_i18n,
    }


def parse_to_plugin_meta(
    meta: Message[Any, Any] | importlib_metadata.PackageMetadata | dict[str, Any],
) -> PluginMeta | None:
    """索引/METADATA → 未激活 ``PluginMeta``；缺展示 i18n 注解则丢弃。"""
    view = _view(meta)
    if view is None:
        return None

    # 文首 HTML 注释 → locale→文案（描述段与展示名各用一次）
    def maps(raw: str) -> dict[str, str] | None:
        match = _I18N_COMMENT.match(raw or "")
        if not match:
            return None
        try:
            parsed = json.loads(match.group(1))
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(parsed, dict) or not parsed:
            return None
        out: dict[str, str] = {}
        for locale, text in parsed.items():
            if isinstance(locale, str) and locale and isinstance(text, str) and text:
                out[locale] = text
        return out or None

    description_i18n = maps(str(view["summary"]))
    display_name_i18n = maps(str(view["urls"].get(_DISPLAY_NAME_URL) or ""))
    tags_i18n = view["tags_i18n"]
    if not description_i18n or not display_name_i18n or not tags_i18n:
        return None
    return PluginMeta.build(
        info={
            "package_name": view["package_name"],
            "plugin_name": view["plugin_name"],
            "version": view["version"],
            "docs_url": view["docs_url"],
            "homepage": view["homepage"],
            "requires_dist": list(view["requires_dist"]),
            "display_name_i18n": display_name_i18n,
            "description_i18n": description_i18n,
            "tags_i18n": tags_i18n,
        }
    )


def parse_to_plugin_record(
    meta: Message[Any, Any] | importlib_metadata.PackageMetadata | dict[str, Any],
    *,
    import_name: str,
    source: Literal["installed", "local"],
) -> PluginRecord | None:
    """发行版/本地 METADATA → 未激活 ``PluginRecord``（无展示字段）。"""
    view = _view(meta)
    if view is None:
        return None
    plugin_name = str(view["plugin_name"])
    return PluginRecord.build(
        info={
            "plugin_name": plugin_name,
            "package_name": view["package_name"],
            "version": view["version"],
            "docs_url": view["docs_url"],
            "import_name": import_name,
            "source": source,
            "is_local": source == "local",
            "is_core": plugin_name == CORE_PLUGIN_NAME,
            "enabled": plugin_name == CORE_PLUGIN_NAME,
            "state": PluginState.UNLOADED,
        }
    )


__all__ = ["parse_to_plugin_meta", "parse_to_plugin_record"]
