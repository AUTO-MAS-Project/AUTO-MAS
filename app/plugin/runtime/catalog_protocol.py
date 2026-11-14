"""插件目录 v1 线协议；宿主与生成器通过相同样例校验契约。"""

import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path

MAX_BYTES = 8 * 1024 * 1024
TEXT_FIELDS = (
    "package_name",
    "plugin_name",
    "version",
    "docs_url",
    "homepage",
    "repository",
    "author",
    "license",
)
ENTRY_FIELDS = {
    *TEXT_FIELDS,
    "requires_dist",
    "display_name_i18n",
    "description_i18n",
    "tags_i18n",
}


def package_key(name: str) -> str:
    """按 Python 发行包名称规则统一大小写和连续分隔符。"""
    return re.sub(r"[-_.]+", "-", name).lower()


def canonical_bytes(value: object) -> bytes:
    """以稳定键序和 UTF-8 编码输出 JSON，避免格式变化产生新的目录版本。"""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def validate_entries(raw: object) -> list[dict]:
    """校验完整展示元信息及身份唯一性，拒绝配置触发器或其他非目录字段。"""
    if not isinstance(raw, list):
        raise ValueError("plugins must be a list")
    packages, identities = set(), set()
    entries = []
    for item in raw:
        if not isinstance(item, dict) or set(item) != ENTRY_FIELDS:
            raise ValueError("plugin fields do not match catalog v1")
        if any(not isinstance(item[field], str) for field in TEXT_FIELDS):
            raise ValueError("plugin text fields must be strings")
        package, identity = item["package_name"], item["plugin_name"]
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?", package):
            raise ValueError("invalid package name")
        if not identity or "/" in identity or any(char.isspace() for char in identity):
            raise ValueError("invalid plugin identity")
        if identity == "auto_mas_core" or not item["version"].strip():
            raise ValueError("core is not a market plugin; version must be nonempty")
        if package_key(package) in packages or identity in identities:
            raise ValueError("duplicate package or plugin identity")
        packages.add(package_key(package))
        identities.add(identity)
        requirements = item["requires_dist"]
        if not isinstance(requirements, list) or not all(
            isinstance(v, str) for v in requirements
        ):
            raise ValueError("requires_dist must be a list of strings")
        for field in ("display_name_i18n", "description_i18n", "tags_i18n"):
            values = item[field]
            if not isinstance(values, dict) or not values:
                raise ValueError(f"{field} must be a nonempty language map")
            for locale, value in values.items():
                if not isinstance(locale, str) or not locale:
                    raise ValueError("locale must be nonempty")
                if field == "tags_i18n":
                    if not isinstance(value, list) or not all(
                        isinstance(v, str) for v in value
                    ):
                        raise ValueError("tags must be lists of strings")
                elif not isinstance(value, str) or not value:
                    raise ValueError("translated text must be nonempty")
        entries.append(deepcopy(item))
    return sorted(entries, key=lambda item: package_key(item["package_name"]))


def content_revision(entries: list[dict]) -> str:
    """只计算协议版本和插件业务内容的摘要，不将轮询时间作为变更。"""
    return hashlib.sha256(
        canonical_bytes({"schema_version": 1, "plugins": entries})
    ).hexdigest()


def validate_catalog(raw: object) -> dict:
    """校验目录结构、内容摘要和带时区时间；不以发布时间判定目录过期。"""
    if not isinstance(raw, dict) or set(raw) != {
        "schema_version",
        "revision",
        "updated_at",
        "plugins",
    }:
        raise ValueError("invalid catalog envelope")
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        raise ValueError("unsupported catalog schema version")
    if not isinstance(raw["updated_at"], str):
        raise ValueError("updated_at must be a timestamp")
    stamp = datetime.fromisoformat(raw["updated_at"])
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("updated_at must include a timezone")
    entries = validate_entries(raw["plugins"])
    if raw["revision"] != content_revision(entries):
        raise ValueError("catalog revision does not match content")
    return {**raw, "plugins": entries}


def write_document(path: Path, document: dict) -> None:
    """在同目录写入临时文件后原子替换，保留失败前已可用的 JSON 文件。"""
    import os
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical_bytes(document) + b"\n")
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)
