from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from app.core import Config as app_config
from app.plugins import PluginHttpRequest, ScriptAdapterDefinition, ScriptAdapterPlugin
from app.plugins.script_config_store import ScriptConfigStore
from app.utils import get_logger

from .adapter import OkwwAdapterHooks
from .adapter.autoproxy import _OKWW_REL_CONFIG_DIR, _OKWW_REL_EXE
from .config_schema import (
    build_fields_for_config,
    get_all_config_info,
    get_field_specs,
    load_okww_option_labels,
)
from .schema import OkwwConfig, OkwwUserConfig

DEFAULT_INSTANCE = {
    "name": "OK-WW 专项适配",
    "enabled": True,
    "config": {},
}

SCRIPT_ADAPTER_TYPE_KEYS = ("Okww",)
logger = get_logger("OK-WW 插件适配")


def _okww_mas_config_dir(script_id: str, user_id: str) -> Path:
    script_uid = str(uuid.UUID(str(script_id)))
    user_uid = str(uuid.UUID(str(user_id)))
    data_root = (Path.cwd() / "data").resolve()
    target = (data_root / script_uid / user_uid / "ConfigFile").resolve()
    if data_root != target and data_root not in target.parents:
        raise ValueError("非法配置目录路径")
    return target


def _okww_config_file_path(config_dir: Path, filename: str) -> Path:
    target = (config_dir / filename).resolve()
    root = config_dir.resolve()
    if root != target and root not in target.parents:
        raise ValueError("非法配置文件路径")
    return target


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _write_json_file_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_path.replace(path)


def _ensure_user_config_defaults(
    config_dir: Path,
    source_dir: Path | None,
    filenames: list[str],
) -> None:
    if source_dir is None or not source_dir.is_dir():
        return
    config_dir.mkdir(parents=True, exist_ok=True)
    for filename in filenames:
        source_path = source_dir / filename
        if not source_path.is_file():
            continue
        current_path = _okww_config_file_path(config_dir, filename)
        source_data = _read_json_file(source_path)
        current_data = _read_json_file(current_path)
        merged_data = {**source_data, **current_data}
        if merged_data != current_data:
            _write_json_file_atomic(current_path, merged_data)


def _iter_config_updates(raw: Any) -> list[tuple[str, dict[str, Any]]]:
    updates: list[tuple[str, dict[str, Any]]] = []
    if isinstance(raw, dict):
        for filename, data in raw.items():
            if isinstance(filename, str) and isinstance(data, dict):
                updates.append((filename, data))
        return updates
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            filename = item.get("filename")
            data = item.get("data")
            if isinstance(filename, str) and isinstance(data, dict):
                updates.append((filename, data))
    return updates


