"""启动期一次性 JSON 配置升级；运行配置始终由 YAML 框架负责。"""

from __future__ import annotations

import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from app.config import ConfigCollection, ConfigEntry, ExportContext
from app.config.fields import (
    LegacyMarker,
    is_encrypted_model_field,
    is_reactive_model_field,
)
from app.config.fields.hints import UiHintMarker
from app.models.config import (
    GameSignAccount,
    PlanEntry,
    QueueEntry,
    ScriptEntry,
    Setting,
    Tools,
)
from app.utils import get_logger
from app.utils.constants import UTC8
from app.utils.io import read_dict_file, write_file
from app.utils.security import looks_like_dpapi_blob

logger = get_logger("配置升级")

GROUP_NAMES = {"appearance": "UI", "updates": "Update", "arknights_pc": "ArknightsPC"}
COLLECTION_NAMES = {
    "custom_webhooks": "Notify_CustomWebhooks",
    "accounts": "GameSign_Accounts",
    "items": "QueueItem",
    "time_sets": "TimeSet",
    # Legacy ScriptConfig calls the nested user collection UserData.
    "users": "UserData",
}
TYPE_NAMES = {
    "QueueConfig": "QueueEntry",
    "QueueItem": "QueueItemEntry",
    "TimeSet": "TimeSetEntry",
    "GameSignAccountGroup": "GameSignAccount",
    "MaaConfig": "MaaScript",
    "MaaUserConfig": "MaaUser",
    "MaaPlanConfig": "MaaPlan",
}


def convert_emulator_config(source: dict[str, Any]) -> dict[str, Any]:
    """Convert the legacy emulator collection to the new game collection.

    Emulator configuration is the first game adapter migration.  The target
    type is kept as ``MuMuGame`` so the plugin can register and validate it
    during the normal domain activation phase.
    """
    instances = source.get("instances")
    if not isinstance(instances, list):
        raise ValueError("EmulatorConfig.instances 升级格式无效")

    order: list[dict[str, str]] = []
    data: dict[str, dict[str, Any]] = {}
    for item in instances:
        if not isinstance(item, dict):
            raise ValueError("EmulatorConfig.instances 含有无效条目")
        uid = str(UUID(str(item["uid"])))
        if item.get("type") != "EmulatorConfig":
            raise ValueError(f"尚未迁移的模拟器配置类型: {item.get('type')!r}")
        raw = source.get(uid, {})
        info = raw.get("Info", {}) if isinstance(raw, dict) else {}
        if not isinstance(info, dict):
            raise ValueError(f"模拟器配置 {uid} 的 Info 格式无效")
        game_type = str(info.get("Type") or "mumu").casefold()
        if game_type != "mumu":
            raise ValueError(f"尚未迁移的模拟器类型: {game_type}")
        order.append({"uid": uid, "type": "MuMuGame"})
        data[uid] = {
            "info": {
                "name": info.get("Name") or "MuMu模拟器",
                "path": info.get("Path") or None,
                "max_wait_time": info.get("MaxWaitTime", 300),
                "force_kill": bool(
                    info.get("ForceKillOnClose", info.get("ForceKillBeforeLaunch", False))
                ),
            },
            "devices": {"order": [], "data": {}},
        }
    return {"order": order, "data": data}


def _archive_legacy_json(source_path: Path, backup_dir: Path) -> None:
    """Move a migrated source file to the immutable legacy archive."""
    backup_dir.mkdir(exist_ok=True)
    target = backup_dir / source_path.name
    if target.exists():
        # A previous interrupted run may already have archived the source.
        source_path.unlink()
        return
    source_path.replace(target)


def _is_default_entry_payload(
    payload: dict[str, Any], entry_type: type[ConfigEntry]
) -> bool:
    """Recognize the empty placeholder generated before plugin activation."""
    default = entry_type.build().model_dump(
        mode="json", context=ExportContext(audience="persist")
    )
    return payload == default


