"""v1.8 -> v1.9 directory-layout migration without legacy Config.

Re-implements ``AppConfig.check_data`` 的 v1.8→v1.9 步骤（app/core/config.py
317-514 行）为纯文件变换：把 ``config/MaaPlanConfig``、``config/MaaConfig``、
``config/GeneralConfig`` 目录与 ``config/QueueConfig/*.json`` 合并为
``PlanConfig.json`` / ``ScriptConfig.json`` / ``QueueConfig.json`` 三个
MultipleConfig 根，并复制 gui/基建/配置文件到 ``data/<uid>/...``。

与 legacy 实现的关键差异（有意为之，见 PROGRESS.md）：

* 不构造 legacy ``AppConfig``/``MultipleConfig`` 对象，直接按序列化契约
  （``{"instances": [{uid, type}], "<uid>": {...}}``，嵌套走
  ``SubConfigsInfo.{UserData,TimeSet,QueueItem}``）产出 JSON。
* 产物随后被冻结进不可变快照并直接由 Config v2 的 legacy 导入链消费，而
  v2 端对未知字段/非法枚举/坏路径 fail-closed——因此本模块采用**白名单字段
  映射 + 主动纠正**（枚举、日期、路径存在性、用户名），legacy validator 的
  auto-correct 帮不上忙。
* 加密字段（Password/SklandToken/ServerChanKey）一律置空或省略，与 legacy
  迁移的 ``Password = ""`` 行为一致；v2 拒绝非 DPAPI 密文的非空值。
* 用户 ``Task`` 组同时接受 v1.10 旧键名（IfWakeUp/IfBase/IfCombat/...）与
  新键名，统一产出新键名——legacy 的 v1.10→v1.11 重命名从未真正写盘
  （str.replace 未赋值），旧档案里两种键名都可能出现。
"""

from __future__ import annotations

import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

_WINDOWS_ILLEGAL_NAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

AFTER_ACCOMPLISH_ACTIONS = (
    "NoAction",
    "Shutdown",
    "ShutdownForce",
    "Reboot",
    "Hibernate",
    "Sleep",
    "KillSelf",
    "Logoff",
)
# 旧版中文动作 -> v2 英文枚举；无法确认的旧值省略字段（回落默认 NoAction）。
_AFTER_ACCOMPLISH_ALIASES = {
    "无动作": "NoAction",
    "关机": "Shutdown",
    "强制关机": "ShutdownForce",
    "重启": "Reboot",
    "休眠": "Hibernate",
    "睡眠": "Sleep",
    "退出软件": "KillSelf",
    "注销": "Logoff",
}

# v1.10 遗留任务键名 -> v1.11 键名（legacy 重命名从未写盘，两种都可能出现）。
_TASK_FIELD_ALIASES = {
    "IfWakeUp": "IfStartUp",
    "IfStartUp": "IfStartUp",
    "IfCombat": "IfFight",
    "IfFight": "IfFight",
    "IfBase": "IfInfrast",
    "IfInfrast": "IfInfrast",
    "IfRecruiting": "IfRecruit",
    "IfRecruit": "IfRecruit",
    "IfMall": "IfMall",
    "IfMission": "IfAward",
    "IfAward": "IfAward",
    "IfAutoRoguelike": "IfRoguelike",
    "IfRoguelike": "IfRoguelike",
    "IfReclamation": "IfReclamation",
}

_PLAN_GROUP_FIELDS = (
    "MedicineNumb",
    "SeriesNumb",
    "Stage",
    "Stage_1",
    "Stage_2",
    "Stage_3",
    "Stage_Remain",
)
_WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


