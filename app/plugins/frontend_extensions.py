from __future__ import annotations

import json
from importlib import resources
from pathlib import PurePosixPath
from typing import Any, Literal
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.page_registry import PageDeclaration, page_registry
from app.utils import get_logger


logger = get_logger("插件前端扩展")

PluginFrontendRenderer = Literal["custom-element"]


def _normalize_asset_path(raw: Any) -> str:
    text = str(raw or "").strip().replace("\\", "/")
    if not text:
        raise ValueError("资源路径不能为空")
    if text.startswith("/"):
        text = text.lstrip("/")
    path = PurePosixPath(text)
    parts = list(path.parts)
    if not parts:
        raise ValueError("资源路径不能为空")
    if parts[0] != "frontend":
        raise ValueError("插件前端资源必须位于 frontend/ 目录下")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("插件前端资源路径不允许包含空段、. 或 ..")
    return "/".join(parts)


class PluginFrontendElement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tag: str = Field(..., min_length=1)

    @field_validator("tag", mode="before")
    @classmethod
    def _normalize_tag(cls, raw: Any) -> str:
        text = str(raw or "").strip()
        if not text:
            raise ValueError("custom element 标签不能为空")
        return text


class PluginFrontendManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(default=1, ge=1)
    renderer: PluginFrontendRenderer = Field(default="custom-element")
    entry: str = Field(..., min_length=1)
    style: list[str] = Field(default_factory=list)
    elements: list[PluginFrontendElement] = Field(default_factory=list)

    @field_validator("renderer", mode="before")
    @classmethod
    def _normalize_renderer(cls, raw: Any) -> PluginFrontendRenderer:
        text = str(raw or "custom-element").strip().lower()
        if text != "custom-element":
            raise ValueError("插件前端 manifest.renderer 仅支持 custom-element")
        return text  # type: ignore[return-value]

    @field_validator("entry", mode="before")
    @classmethod
    def _normalize_entry(cls, raw: Any) -> str:
        return _normalize_asset_path(raw)

    @field_validator("style", mode="before")
    @classmethod
    def _normalize_style(cls, raw: Any) -> list[str]:
        if raw is None:
            return []
        items = raw if isinstance(raw, list) else [raw]
        return [_normalize_asset_path(item) for item in items]


def _plugin_package_root(plugin_source: Any) -> str:
    module_name = str(getattr(plugin_source, "module_name", "") or "").strip()
    if not module_name:
        entry_point = getattr(plugin_source, "entry_point", None)
        module_name = str(getattr(entry_point, "module", "") or "").strip()
    if not module_name:
        raise ValueError("插件缺少可定位的 module_name")
    return module_name.split(".", 1)[0]


def _get_resource_root(plugin_name: str, plugin_source: Any):
    package_root = _plugin_package_root(plugin_source)
    try:
        return resources.files(package_root)
    except Exception as exc:
        raise FileNotFoundError(
            f"无法定位插件包资源: plugin={plugin_name}, package={package_root}"
        ) from exc


def load_frontend_manifest(plugin_name: str, plugin_source: Any) -> PluginFrontendManifest:
    resource_root = _get_resource_root(plugin_name, plugin_source)
    manifest_resource = resource_root.joinpath("frontend", "manifest.json")
    if not manifest_resource.is_file():
        raise FileNotFoundError(
            f"插件缺少 frontend/manifest.json: plugin={plugin_name}"
        )

    try:
        payload = json.loads(manifest_resource.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(
            f"插件前端 manifest 读取失败: plugin={plugin_name}, error={type(exc).__name__}: {exc}"
        ) from exc

    return PluginFrontendManifest.model_validate(payload)


def load_frontend_asset(
    plugin_name: str,
    plugin_source: Any,
    asset_path: str,
):
    normalized_path = _normalize_asset_path(asset_path)
    resource_root = _get_resource_root(plugin_name, plugin_source)
    target = resource_root
    for part in PurePosixPath(normalized_path).parts:
        target = target.joinpath(part)
    if not target.is_file():
        raise FileNotFoundError(
            f"插件前端资源不存在: plugin={plugin_name}, asset={normalized_path}"
        )
    return target


def build_frontend_asset_url(
    plugin_name: str,
    asset_path: str,
    *,
    version: int | None = None,
) -> str:
    normalized_path = _normalize_asset_path(asset_path)
    plugin_segment = quote(str(plugin_name or "").strip(), safe="")
    path_segments = [quote(part, safe="") for part in PurePosixPath(normalized_path).parts]
    url = f"/api/plugins/assets/{plugin_segment}/{'/'.join(path_segments)}"
    if version is not None:
        url = f"{url}?v={int(version)}"
    return url


def _append_error(errors: list[str], message: str) -> None:
    if message not in errors:
        errors.append(message)
        logger.warning(message)


def _infer_frontend_plugin(page: PageDeclaration, records: dict[str, Any]) -> str | None:
    if page.frontend_plugin:
        return page.frontend_plugin
    if not page.source.startswith("plugin:"):
        return None
    instance_id = page.source.split(":", 1)[1].strip()
    if not instance_id:
        return None
    record = records.get(instance_id)
    plugin_name = str(getattr(record, "plugin_name", "") or "").strip()
    return plugin_name or None


def build_page_snapshot(
    *,
    discovered: dict[str, Any],
    records: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    result: list[dict[str, Any]] = []
    errors = list(page_registry.warnings())
    runtime_records = records or {}

    for page in page_registry.list_pages():
        payload = page.model_dump()
        if page.renderer != "custom-element":
            result.append(payload)
            continue

        frontend_plugin = _infer_frontend_plugin(page, runtime_records)
        payload["frontend_plugin"] = frontend_plugin
        if not frontend_plugin:
            _append_error(
                errors,
                f"custom-element 页面缺少 frontend_plugin: id={page.id}, source={page.source}",
            )
            result.append(payload)
            continue

        plugin_source = discovered.get(frontend_plugin)
        if plugin_source is None:
            _append_error(
                errors,
                f"未找到 custom-element 页面对应插件: id={page.id}, frontend_plugin={frontend_plugin}",
            )
            result.append(payload)
            continue

        try:
            manifest = load_frontend_manifest(frontend_plugin, plugin_source)
        except Exception as exc:
            _append_error(
                errors,
                f"插件前端 manifest 无效: page={page.id}, plugin={frontend_plugin}, error={type(exc).__name__}: {exc}",
            )
            result.append(payload)
            continue

        payload["manifest_version"] = manifest.version
        payload["entry_asset_url"] = build_frontend_asset_url(
            frontend_plugin,
            manifest.entry,
            version=manifest.version,
        )
        payload["style_asset_urls"] = [
            build_frontend_asset_url(frontend_plugin, style_path, version=manifest.version)
            for style_path in manifest.style
        ]

        declared_tag = str(page.element_tag or "").strip() or None
        manifest_tags = [item.tag for item in manifest.elements]
        if declared_tag is None:
            if len(manifest_tags) == 1:
                declared_tag = manifest_tags[0]
                payload["element_tag"] = declared_tag
            else:
                _append_error(
                    errors,
                    f"custom-element 页面缺少 element_tag 且 manifest 无法唯一推断: page={page.id}, plugin={frontend_plugin}",
                )
        elif manifest_tags and declared_tag not in manifest_tags:
            _append_error(
                errors,
                f"custom-element 页面 element_tag 未出现在 manifest 中: page={page.id}, tag={declared_tag}, plugin={frontend_plugin}",
            )

        result.append(payload)

    return result, errors