def _merge_plugin_collection(
    migrated: dict[str, Any],
    existing: dict[str, Any],
    entry_types: dict[str, type[ConfigEntry]],
) -> dict[str, Any]:
    """Merge migrated entries while removing only generated empty placeholders."""
    if not existing.get("order") and not existing.get("data"):
        return migrated

    existing_order = existing.get("order")
    existing_data = existing.get("data")
    if not isinstance(existing_order, list) or not isinstance(existing_data, dict):
        return migrated

    real_existing = []
    for item in existing_order:
        if not isinstance(item, dict):
            continue
        raw = existing_data.get(str(item.get("uid")))
        type_name = str(item.get("type", ""))
        entry_type = entry_types.get(type_name)
        if isinstance(raw, dict) and entry_type and not _is_default_entry_payload(
            raw, entry_type
        ):
            real_existing.append(item)

    # The only pre-plugin YAML currently produced is a single default MaaScript
    # placeholder. Replace that placeholder with the legacy source entries.
    if not real_existing:
        return migrated

    result = {
        "order": list(existing_order),
        "data": dict(existing_data),
    }
    known = {str(item.get("uid")) for item in existing_order if isinstance(item, dict)}
    for item in migrated.get("order", []):
        if not isinstance(item, dict):
            continue
        uid = str(item.get("uid"))
        if uid not in known:
            result["order"].append(item)
        result["data"][uid] = migrated.get("data", {}).get(uid, {})
    return result


def _convert_maa_script(source: dict[str, Any], entry_type: type[ScriptEntry]) -> dict[str, Any]:
    """Convert one legacy MaaConfig without reconstructing MAA internals."""
    result = convert_entry(source, entry_type.build())
    info = result.setdefault("info", {})
    emulator = source.get("Emulator")
    if isinstance(emulator, dict):
        game_id = emulator.get("Id")
        if game_id not in (None, "", "-"):
            try:
                info["game_id"] = str(UUID(str(game_id)))
            except (TypeError, ValueError):
                logger.warning(f"Skipping invalid legacy MAA game id: {game_id!r}")
    # MaaUser used Info.Id for the account identifier; the new model names it
    # account_id so it is not confused with the host entry UUID.
    nested = source.get("SubConfigsInfo", {})
    if isinstance(nested, dict):
        for user_item in nested.get("UserData", {}).get("instances", []):
            if not isinstance(user_item, dict):
                continue
            user_uid = str(user_item.get("uid", ""))
            user_raw = nested.get("UserData", {}).get(user_uid)
            if not isinstance(user_raw, dict):
                continue
            user_payload = result.get("users", {}).get("data", {}).get(user_uid)
            account_id = user_raw.get("Info", {}).get("Id")
            if isinstance(user_payload, dict) and account_id is not None:
                user_payload.setdefault("info", {})["account_id"] = str(account_id)
    # Legacy Index is a transient emulator index, not a new device UUID.
    info["game_device_id"] = "-"
    return result


def convert_maa_script_collection(
    source: dict[str, Any], collection: ConfigCollection[ScriptEntry]
) -> dict[str, Any]:
    """Convert only MaaConfig entries and report unsupported script types."""
    entry_type = collection._entry_types.get("MaaScript")
    if entry_type is None:
        raise LookupError("MaaScript is not registered")
    order: list[dict[str, str]] = []
    data: dict[str, dict[str, Any]] = {}
    skipped: list[str] = []
    for item in source.get("instances", []):
        if not isinstance(item, dict):
            raise ValueError("ScriptConfig.instances contains an invalid item")
        uid = str(UUID(str(item["uid"])))
        legacy_type = str(item.get("type", ""))
        if legacy_type != "MaaConfig":
            skipped.append(legacy_type)
            continue
        raw = source.get(uid)
        if not isinstance(raw, dict):
            raise ValueError(f"ScriptConfig entry {uid} is invalid")
        order.append({"uid": uid, "type": "MaaScript"})
        data[uid] = _convert_maa_script(raw, entry_type)
    if skipped:
        logger.warning(
            f"Skipped unsupported legacy script types during migration: "
            f"{', '.join(sorted(set(skipped)))}"
        )
    return {"order": order, "data": data}