def _sanitize_name(value: Any, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    cleaned = _WINDOWS_ILLEGAL_NAME_CHARS.sub("", value).strip().rstrip(".")
    if not cleaned or cleaned.upper() in _RESERVED_NAMES or len(cleaned) > 255:
        return fallback
    return cleaned


def _system_root() -> Path | None:
    import os

    system_root = os.environ.get("SystemRoot")
    return Path(system_root) if system_root else None


def _safe_existing_dir(value: Any, *, allow_cwd: bool = False) -> str:
    """路径必须是当前存在的绝对目录且不在 SystemRoot/cwd 之下，否则置空。"""

    if not isinstance(value, str) or not value.strip():
        return ""
    try:
        path = Path(value)
        if not path.is_absolute() or not path.is_dir():
            return ""
        resolved = path.resolve()
        system_root = _system_root()
        if system_root is not None and resolved.is_relative_to(system_root):
            return ""
        if not allow_cwd:
            cwd = Path.cwd().resolve()
            if resolved == cwd or resolved.is_relative_to(cwd):
                return ""
    except OSError:
        return ""
    return value


def _safe_abs_path(value: Any) -> str:
    """文件类路径：绝对、非 .lnk、不在 SystemRoot 下即可（不要求存在）。"""

    if not isinstance(value, str) or not value.strip():
        return ""
    try:
        path = Path(value)
        if not path.is_absolute() or path.suffix.lower() == ".lnk":
            return ""
        system_root = _system_root()
        if system_root is not None and path.resolve().is_relative_to(system_root):
            return ""
    except OSError:
        return ""
    return value


def _put_str(target: dict, source: dict, name: str, *, source_name: str | None = None) -> None:
    value = source.get(source_name or name)
    if isinstance(value, str):
        target[name] = value


def _put_bool(target: dict, source: dict, name: str, *, source_name: str | None = None) -> None:
    value = source.get(source_name or name)
    if isinstance(value, bool):
        target[name] = value


def _put_int(target: dict, source: dict, name: str) -> None:
    value = source.get(name)
    if isinstance(value, bool):
        return
    if isinstance(value, int):
        target[name] = value


def _put_enum(target: dict, source: dict, name: str, options: tuple[str, ...]) -> None:
    value = source.get(name)
    if isinstance(value, str) and value in options:
        target[name] = value


def _put_date(target: dict, source: dict, name: str) -> None:
    value = source.get(name)
    if isinstance(value, str) and _DATE_PATTERN.match(value):
        target[name] = value


def _new_uid() -> str:
    return str(uuid.uuid4())


def _load_json_dict(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _write_root(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=4),
        encoding="utf-8",
    )


def _load_or_new_root(path: Path) -> dict[str, Any]:
    if path.exists():
        existing = _load_json_dict(path)
        if existing is not None and isinstance(existing.get("instances"), list):
            return existing
    return {"instances": []}


def _append_instance(root: dict[str, Any], uid: str, type_name: str, payload: dict) -> None:
    root["instances"].append({"uid": uid, "type": type_name})
    root[uid] = payload


# ---------------------------------------------------------------------------
# 各实体映射
# ---------------------------------------------------------------------------


def _map_plan(raw: dict[str, Any], fallback_name: str) -> dict[str, Any]:
    info_source = raw.get("Info") if isinstance(raw.get("Info"), dict) else {}
    info: dict[str, Any] = {
        "Name": _sanitize_name(info_source.get("Name"), fallback_name),
    }
    _put_enum(info, info_source, "Mode", ("ALL", "Weekly"))
    entry: dict[str, Any] = {"Info": info}

    for group_name in ("ALL", *_WEEKDAYS):
        group_source = raw.get(group_name)
        if not isinstance(group_source, dict):
            continue
        group: dict[str, Any] = {}
        _put_int(group, group_source, "MedicineNumb")
        for field in _PLAN_GROUP_FIELDS[1:]:
            _put_str(group, group_source, field)
        if group:
            entry[group_name] = group
    return entry


def _map_maa_script(raw: dict[str, Any], fallback_name: str) -> dict[str, Any]:
    # legacy 迁移把 MaaSet 赋给 Info、RunSet 赋给 Run；两种键名都接受。
    info_source = raw.get("MaaSet") or raw.get("Info") or {}
    run_source = raw.get("RunSet") or raw.get("Run") or {}
    if not isinstance(info_source, dict):
        info_source = {}
    if not isinstance(run_source, dict):
        run_source = {}

    info: dict[str, Any] = {
        "Name": _sanitize_name(info_source.get("Name"), fallback_name),
        "Path": _safe_existing_dir(info_source.get("Path")),
    }
    run: dict[str, Any] = {}
    for field in (
        "ProxyTimesLimit",
        "RunTimesLimit",
        "AnnihilationTimeLimit",
        "RoutineTimeLimit",
    ):
        _put_int(run, run_source, field)
    _put_bool(run, run_source, "AnnihilationAvoidWaste")

    entry: dict[str, Any] = {"Info": info}
    if run:
        entry["Run"] = run
    return entry


def _map_maa_user(
    raw: dict[str, Any],
    fallback_name: str,
    plan_uid_by_name: dict[str, str],
) -> dict[str, Any]:
    info_source = raw.get("Info") if isinstance(raw.get("Info"), dict) else {}
    data_source = raw.get("Data") if isinstance(raw.get("Data"), dict) else {}
    task_source = raw.get("Task") if isinstance(raw.get("Task"), dict) else {}

    info: dict[str, Any] = {
        "Name": _sanitize_name(info_source.get("Name"), fallback_name),
        # legacy 迁移显式清空密码（core/config.py:389）；v2 拒绝非密文非空值。
        "Password": "",
        "StageMode": plan_uid_by_name.get(
            str(info_source.get("StageMode", "")), "Fixed"
        ),
    }
    _put_str(info, info_source, "Id")
    _put_str(info, info_source, "Notes")
    _put_enum(info, info_source, "Mode", ("简洁", "详细"))
    _put_enum(info, info_source, "Server", ("Official", "Bilibili"))
    _put_bool(info, info_source, "Status")
    _put_int(info, info_source, "RemainedDay")
    _put_int(info, info_source, "MedicineNumb")
    _put_str(info, info_source, "SeriesNumb")
    for field in ("Stage", "Stage_1", "Stage_2", "Stage_3", "Stage_Remain"):
        _put_str(info, info_source, field)
    _put_bool(info, info_source, "IfScriptBeforeTask")
    _put_str(info, info_source, "ScriptBeforeTask")
    _put_bool(info, info_source, "IfScriptAfterTask")
    _put_str(info, info_source, "ScriptAfterTask")
    _put_bool(info, info_source, "IfSkland")

    data: dict[str, Any] = {}
    _put_date(data, data_source, "LastProxyDate")
    _put_int(data, data_source, "ProxyTimes")
    _put_bool(data, data_source, "IfPassCheck")
    _put_str(data, data_source, "InfrastIndex")

    task: dict[str, Any] = {}
    for old_name, new_name in _TASK_FIELD_ALIASES.items():
        value = task_source.get(old_name)
        if isinstance(value, bool) and new_name not in task:
            task[new_name] = value

    entry: dict[str, Any] = {"Info": info}
    if data:
        entry["Data"] = data
    if task:
        entry["Task"] = task
    return entry


def _map_general_script(raw: dict[str, Any], fallback_name: str) -> dict[str, Any]:
    script_source = raw.get("Script") if isinstance(raw.get("Script"), dict) else {}

    info: dict[str, Any] = {
        "Name": _sanitize_name(script_source.get("Name"), fallback_name),
        "RootPath": _safe_existing_dir(
            script_source.get("RootPath"), allow_cwd=True
        ),
    }

    script: dict[str, Any] = {}
    config_path_mode = script_source.get("ConfigPathMode")
    if isinstance(config_path_mode, str):
        # legacy 迁移逻辑：含「所有文件」→ File，否则 Folder。
        script["ConfigPathMode"] = (
            "File" if "所有文件" in config_path_mode else "Folder"
        )
    for field in ("ScriptPath", "ConfigPath", "LogPath"):
        value = _safe_abs_path(script_source.get(field))
        if value:
            script[field] = value
    _put_str(script, script_source, "Arguments")
    _put_str(script, script_source, "LogPathFormat")
    _put_str(script, script_source, "LogTimeFormat")
    _put_int(script, script_source, "LogTimeStart")
    _put_int(script, script_source, "LogTimeEnd")
    _put_str(script, script_source, "SuccessLog")
    _put_str(script, script_source, "ErrorLog")
    _put_bool(script, script_source, "IfTrackProcess")
    _put_str(script, script_source, "TrackProcessName")
    _put_str(script, script_source, "TrackProcessExe")
    _put_str(script, script_source, "TrackProcessCmdline")

    entry: dict[str, Any] = {"Info": info}
    if script:
        entry["Script"] = script
    return entry


def _map_general_user(raw: dict[str, Any], fallback_name: str) -> dict[str, Any]:
    info_source = raw.get("Info") if isinstance(raw.get("Info"), dict) else {}
    data_source = raw.get("Data") if isinstance(raw.get("Data"), dict) else {}

    info: dict[str, Any] = {
        "Name": _sanitize_name(info_source.get("Name"), fallback_name),
    }
    _put_bool(info, info_source, "Status")
    _put_int(info, info_source, "RemainedDay")
    _put_str(info, info_source, "Notes")
    _put_bool(info, info_source, "IfScriptBeforeTask")
    _put_str(info, info_source, "ScriptBeforeTask")
    _put_bool(info, info_source, "IfScriptAfterTask")
    _put_str(info, info_source, "ScriptAfterTask")

    data: dict[str, Any] = {}
    _put_date(data, data_source, "LastProxyDate")
    _put_int(data, data_source, "ProxyTimes")

    entry: dict[str, Any] = {"Info": info}
    if data:
        entry["Data"] = data
    return entry


def _map_queue(
    raw: dict[str, Any],
    fallback_name: str,
    script_uid_by_name: dict[str, str],
) -> dict[str, Any]:
    # v1.7→v1.8 步骤已把 Enabled 别名为 TimeEnabled、Member_i 别名为 Script_i。
    info_source = raw.get("QueueSet") or raw.get("Info") or {}
    queue_source = raw.get("Queue") if isinstance(raw.get("Queue"), dict) else {}
    time_source = raw.get("Time") if isinstance(raw.get("Time"), dict) else {}
    if not isinstance(info_source, dict):
        info_source = {}

    info: dict[str, Any] = {
        "Name": _sanitize_name(info_source.get("Name"), fallback_name),
    }
    _put_bool(info, info_source, "TimeEnabled")
    after = info_source.get("AfterAccomplish")
    if isinstance(after, str):
        mapped = (
            after
            if after in AFTER_ACCOMPLISH_ACTIONS
            else _AFTER_ACCOMPLISH_ALIASES.get(after)
        )
        if mapped is not None:
            info["AfterAccomplish"] = mapped

    time_sets: dict[str, Any] = {"instances": []}
    queue_items: dict[str, Any] = {"instances": []}
    for i in range(10):
        enabled = time_source.get(f"Enabled_{i}")
        time_value = time_source.get(f"Set_{i}")
        time_info: dict[str, Any] = {
            "Enabled": enabled if isinstance(enabled, bool) else False,
        }
        if isinstance(time_value, str) and _TIME_PATTERN.match(time_value):
            time_info["Time"] = time_value
        time_uid = _new_uid()
        time_sets["instances"].append({"uid": time_uid, "type": "TimeSet"})
        time_sets[time_uid] = {"Info": time_info}

        script_name = queue_source.get(f"Script_{i}")
        item_uid = _new_uid()
        queue_items["instances"].append({"uid": item_uid, "type": "QueueItem"})
        queue_items[item_uid] = {
            "Info": {
                "ScriptId": script_uid_by_name.get(str(script_name), "-"),
            }
        }

    return {
        "Info": info,
        "SubConfigsInfo": {
            "TimeSet": time_sets,
            "QueueItem": queue_items,
        },
    }


# ---------------------------------------------------------------------------
# 目录迁移主流程
# ---------------------------------------------------------------------------


def _copy_if_exists(source: Path, target: Path) -> None:
    if source.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(source, target)


def _iter_config_dirs(base: Path) -> list[Path]:
    if not base.exists():
        return []
    return sorted(
        (entry for entry in base.iterdir() if entry.is_dir()),
        key=lambda entry: entry.name,
    )


def migrate_v1_8_directories(base_dir: Path) -> None:
    """把 v1.8 目录布局迁移为 v1.9 合并 JSON 根（幂等，见模块文档）。"""

    base_dir = Path(base_dir)
    config_dir = base_dir / "config"
    data_dir = base_dir / "data"

    # config.json -> Config.json。Windows 文件系统大小写不敏感,
    # Path.exists() 无法区分两个名字,必须按目录项的真实大小写判断。
    if config_dir.exists():
        real_names = {entry.name for entry in config_dir.iterdir()}
        if "config.json" in real_names and "Config.json" not in real_names:
            (config_dir / "config.json").rename(config_dir / "Config.json")

    # ---- 计划 ----
    plan_root = _load_or_new_root(config_dir / "PlanConfig.json")
    plan_uid_by_name: dict[str, str] = {"固定": "Fixed"}
    for plan_dir in _iter_config_dirs(config_dir / "MaaPlanConfig"):
        raw = _load_json_dict(plan_dir / "config.json")
        if raw is None:
            continue
        uid = _new_uid()
        plan_uid_by_name[plan_dir.name] = uid
        _append_instance(
            plan_root, uid, "MaaPlanConfig", _map_plan(raw, plan_dir.name)
        )

    # ---- 脚本 ----
    script_root = _load_or_new_root(config_dir / "ScriptConfig.json")
    script_uid_by_name: dict[str, str] = {}

    for maa_dir in _iter_config_dirs(config_dir / "MaaConfig"):
        raw = _load_json_dict(maa_dir / "config.json")
        if raw is None:
            continue
        uid = _new_uid()
        script_uid_by_name[maa_dir.name] = uid
        entry = _map_maa_script(raw, maa_dir.name)

        _copy_if_exists(
            maa_dir / "Default/gui.json",
            data_dir / uid / "Default/ConfigFile/gui.json",
        )

        users: dict[str, Any] = {"instances": []}
        user_data_dir = maa_dir / "UserData"
        for user_dir in _iter_config_dirs(user_data_dir):
            user_raw = _load_json_dict(user_dir / "config.json")
            if user_raw is None:
                continue
            user_uid = _new_uid()
            users["instances"].append(
                {"uid": user_uid, "type": "MaaUserConfig"}
            )
            users[user_uid] = _map_maa_user(
                user_raw, user_dir.name, plan_uid_by_name
            )
            _copy_if_exists(
                user_dir / "Routine/gui.json",
                data_dir / uid / user_uid / "ConfigFile/gui.json",
            )
            _copy_if_exists(
                user_dir / "Infrastructure/infrastructure.json",
                data_dir / uid / user_uid / "Infrastructure/infrastructure.json",
            )
        if users["instances"]:
            entry["SubConfigsInfo"] = {"UserData": users}
        _append_instance(script_root, uid, "MaaConfig", entry)

    for general_dir in _iter_config_dirs(config_dir / "GeneralConfig"):
        raw = _load_json_dict(general_dir / "config.json")
        if raw is None:
            continue
        uid = _new_uid()
        script_uid_by_name[general_dir.name] = uid
        entry = _map_general_script(raw, general_dir.name)

        users = {"instances": []}
        for user_dir in _iter_config_dirs(general_dir / "SubData"):
            user_raw = _load_json_dict(user_dir / "config.json")
            if user_raw is None:
                continue
            user_uid = _new_uid()
            users["instances"].append(
                {"uid": user_uid, "type": "GeneralUserConfig"}
            )
            users[user_uid] = _map_general_user(user_raw, user_dir.name)
            config_files = user_dir / "ConfigFiles"
            if config_files.exists():
                target = data_dir / uid / user_uid / "ConfigFile"
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    shutil.move(str(config_files), str(target))
        if users["instances"]:
            entry["SubConfigsInfo"] = {"UserData": users}
        _append_instance(script_root, uid, "GeneralConfig", entry)

    # ---- 队列 ----
    queue_root = _load_or_new_root(config_dir / "QueueConfig.json")
    queue_config_dir = config_dir / "QueueConfig"
    if queue_config_dir.exists():
        for queue_path in sorted(queue_config_dir.glob("*.json")):
            raw = _load_json_dict(queue_path)
            if raw is None:
                continue
            uid = _new_uid()
            _append_instance(
                queue_root,
                uid,
                "QueueConfig",
                _map_queue(raw, queue_path.stem, script_uid_by_name),
            )

    # ---- 先落三个根，再清理旧目录（崩溃时可重跑，见 legacy_data_upgrade）----
    _write_root(config_dir / "PlanConfig.json", plan_root)
    _write_root(config_dir / "ScriptConfig.json", script_root)
    _write_root(config_dir / "QueueConfig.json", queue_root)

    for stale in ("QueueConfig", "MaaPlanConfig", "MaaConfig", "GeneralConfig"):
        stale_dir = config_dir / stale
        if stale_dir.exists():
            shutil.rmtree(stale_dir)
    if (data_dir / "gameid.txt").exists():
        (data_dir / "gameid.txt").unlink()
    if (data_dir / "key").exists():
        shutil.rmtree(data_dir / "key")
