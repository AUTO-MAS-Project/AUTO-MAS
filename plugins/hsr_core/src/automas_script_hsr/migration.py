from __future__ import annotations

from typing import Any

import json

from app.core.script_config_codec import form_to_storage
from app.models.plugin_script_config import PluginScriptConfig


async def migrate_legacy_hsr_config(legacy_script: Any, provider: Any) -> Any:
    """把宿主 HSRConfig 幂等转换为插件配置容器使用的模型。"""

    raw_script = await legacy_script.toDict(if_decrypt=False)
    info = _group(raw_script, "Info")
    run = _group(raw_script, "Run")
    m7a_path = str(info.get("M7APath") or "")
    sra_path = str(info.get("SRAPath") or "")
    enabled_engines = [
        engine
        for engine, path in (("SRA", sra_path), ("M7A", m7a_path))
        if path.strip()
    ]
    if not enabled_engines:
        enabled_engines = ["SRA", "M7A"]

    user_collection = await _build_user_collection(
        legacy_script,
        provider,
    )
    script_payload = {
        "Info": {"Name": info.get("Name") or "新 HSR 脚本"},
        "Engine": {"EnabledEngines": enabled_engines},
        "SRA": {"Path": sra_path},
        "M7A": {
            "Path": m7a_path,
            "LowPerformanceMode": bool(run.get("LowPerformanceMode")),
        },
        "Game": _group(raw_script, "Game"),
        "Run": {
            key: value
            for key, value in run.items()
            if key != "LowPerformanceMode"
        },
        "TaskMapping": _group(raw_script, "TaskMapping"),
    }

    migrated = PluginScriptConfig()
    await migrated.set("Meta", "PluginTypeKey", provider.type_key)
    await migrated.set("Info", "Name", str(script_payload["Info"]["Name"]))
    storage_payload = await form_to_storage(provider, script_payload, "script")
    await migrated.set(
        "PluginData",
        "Config",
        json.dumps(storage_payload, ensure_ascii=False),
    )
    await migrated.UserData.load(user_collection)
    return migrated


async def _build_user_collection(
    legacy_script: Any,
    provider: Any,
) -> dict[str, Any]:
    result: dict[str, Any] = {"instances": []}
    for uid, old_user in legacy_script.UserData.items():
        raw_user = await old_user.toDict(if_decrypt=False)
        form_payload = _build_user_payload(raw_user)
        storage_payload = await form_to_storage(provider, form_payload, "user")
        result["instances"].append(
            {"uid": str(uid), "type": "PluginUserConfig"}
        )
        result[str(uid)] = {
            "Meta": {"PluginTypeKey": provider.type_key},
            "Info": {"Name": form_payload["Info"].get("Name") or str(uid)},
            "PluginData": {
                "Config": json.dumps(storage_payload, ensure_ascii=False),
            },
        }
    return result


def _build_user_payload(raw_user: dict[str, Any]) -> dict[str, Any]:
    info = _group(raw_user, "Info")
    sub_configs = _group(raw_user, "SubConfigsInfo")
    return {
        "Info": {
            key: value
            for key, value in info.items()
            if key not in {"Id", "Password", "Tag"}
        },
        "SRA": {
            "Id": info.get("Id") or "",
            "Password": info.get("Password") or "",
        },
        "Data": _group(raw_user, "Data"),
        "TaskSwitch": _group(raw_user, "TaskSwitch"),
        "Stage": _group(raw_user, "Stage"),
        "TaskOpt": _group(raw_user, "TaskOpt"),
        "Abyss": _group(raw_user, "Abyss"),
        "Notify": {
            **_group(raw_user, "Notify"),
            "CustomWebhooks": sub_configs.get("Notify_CustomWebhooks", {}),
        },
    }


def _group(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    return dict(value) if isinstance(value, dict) else {}