def convert_maa_plan_collection(
    source: dict[str, Any], collection: ConfigCollection[PlanEntry]
) -> dict[str, Any]:
    """Convert only MaaPlanConfig entries; each weekday is validated by MaaPlan."""
    entry_type = collection._entry_types.get("MaaPlan")
    if entry_type is None:
        raise LookupError("MaaPlan is not registered")
    order: list[dict[str, str]] = []
    data: dict[str, dict[str, Any]] = {}
    skipped: list[str] = []
    for item in source.get("instances", []):
        if not isinstance(item, dict):
            raise ValueError("PlanConfig.instances contains an invalid item")
        uid = str(UUID(str(item["uid"])))
        legacy_type = str(item.get("type", ""))
        if legacy_type != "MaaPlanConfig":
            skipped.append(legacy_type)
            continue
        raw = source.get(uid)
        if not isinstance(raw, dict):
            raise ValueError(f"PlanConfig entry {uid} is invalid")
        order.append({"uid": uid, "type": "MaaPlan"})
        data[uid] = convert_entry(raw, entry_type.build())
    if skipped:
        logger.warning(
            f"Skipped unsupported legacy plan types during migration: "
            f"{', '.join(sorted(set(skipped)))}"
        )
    return {"order": order, "data": data}


def upgrade_plugin_json_configs(
    config_path: Path,
    scripts: ConfigCollection[ScriptEntry],
    plans: ConfigCollection[PlanEntry],
) -> None:
    """Migrate approved plugin JSON once after plugin type registration."""
    migrations = (
        ("ScriptConfig.json", "scripts.yaml", scripts, convert_maa_script_collection),
        ("PlanConfig.json", "plans.yaml", plans, convert_maa_plan_collection),
    )
    backup_dir = config_path / "legacy-json"
    for old_name, new_name, collection, converter in migrations:
        source_path = config_path / old_name
        if not source_path.exists():
            continue
        source = read_dict_file(source_path)
        migrated = converter(source, collection)
        target = config_path / new_name
        existing = read_dict_file(target)
        payload = _merge_plugin_collection(migrated, existing, collection._entry_types)
        write_file(target, payload)
        _archive_legacy_json(source_path, backup_dir)
        logger.info(f"Migrated approved plugin config: {old_name} -> {new_name}")


def convert_entry(source: dict[str, Any], entry: ConfigEntry) -> dict[str, Any]:
    """按新模型字段转换旧分组，并沿用模型校验与敏感字段序列化。"""
    result: dict[str, Any] = {}
    for group_name in entry._cfg_group_fields:
        group = entry.__dict__[group_name]
        old_name = GROUP_NAMES.get(group_name, group_name)
        if isinstance(entry, GameSignAccount) and group_name == "info":
            old_name = "GameSignAccount"
        old = next(
            (
                v
                for k, v in source.items()
                if k.casefold().replace("_", "") == old_name.casefold().replace("_", "")
            ),
            {},
        )
        values: dict[str, Any] = {}
        for name, field in type(group).model_fields.items():
            if is_reactive_model_field(field):
                continue
            value_found = False
            value: Any = None
            for key, raw in old.items():
                if key.casefold().replace("_", "") == name.replace("_", ""):
                    value, value_found = raw, True
                    break
            for marker in field.metadata:
                if isinstance(marker, LegacyMarker) and not value_found:
                    legacy_group = source.get(marker.group, {})
                    if marker.name in legacy_group:
                        value, value_found = legacy_group[marker.name], True
            if not value_found:
                continue
            if (
                is_encrypted_model_field(field)
                and isinstance(value, str)
                and looks_like_dpapi_blob(value)
            ):
                value = "DPAPI:" + value
            if isinstance(value, str):
                hint = next(
                    (m for m in field.metadata if isinstance(m, UiHintMarker)), None
                )
                if hint and hint.format and hint.format.startswith("hm"):
                    if not value:
                        continue
                    if len(value) in (5, 8):
                        value = "2000-01-01T" + value
                    value = datetime.fromisoformat(value).replace(tzinfo=UTC8)
                elif name in {
                    "next_run_at",
                    "last_cycle_started_at",
                    "last_cycle_finished_at",
                    "last_startup_time",
                }:
                    value = (
                        datetime.fromisoformat(value).replace(tzinfo=UTC8)
                        if value
                        else None
                    )
                    if value is not None and value.date() <= date(2000, 1, 1):
                        value = None
            values[name] = value
        if isinstance(entry, QueueEntry) and group_name == "info":
            values["schedule_mode"] = (
                "cycle" if source.get("Info", {}).get("CycleEnabled") else "timed"
            )
        # 校验异常不打印 payload，凭据只能出现在原文件与备份里。
        try:
            validated = type(group).model_validate(values)
        except Exception:
            raise ValueError(
                f"{type(entry).__name__}.{group_name} 升级校验失败"
            ) from None
        result[group_name] = validated.model_dump(
            mode="json", context=ExportContext(audience="persist"), exclude_unset=True
        )
    nested = source.get("SubConfigsInfo", {})
    for name in entry._cfg_collection_fields:
        old = nested.get(COLLECTION_NAMES.get(name, name))
        if old is not None:
            result[name] = convert_collection(old, entry.__dict__[name])
    return result


