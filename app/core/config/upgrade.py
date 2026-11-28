"""启动期一次性配置升级，运行期只使用新配置文档。"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
from collections.abc import Callable, Mapping
from contextlib import closing
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
    ("GameSignAccounts.json", "sign_flow_accounts.yaml", "SignFlowAccounts"),
)

#: 改名前的集合成员类型名。旧 JSON 是一次性升级的输入，里面的类型标签仍是
#: 改名前的类名；运行期文档不会出现旧名，所以只在转换入口查一次。
LEGACY_ENTRY_TYPE_NAMES = {"GameSignAccountGroup": "SignFlowAccountGroup"}

#: 改名前的活跃文档名。v2.2 用户手里直接是 YAML，不经过 JSON 迁移管道，
#: 只能按「旧文件在、新文件不在」判断是否需要搬。
LEGACY_SIGN_FLOW_DOCUMENTS = (
    ("game_sign_accounts.yaml", "sign_flow_accounts.yaml"),
    ("GameSignResult.json", "SignFlowResult.json"),
)

#: 新文档名 → 改名前的文档名。续跑要按「内容实际落在哪个名字」结账。
LEGACY_DOCUMENT_NAMES = {new: old for old, new in LEGACY_SIGN_FLOW_DOCUMENTS}

# 专项只解释当前条目的旧载荷；递归、校验和持久化仍由升级管道负责。
LegacyEntryMigrations = Mapping[type[ConfigEntry], Callable[[dict[str, Any]], None]]


def contains_legacy_type(path: Path, entry_type: str) -> bool:
    """按类型标签轻量筛选旧文档，避免无对应配置时加载专项。"""
    try:
        return f'"{entry_type}"'.encode() in path.read_bytes()
    except OSError:
        return False


def retire_baah_plans(config_path: Path) -> None:
    """归档并移除已停用的 MAS 计划，不接触 BAAH 原生配置。"""
    path = config_path / "plans.yaml"
    if not path.is_file() or is_blank_file(path):
        return
    document = _utils_io.read_dict_file(path)
    order = document.get("order", [])
    retired = {item["uid"] for item in order if item["type"] == "BAAHPlanConfig"}
    if not retired:
        return

    # 先保留完整原文件；备份失败就不改有效配置，重试也不覆盖已有备份。
    original = path.read_bytes()
    backup = config_path / "retired-baah-plans" / hashlib.sha256(original).hexdigest()
    target = backup / path.name
    if not target.exists():
        _utils_io.atomic_write(target, original)
    document["order"] = [item for item in order if item["uid"] not in retired]
    for uid in retired:
        document["data"].pop(uid, None)
    _utils_io.write_file(path, document)


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
            # 旧 JSON 会由升级管道完整归档；不再导入重复的 BAAH 计划。
            if item["type"] == "BAAHPlanConfig":
                continue
            uid = str(UUID(item["uid"]))
            type_name = LEGACY_ENTRY_TYPE_NAMES.get(item["type"], item["type"])
            entry_type = node._entry_types.get(type_name)
            if entry_type is None:
                raise ValueError(f"尚未迁移的配置类型：{item['type']}")
            if uid in data or not isinstance(document.get(uid), dict):
                raise ValueError("旧集合成员缺失或身份重复")
            order.append({"uid": uid, "type": type_name})
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


def migrate_sign_flow_documents(config_path: Path) -> None:
    """把改名前的活跃文档搬到新名下，供已升级到 v2.2 的用户直接启动。

    改名只影响文档名与集合成员类型标签两类内容：旧 YAML 的 ``order[].type``
    仍是 ``GameSignAccountGroup``，不搬会被当成不认识的成员类型而整根激活
    失败（账号 YAML 没开 ``keep_unknown_types``）。成员内层键
    ``GameSignAccount`` 由 ``SignFlowAccountGroup.normalize_payload`` 负责，
    这里不动，避免同一份改名规则写两处。

    幂等：只在新名不存在时搬，新名已在用说明这一轮已经搬过（或用户手建），
    旧名留着不影响加载，不再覆盖。
    """

    for old_name, new_name in LEGACY_SIGN_FLOW_DOCUMENTS:
        source = config_path / old_name
        target = config_path / new_name
        if not source.is_file() or target.exists():
            continue
        if old_name.endswith(".yaml"):
            document = _utils_io.read_dict_file(source, allow_empty=True)
            order = document.get("order")
            if isinstance(order, list):
                for item in order:
                    if not isinstance(item, dict):
                        continue
                    type_name = item.get("type")
                    if isinstance(type_name, str):
                        item["type"] = LEGACY_ENTRY_TYPE_NAMES.get(type_name, type_name)
            _utils_io.write_file(target, document, format=".yaml")
        else:
            shutil.copy2(source, target)
        backup_dir = config_path / "legacy-json"
        backup_dir.mkdir(exist_ok=True)
        archived = backup_dir / old_name
        if archived.exists():
            source.unlink()
        else:
            source.replace(archived)


def preserve_pre_upgrade(
    config_path: Path, *, database_path: Path | None = None
) -> None:
    """按配置白名单及 SQLite 一致性快照留存升级原件，重试不覆盖首次备份。"""
    backup = config_path / "legacy-json" / "pre-upgrade"
    backup.mkdir(parents=True, exist_ok=True)
    # 新旧聚合配置及早期升级涉及的 JSON；按固定范围保留相对路径，不复制历史备份。
    for pattern in (
        *(old for old, _new, _key in CONFIG_FILES),
        *(new for _old, new, _key in CONFIG_FILES),
        "plugins/*.yaml",
        "plugin_registry.yaml",
        "plugin_catalog.yaml",
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
    if database_path is not None and database_path.is_file():
        target = backup / database_path.name
        if not target.exists():
            temporary = target.with_suffix(target.suffix + ".tmp")
            temporary.unlink(missing_ok=True)
            with (
                closing(sqlite3.connect(database_path)) as source_db,
                closing(sqlite3.connect(temporary)) as target_db,
            ):
                source_db.backup(target_db)
            temporary.replace(target)


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
    if record.get("complete") and all(
        record.get("files", {}).get(old, {}).get("state") == "complete"
        and (config_path / old).is_file()
        for old, _new, _key in CONFIG_FILES
    ):
        # 调用方只在旧数据库版本进入迁移；整套 JSON 再现时以当前旧版配置为准。
        # 先检查来源并登记重迁，逐文件准备好替代结果后再覆盖，不生成 YAML 备份。
        for old, _new, _key in CONFIG_FILES:
            source = config_path / old
            if not is_blank_file(source):
                _utils_io.read_dict_file(source)
        record = {"version": 2, "files": {}, "reset_targets": True}
        _utils_io.write_file(record_path, record)
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
        # 旧 ToolsConfig.json 的内嵌账号键也随改名换了写法；先读新键，
        # 回落到旧键，避免已经手工改过键名的用户丢掉账号。
        sub_configs = tools.get("SubConfigsInfo", {})
        embedded_accounts = sub_configs.get("SignFlow_Accounts") or sub_configs.get(
            "GameSign_Accounts", {}
        )

    for old_name, new_name, key in CONFIG_FILES:
        source = config_path / old_name
        target = config_path / new_name
        archived = backup_dir / old_name
        progress = files.get(old_name)
        if progress and not target.exists():
            # 改名会波及目标文件名（GameSignAccounts.json → game_sign_accounts.yaml）。
            # 旧版续跑可能把内容写进改名前的名字，进度却记新名。核对时按「进度
            # 里记的名字 → 改名前的名字」找实际文件：内容已写好就按它结账，需要
            # 重写就照新名重写，写出的文件与进度记的名字始终同一个。改名与成员类型
            # 标签归一化仍留给 migrate_sign_flow_documents。
            for name in (progress.get("target"), LEGACY_DOCUMENT_NAMES.get(new_name)):
                if not name or name == new_name:
                    continue
                candidate = config_path / str(name)
                if not candidate.is_file():
                    continue
                # 只在「已写好、可直接结账」时认旧名；需要重写就留在新名上，
                # 让写出的文件与进度记的名字同为 new_name。
                if (
                    progress["state"] == "complete"
                    or _digest(candidate) == progress["target_sha256"]
                ):
                    target = candidate
                break
        reset_target = record.get("reset_targets") and (
            not progress or (progress["state"] == "prepared" and source.is_file())
        )
        if reset_target:
            if not source.is_file():
                raise ValueError(f"重新迁移的原配置缺失：{old_name}")
            if progress and _digest(source) != progress["source_sha256"]:
                raise ValueError(f"迁移期间原配置发生变化：{old_name}")
        elif progress:
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
                # 结账同时把进度里的目标名对齐到磁盘上的实际文件名，
                # 避免续跑回落到旧名后进度仍写着新名。
                progress["target"] = target.name
                progress["state"] = "complete"
                _utils_io.write_file(record_path, record)
                continue
            if target.exists():
                raise ValueError(f"迁移目标发生变化，已保留现有文件：{target.name}")
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
        elif key == "SignFlowAccounts" and embedded_accounts:
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
            raise ValueError(f"迁移文件校验失败：{target.name}")
        files[old_name] = {
            # 进度记内容实际写入的名字：续跑回落到旧目标时也照旧名记，
            # 否则下次启动会按新名查摘要，把写好的内容判成缺失。
            "target": target.name,
            "source_sha256": _digest(source) if source.exists() else None,
            "target_sha256": _digest(temporary),
            "state": "prepared",
        }
        _utils_io.write_file(record_path, record)
        if reset_target:
            archived.unlink(missing_ok=True)
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
    record.pop("reset_targets", None)
    record["complete"] = True
    _utils_io.write_file(record_path, record)
