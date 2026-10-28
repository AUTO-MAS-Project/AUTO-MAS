"""启动期一次性配置升级，运行期只使用新配置文档。"""

from __future__ import annotations

import hashlib
import shutil
from collections.abc import Callable, Mapping
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, get_args
from uuid import UUID

from app.config import ConfigCollection, ConfigEntry, ExportContext
from app.config.fields import is_encrypted_model_field, is_reactive_model_field
from app.config.fields.hints import migrate_legacy_fields
from app.config.types import TzMarker
from app.models.config.shared import local_timezone
from app.utils import UTC4, looks_like_dpapi_blob
from app.utils import io as _utils_io

MIGRATION_RECORD = ".config-migration-v2.json"
CONFIG_FILES = (
    ("Config.json", "setting.yaml", "setting"),
    ("EmulatorConfig.json", "emulators.yaml", "EmulatorConfig"),
    ("PlanConfig.json", "plans.yaml", "PlanConfig"),
    ("ScriptConfig.json", "scripts.yaml", "ScriptConfig"),
    ("QueueConfig.json", "queues.yaml", "QueueConfig"),
    ("ToolsConfig.json", "tools.yaml", "ToolsConfig"),
    ("GameSignAccounts.json", "game_sign_accounts.yaml", "GameSignAccounts"),
)

# 专项只解释当前条目的旧载荷；递归、校验和持久化仍由升级管道负责。
LegacyEntryMigrations = Mapping[type[ConfigEntry], Callable[[dict[str, Any]], None]]


def contains_legacy_type(path: Path, entry_type: str) -> bool:
    """按类型标签轻量筛选旧文档，避免无对应配置时加载专项。"""
    try:
        return f'"{entry_type}"'.encode() in path.read_bytes()
    except OSError:
        return False