def convert_collection(
    source: dict[str, Any], collection: ConfigCollection
) -> dict[str, Any]:
    """转换一次旧 instances/UUID 结构，保留顺序、UUID 与引用值。"""
    types = collection._entry_types
    order = []
    data = {}
    for item in source["instances"]:
        uid = str(UUID(item["uid"]))
        name = TYPE_NAMES.get(item["type"], item["type"])
        if name not in types:
            raise ValueError(f"尚未迁移配置类型：{item['type']}")
        order.append({"uid": uid, "type": name})
        data[uid] = convert_entry(source[uid], types[name].build())
    return {"order": order, "data": data}


def merge_existing(
    source: dict[str, Any], existing: dict[str, Any], defaults: dict[str, Any]
) -> dict[str, Any]:
    """已修改的 YAML 值优先；仅导入缺项或迁移草案生成的默认值。"""
    result = dict(existing)
    for key, value in source.items():
        if key not in existing or existing[key] == defaults.get(key):
            result[key] = value
        elif isinstance(value, dict) and isinstance(existing[key], dict):
            if (
                set(value) >= {"order", "data"}
                and not existing[key].get("order")
                and not existing[key].get("data")
                and (value.get("order") or value.get("data"))
            ):
                result[key] = value
                continue
            result[key] = merge_existing(value, existing[key], defaults.get(key, {}))
    return result


def upgrade_json_configs(config_path: Path) -> None:
    """升级已迁移领域，成功后归档源文件；后续启动不再读取归档 JSON。"""
    roots = (
        ("Config.json", "setting.yaml", Setting.build()),
        ("ToolsConfig.json", "tools.yaml", Tools.build()),
        ("QueueConfig.json", "queues.yaml", ConfigCollection.build([QueueEntry])),
    )
    for old_name, new_name, node in roots:
        source_path = config_path / old_name
        if not source_path.exists():
            continue
        source = read_dict_file(source_path)
        converter = (
            convert_collection if isinstance(node, ConfigCollection) else convert_entry
        )
        migrated = converter(source, node)
        target = config_path / new_name
        existing = read_dict_file(target)
        defaults = node.model_dump(
            mode="json", context=ExportContext(audience="persist")
        )
        # UID 是随机默认值，旧安装身份需保留；其余已有非默认 YAML 值不覆盖。
        if old_name == "Config.json" and "uid" in migrated.get("data", {}):
            defaults.setdefault("data", {})["uid"] = existing.get("data", {}).get("uid")
        payload = merge_existing(migrated, existing, defaults)
        backup_dir = config_path / "legacy-json"
        backup_dir.mkdir(exist_ok=True)
        # 未映射字段保留在完整归档里，并显式提醒后端能力核对尚未结束。
        logger.info(f"升级原始配置完整保留于 legacy-json/{old_name}，用于核对未迁移能力")
        if target.exists() and not (backup_dir / new_name).exists():
            shutil.copy2(target, backup_dir / new_name)
        write_file(target, payload)
        # 归档是本文件升级完成标记；写入失败时旧文件仍在，可再次启动重试。
        source_path.replace(backup_dir / old_name)
        logger.info(f"配置一次性升级完成：{old_name} → {new_name}")

    emulator_source_path = config_path / "EmulatorConfig.json"
    if emulator_source_path.exists():
        source = read_dict_file(emulator_source_path)
        migrated = convert_emulator_config(source)
        target = config_path / "games.yaml"
        existing = read_dict_file(target)
        payload = migrated if not existing.get("order") and not existing.get("data") else existing
        backup_dir = config_path / "legacy-json"
        backup_dir.mkdir(exist_ok=True)
        write_file(target, payload)
        emulator_source_path.replace(backup_dir / "EmulatorConfig.json")
        logger.info("配置一次性升级完成：EmulatorConfig.json → games.yaml")