class Plugin(ScriptAdapterPlugin):
    """OK-WW script adapter plugin."""

    def build_script_adapters(self) -> list[ScriptAdapterDefinition]:
        return [
            ScriptAdapterDefinition(
                type_key="Okww",
                display_name="ok-ww脚本",
                script_model=OkwwConfig,
                user_model=OkwwUserConfig,
                hooks_factory=OkwwAdapterHooks,
                supported_modes=("AutoProxy",),
                icon="Okww",
                editor_kind="plugin:okww_adapter",
                metadata={
                    "framework": "ok-script",
                    "source": "okww_adapter",
                    "client": {
                        "config_editor": {
                            "kind": "json-files",
                            "endpoint_prefix": "/plugin/okww/configs",
                        }
                    },
                },
            )
        ]

    async def on_start(self) -> None:
        await super().on_start()
        self.ctx.server.http(
            "/okww/configs/list",
            self._list_configs,
            methods=("GET", "POST"),
        )
        self.ctx.server.http(
            "/okww/configs/update",
            self._update_config,
            methods=("POST",),
        )
        self.ctx.server.http(
            "/okww/configs/batch-update",
            self._batch_update_configs,
            methods=("POST",),
        )

    async def _script_form_config(self, script_id: str) -> dict[str, Any]:
        script_config = app_config.ScriptConfig[uuid.UUID(script_id)]
        from app.core.script_types import script_type_registry

        provider = script_type_registry.get("Okww")
        type_key_resolver = getattr(app_config, "get_script_type_key", None)
        actual_type_key = None
        if callable(type_key_resolver):
            try:
                actual_type_key = str(type_key_resolver(script_id) or "").strip()
            except (KeyError, TypeError, ValueError):
                actual_type_key = None
        if not actual_type_key:
            try:
                actual_type_key = str(
                    script_config.get("Meta", "PluginTypeKey") or ""
                ).strip()
            except (AttributeError, KeyError):
                actual_type_key = None
        if not actual_type_key:
            try:
                actual_type_key = script_type_registry.get_by_script_config(
                    script_config
                ).type_key
            except KeyError:
                actual_type_key = None
        if actual_type_key != provider.type_key:
            raise ValueError("脚本不是 OK-WW 插件配置")

        return await ScriptConfigStore(
            provider=provider,
            storage_script_config=script_config,
        ).read_script_data()

    async def _script_root_path(self, script_id: str) -> Path | None:
        config = await self._script_form_config(script_id)
        root_path = config.get("Info", {}).get("RootPath")
        if isinstance(root_path, str) and root_path.strip():
            return Path(root_path)
        return None

    async def _list_configs(self, request: PluginHttpRequest) -> dict[str, Any]:
        payload = request.json if isinstance(request.json, dict) else request.query
        script_id = str(payload.get("script_id") or payload.get("scriptId") or "")
        user_id = str(payload.get("user_id") or payload.get("userId") or "")
        if not script_id or not user_id:
            return {"code": 400, "status": "error", "message": "缺少 script_id 或 user_id"}
        try:
            mas_config_dir = _okww_mas_config_dir(script_id, user_id)
        except ValueError as exc:
            return {"code": 400, "status": "error", "message": str(exc)}

        try:
            root_path = await self._script_root_path(script_id)
        except (KeyError, ValueError) as exc:
            return {"code": 400, "status": "error", "message": str(exc)}

        # ok-ww 程序不可用时不返回静态兜底字段：缺少安装目录就无法动态读取
        # 配置项与中文翻译，静态字段会误导用户编辑到不存在/无翻译的项。
        if root_path is None or not (root_path / _OKWW_REL_EXE).is_file():
            return {
                "code": 409,
                "status": "unavailable",
                "message": "当前 ok-ww 程序不可用，请返回脚本设置选择正确的 ok-ww 根目录",
                "data": [],
            }

        option_labels = load_okww_option_labels(root_path)
        okww_configs_dir = root_path / _OKWW_REL_CONFIG_DIR

        # 动态注册表 + 字段规格（下拉候选项）按 config.py version 缓存。
        config_info = get_all_config_info(root_path, option_labels)
        field_specs = get_field_specs(root_path)
        filenames = [str(info["filename"]) for info in config_info]

        _ensure_user_config_defaults(mas_config_dir, okww_configs_dir, filenames)

        configs: list[dict[str, Any]] = []
        for info in config_info:
            filename = str(info["filename"])
            file_path = mas_config_dir / filename
            data = _read_json_file(file_path)
            configs.append(
                {
                    **info,
                    "exists": file_path.is_file(),
                    "fields": build_fields_for_config(
                        filename, data, option_labels, field_specs
                    ),
                    "currentData": data,
                }
            )

        return {
            "code": 200,
            "status": "success",
            "data": configs,
            "optionLabels": option_labels,
            "configPath": str(mas_config_dir),
        }

    async def _update_config(self, request: PluginHttpRequest) -> dict[str, Any]:
        payload = request.json if isinstance(request.json, dict) else {}
        script_id = str(payload.get("script_id") or payload.get("scriptId") or "")
        user_id = str(payload.get("user_id") or payload.get("userId") or "")
        filename = str(payload.get("filename") or "")
        data = payload.get("data")
        if not script_id or not user_id or not filename or not isinstance(data, dict):
            return {"code": 400, "status": "error", "message": "请求参数不完整"}

        try:
            config_dir = _okww_mas_config_dir(script_id, user_id)
        except ValueError as exc:
            return {"code": 400, "status": "error", "message": str(exc)}
        config_dir.mkdir(parents=True, exist_ok=True)
        file_path = _okww_config_file_path(config_dir, filename)
        existing_data = _read_json_file(file_path)
        existing_data.update(data)
        _write_json_file_atomic(file_path, existing_data)
        return {"code": 200, "status": "success"}

    async def _batch_update_configs(self, request: PluginHttpRequest) -> dict[str, Any]:
        payload = request.json if isinstance(request.json, dict) else {}
        script_id = str(payload.get("script_id") or payload.get("scriptId") or "")
        user_id = str(payload.get("user_id") or payload.get("userId") or "")
        configs = payload.get("configs")
        updates = _iter_config_updates(configs)
        if not script_id or not user_id or not updates:
            return {"code": 400, "status": "error", "message": "请求参数不完整"}

        try:
            config_dir = _okww_mas_config_dir(script_id, user_id)
        except ValueError as exc:
            return {"code": 400, "status": "error", "message": str(exc)}
        config_dir.mkdir(parents=True, exist_ok=True)
        updated_files: list[str] = []
        for filename, data in updates:
            file_path = _okww_config_file_path(config_dir, filename)
            existing_data = _read_json_file(file_path)
            existing_data.update(data)
            _write_json_file_atomic(file_path, existing_data)
            updated_files.append(filename)
        return {"code": 200, "status": "success", "data": updated_files}