def convert_legacy(
    document: dict[str, Any],
    node: ConfigEntry | ConfigCollection,
    *,
    entry_migrations: LegacyEntryMigrations | None = None,
) -> dict[str, Any]:
    """转换旧分组和 instances/SubConfigsInfo，不推断或重建成员身份。"""
    if not isinstance(document, dict):
        raise ValueError("旧配置必须为映射")
    if isinstance(node, ConfigCollection):
        instances = document.get("instances", [])
        if not isinstance(instances, list):
            raise ValueError("旧集合索引无效")
        order = []
        data = {}
        for item in instances:
            uid = str(UUID(item["uid"]))
            entry_type = node._entry_types.get(item["type"])
            if entry_type is None:
                raise ValueError(f"尚未迁移的配置类型：{item['type']}")
            if uid in data or not isinstance(document.get(uid), dict):
                raise ValueError("旧集合成员缺失或身份重复")
            order.append({"uid": uid, "type": item["type"]})
            data[uid] = convert_legacy(
                document[uid], entry_type.build(), entry_migrations=entry_migrations
            )
        return {"order": order, "data": data}

    from app.models.config.plan import PlanDaysConfig

    if isinstance(node, PlanDaysConfig):
        # 历史 JSON 的 Days 容器仅在一次性升级展开；运行期直接使用配置分组。
        document = dict(document)
        days = document.pop("Days", None)
        if isinstance(days, dict):
            for day, value in days.items():
                group = node.day_group_of(str(day))
                if group is not None:
                    document[group] = value

    normalize = getattr(type(node), "normalize_payload", None)
    source = migrate_legacy_fields(
        type(node), normalize(document) if normalize else document
    )
    migrate = entry_migrations.get(type(node)) if entry_migrations else None
    if migrate is not None:
        migrate(source)
    groups = {}
    # 只在一次性升级中解释旧日期/钟点；运行时无时区输入统一按 UTC 解释。
    legacy_naive: list[tuple[str, str, datetime, bool]] = []
    for group_name in node._cfg_group_fields:
        if group_name == "ui":
            continue
        group = node.__dict__[group_name]
        old_group = source.get(group_name, {})
        if not isinstance(old_group, dict):
            raise ValueError(f"配置分组无效：{group_name}")
        values = {}
        for name, field in type(group).model_fields.items():
            if is_reactive_model_field(field):
                continue
            found = name in old_group
            value = old_group.get(name)
            if found:
                if field.annotation is datetime or datetime in get_args(
                    field.annotation
                ):
                    if value is None or value == "":
                        if type(None) in get_args(field.annotation):
                            values[name] = None
                            continue
                    try:
                        if isinstance(value, datetime):
                            parsed = value
                        elif isinstance(value, date):
                            parsed = datetime.combine(value, time.min)
                        elif isinstance(value, str):
                            try:
                                parsed = datetime.fromisoformat(value)
                            except ValueError:
                                if (type(node).__name__, group_name, name) == (
                                    "MaaUserConfig",
                                    "Data",
                                    "GreenTicketStoreMonth",
                                ):
                                    month = datetime.strptime(value, "%Y-%m")
                                    if (month.year, month.month) == (2000, 1):
                                        values[name] = None
                                        continue
                                    # 旧数据只有月份，以月中代表时刻保留所属月，并非实际完成时间。
                                    parsed = month.replace(day=15, hour=12, tzinfo=UTC4)
                                else:
                                    # 旧协议仅这两个字段保存纯时分；迁移不依赖可变的 UI 提示。
                                    if (type(node).__name__, group_name, name) in {
                                        ("TimeSet", "Info", "Time"),
                                        ("QueueItem", "Schedule", "Time"),
                                    }:
                                        # 旧校验允许未补零，迁移沿用其解析范围。
                                        parsed = datetime.combine(
                                            date(2000, 1, 1),
                                            datetime.strptime(value, "%H:%M").time(),
                                        )
                                    else:
                                        # 旧完整日期时间也使用 strptime，合法值未必补零。
                                        for date_format in (
                                            "%Y-%m-%d %H:%M:%S",
                                            "%Y-%m-%d %H:%M",
                                            "%Y-%m-%d",
                                        ):
                                            try:
                                                parsed = datetime.strptime(
                                                    value, date_format
                                                )
                                            except ValueError:
                                                continue
                                            break
                                        else:
                                            raise
                        else:
                            raise TypeError("旧日期时间必须为字符串或日期对象")
                        if parsed.utcoffset() is None:
                            full_datetime = isinstance(value, datetime) or (
                                isinstance(value, str)
                                and ("T" in value or " " in value)
                            )
                            legacy_naive.append(
                                (group_name, name, parsed, full_datetime)
                            )
                        value = parsed
                    except (TypeError, ValueError):
                        raise ValueError(
                            f"旧日期时间无效：{type(node).__name__}.{group_name}.{name}"
                        ) from None
                if (
                    is_encrypted_model_field(field)
                    and isinstance(value, str)
                    and looks_like_dpapi_blob(value)
                ):
                    value = "DPAPI:" + value
                values[name] = value
        groups[group_name] = values
    try:
        # Persist serialization preserves ciphertext and excludes reactive fields.
        converted = type(node).model_validate(groups)
        # 全部业务字段已完成冷态校验及绑定，动态预设可读取原服务器设置。
        for group_name, name, parsed, full_datetime in legacy_naive:
            group = converted.__dict__[group_name]
            markers = type(group).model_fields[name].metadata
            # 完整本地时间采用该历史日期的系统偏移；旧纯日期/钟点保留其显示口径。
            value = (
                parsed.astimezone()
                if full_datetime
                and any(
                    isinstance(marker, TzMarker) and marker.tz is local_timezone
                    for marker in markers
                )
                else parsed.replace(tzinfo=group._read_zone(name))
            )
            setattr(
                group,
                name,
                value.astimezone(timezone.utc),
            )
        result = converted.model_dump(context=ExportContext(audience="persist"))
    except Exception:
        raise ValueError(f"配置字段转换失败：{type(node).__name__}") from None
    subconfigs = source.get("SubConfigsInfo", {})
    if not isinstance(subconfigs, dict):
        raise ValueError("嵌套配置无效")
    for name in node._cfg_collection_fields:
        result[name] = convert_legacy(
            subconfigs.get(name, {}),
            getattr(node, name),
            entry_migrations=entry_migrations,
        )
    return result


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# BOM 与 ASCII 空白（含 VT/FF）；strip 后不剩字节的遗留文件视为无数据。
_BLANK_MARKS = b"\xef\xbb\xbf \t\r\n\x0b\x0c"


def is_blank_file(path: Path) -> bool:
    """0 字节或仅剩 BOM 与空白的遗留文件视为无数据，不判损坏。

    空文件没有任何可迁移的数据，按默认值重建并照常归档，与「空白或仅
    注释的配置按默认值处理」的既有口径一致；非空但解析失败仍报损坏。
    """
    return not path.read_bytes().strip(_BLANK_MARKS)


