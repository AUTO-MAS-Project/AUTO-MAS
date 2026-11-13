"""发布元数据解析：同文件分产 ``PluginMeta`` / ``PluginRecord``。

身份门禁和 README 多语言声明由 ``_view`` 解析一次，市场与发现入口共用。
"""

from __future__ import annotations

import importlib.metadata as importlib_metadata
import json
import re
from email.message import Message
from typing import Any, Literal, TypedDict

from app.models.config import PluginMeta, PluginRecord
from app.plugin.types import (
    CORE_PLUGIN_NAME,
    MARKET_GATE_TAG,
    PLUGIN_ID_TAG_PREFIX,
    PluginState,
)

# README 开头的专用声明同时进入 PyPI 描述和发行包 METADATA 正文。
_I18N_COMMENT = re.compile(r"^\s*<!--\s*auto-mas:i18n\s+(.*?)\s*-->", re.DOTALL)


class _DisplayMetadata(TypedDict):
    display_name_i18n: dict[str, str]
    description_i18n: dict[str, str]
    tags_i18n: dict[str, list[str]]


def _read_readme_i18n(readme: str) -> _DisplayMetadata | None:
    """解析 README 专用注释中的三类语言映射，缺失或格式无效时不生成市场声明。"""
    match = _I18N_COMMENT.match(readme)
    if match is None:
        return None
    try:
        declaration = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    if not isinstance(declaration, dict):
        return None

    def text_map(field: str) -> dict[str, str]:
        """读取名称或简介的语言映射，过滤空语言键及非文本条目。"""
        values = declaration.get(field)
        if not isinstance(values, dict):
            return {}
        return {
            locale: value
            for locale, value in values.items()
            if isinstance(locale, str) and locale and isinstance(value, str) and value
        }

    display_name = text_map("display_name_i18n")
    description = text_map("description_i18n")
    raw_tags = declaration.get("tags_i18n")
    if not display_name or not description or not isinstance(raw_tags, dict):
        return None
    tags = {
        locale: list(values)
        for locale, values in raw_tags.items()
        if isinstance(locale, str)
        and locale
        and isinstance(values, list)
        and all(isinstance(value, str) for value in values)
    }
    if not tags:
        return None
    return {
        "display_name_i18n": display_name,
        "description_i18n": description,
        "tags_i18n": tags,
    }


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
        summary = str(info.get("summary") or "")
        readme = str(info.get("description") or "")
        author = str(info.get("author") or info.get("author_email") or "")
        license_text = str(info.get("license_expression") or info.get("license") or "")
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
        description = meta.get("Description")
        if not description and isinstance(meta, Message):
            description = meta.get_payload()
        readme = description if isinstance(description, str) else ""
        author = str(meta.get("Author") or meta.get("Author-email") or "")
        license_text = str(meta.get("License-Expression") or meta.get("License") or "")
        raw_kw = meta.get("Keywords")
        get_all = getattr(meta, "get_all", None)
        raw_urls = (get_all("Project-URL") if callable(get_all) else None) or []
        raw_requires = get_all("Requires-Dist") if callable(get_all) else None
        requires = (
            [str(item) for item in raw_requires if item]
            if isinstance(raw_requires, list)
            else []
        )

    # Keywords 只承载普通关键词与插件身份门禁，不再编码语言映射。
    if isinstance(raw_kw, list):
        kw_text = ", ".join(str(item).strip() for item in raw_kw if str(item).strip())
    else:
        kw_text = str(raw_kw or "").strip()
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
        "display_metadata": _read_readme_i18n(readme),
        "author": author,
        "license": license_text,
    }


def parse_to_plugin_meta(
    meta: Message[Any, Any] | importlib_metadata.PackageMetadata | dict[str, Any],
) -> PluginMeta | None:
    """索引/METADATA → 未激活 ``PluginMeta``；缺展示 i18n 注解则丢弃。"""
    view = _view(meta)
    if view is None:
        return None

    display = view["display_metadata"]
    if display is None:
        return None
    return PluginMeta.build(
        info={
            "package_name": view["package_name"],
            "plugin_name": view["plugin_name"],
            "version": view["version"],
            "docs_url": view["docs_url"],
            "homepage": view["homepage"],
            "requires_dist": list(view["requires_dist"]),
            **display,
        }
    )


def _record_display_metadata(view: dict[str, Any]) -> _DisplayMetadata:
    """本地与安装记录复用 README 声明，缺失时按标准简介和插件身份展示。"""
    display = view["display_metadata"]
    if display is not None:
        return display
    return {
        "display_name_i18n": {"en": str(view["plugin_name"])},
        "description_i18n": {"en": str(view["summary"])},
        "tags_i18n": {},
    }


def parse_to_plugin_record(
    meta: Message[Any, Any] | importlib_metadata.PackageMetadata | dict[str, Any],
    *,
    import_name: str,
    source: Literal["installed", "local"],
) -> PluginRecord | None:
    """发行版/本地 METADATA → 未激活记录，并保留可用的 README 展示声明。"""
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
            "homepage": view["homepage"],
            "repository": next(
                (
                    url
                    for key, url in view["urls"].items()
                    if key.lower() in {"repository", "source", "source code"}
                ),
                "",
            ),
            "author": view["author"],
            "license": view["license"],
            "requires_dist": view["requires_dist"],
            **_record_display_metadata(view),
            "source": source,
            "is_local": source == "local",
            "is_core": plugin_name == CORE_PLUGIN_NAME,
            "enabled": plugin_name == CORE_PLUGIN_NAME,
            "state": PluginState.UNLOADED,
        }
    )


__all__ = ["parse_to_plugin_meta", "parse_to_plugin_record"]