def preserve_pre_upgrade(config_path: Path) -> None:
    """按固定 JSON 白名单留存升级原件，重试不覆盖已有备份。"""
    backup = config_path / "legacy-json" / "pre-upgrade"
    backup.mkdir(parents=True, exist_ok=True)
    # 七个聚合文件及早期升级实际涉及的 JSON；保留相对路径，不复制目录内容。
    for pattern in (
        *(old for old, _new, _key in CONFIG_FILES),
        "config.json",
        "QueueConfig/*.json",
        "MaaPlanConfig/*/config.json",
        "MaaConfig/*/config.json",
        "MaaConfig/*/Default/gui.json",
        "MaaConfig/*/UserData/*/config.json",
        "MaaConfig/*/UserData/*/Routine/gui.json",
        "MaaConfig/*/UserData/*/Infrastructure/infrastructure.json",
        "GeneralConfig/*/config.json",
        "GeneralConfig/*/SubData/*/config.json",
    ):
        for source in config_path.glob(pattern):
            if not source.is_file():
                continue
            target = backup / source.relative_to(config_path)
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def upgrade_json_configs(
    config_path: Path,
    nodes: dict[str, ConfigEntry | ConfigCollection],
    *,
    prepared_documents: dict[str, dict[str, Any]] | None = None,
    entry_migrations: LegacyEntryMigrations | None = None,
) -> None:
    """逐文件完成 JSON→YAML 转换；调用方须在激活及保存成功后提交 v2.0。"""
    config_path.mkdir(parents=True, exist_ok=True)
    record_path = config_path / MIGRATION_RECORD
    record = _utils_io.read_dict_file(record_path)
    if record and record.get("version") != 2:
        raise ValueError("配置迁移记录版本无效")
    record.setdefault("version", 2)
    files = record.setdefault("files", {})
    backup_dir = config_path / "legacy-json"
    backup_dir.mkdir(exist_ok=True)
    prepared_documents = prepared_documents or {}
    tools_source = config_path / "ToolsConfig.json"
    if not tools_source.exists() and files.get("ToolsConfig.json"):
        # 工具文件已归档但账号文件尚未写入时，重试仍须读取原嵌套账号。
        tools_source = backup_dir / "ToolsConfig.json"
    embedded_accounts = {}
    if tools_source.exists():
        # 空白工具配置没有内嵌账号可读，不判损坏。
        tools = (
            {}
            if is_blank_file(tools_source)
            else _utils_io.read_dict_file(tools_source)
        )
        embedded_accounts = tools.get("SubConfigsInfo", {}).get("GameSign_Accounts", {})

    for old_name, new_name, key in CONFIG_FILES:
        source = config_path / old_name
        target = config_path / new_name
        archived = backup_dir / old_name
        progress = files.get(old_name)
        if progress:
            if (
                progress["state"] == "complete"
                and target.exists()
                and not source.exists()
            ):
                # 已归档的文件不再导入；保留迁移后正常校正或用户修改的 YAML。
                _utils_io.read_dict_file(target)
                continue
            if target.exists() and _digest(target) == progress["target_sha256"]:
                if source.exists():
                    if _digest(source) != progress["source_sha256"]:
                        raise ValueError(f"迁移期间原配置发生变化：{old_name}")
                    if not archived.exists():
                        source.replace(archived)
                    elif _digest(archived) == _digest(source):
                        source.unlink()
                    else:
                        raise ValueError(f"旧配置归档冲突：{old_name}")
                progress["state"] = "complete"
                _utils_io.write_file(record_path, record)
                continue
            if target.exists():
                raise ValueError(f"迁移目标发生变化，已保留现有文件：{new_name}")
            if progress["state"] == "complete":
                raise ValueError(f"已迁移文件缺失：{new_name}")
        elif target.exists():
            raise ValueError(f"存在未登记的目标配置，未覆盖：{new_name}")

        node = nodes[key]
        if key in prepared_documents:
            payload = prepared_documents[key]
        elif source.exists() and not is_blank_file(source):
            payload = convert_legacy(
                _utils_io.read_dict_file(source),
                node,
                entry_migrations=entry_migrations,
            )
        elif key == "GameSignAccounts" and embedded_accounts:
            # 空白的账号文件没有可迁数据，优先沿用 ToolsConfig 内嵌账号。
            payload = convert_legacy(
                embedded_accounts, node, entry_migrations=entry_migrations
            )
        else:
            # 空白遗留文件按默认配置生成目标，源文件仍照常记录摘要并归档。
            payload = node.model_dump(context=ExportContext(audience="persist"))
        temporary = target.with_name(target.name + ".migration.tmp")
        _utils_io.write_file(temporary, payload, format=".yaml")
        if _utils_io.read_dict_file(temporary, format=".yaml") != payload:
            raise ValueError(f"迁移文件校验失败：{new_name}")
        files[old_name] = {
            "target": new_name,
            "source_sha256": _digest(source) if source.exists() else None,
            "target_sha256": _digest(temporary),
            "state": "prepared",
        }
        _utils_io.write_file(record_path, record)
        temporary.replace(target)
        if source.exists():
            if archived.exists() and _digest(archived) != _digest(source):
                raise ValueError(f"旧配置归档冲突：{old_name}")
            if not archived.exists():
                source.replace(archived)
            else:
                source.unlink()
        files[old_name]["state"] = "complete"
        _utils_io.write_file(record_path, record)
    record["complete"] = True
    _utils_io.write_file(record_path, record)
