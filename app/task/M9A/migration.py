#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""旧版 M9A 专项配置 → MaaFW 形状，一次性、在 ``ScriptConfig.connect()`` 之前改原始 JSON。

必须在加载前做：``ConfigBase.load`` 只认类里声明的条目，旧键（``Run.IfPsychubeDailyOnce``、
``Task.Queue``、``Data.LastPsychubeDate``…）在按新类加载的那一刻就会被丢弃并写回盘，
之后再想迁就没有原料了。

一趟做两件事：

1. ``type == "M9AConfig"`` 且带旧形状键的脚本 → 按 §3 / §4 逐字段翻译成 MaaFW 形状
   （类型标签不变，用户标签不变，只有数据变）；
2. ``type == "MaaFWConfig"`` 的脚本若项目被识别为 M9A（``flavor.is_m9a_project``）→ 只把
   ``instances[].type`` 换成 ``M9AConfig`` / ``M9AUserConfig``，数据一个字段不动（两类同形）。

幂等：迁完旧键消失、类型标签换完，再跑一遍什么都不会发生。改写前把整个文件复制成
``ScriptConfig.json.m9a-legacy-<时间戳>.bak``，只留最近三份。所有不可无损的地方（丢弃的
选项、停用的用户、读不到 interface 的降级）都收进 ``MigrationReport``，由启动流程发通知。
"""

from __future__ import annotations

import json
import os
import shutil
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app.task.M9A.flavor import (
    CLOSE_ENTRY,
    FALLBACK_TASK_NAMES,
    LEGACY_ENTRY_ALIASES,
    STARTUP_ENTRY,
    SWITCH_ACCOUNT_ENTRY,
    is_m9a_project,
)
from app.utils import get_logger

logger = get_logger("M9A 迁移")

LEGACY_BACKUP_SUFFIX = ".m9a-legacy-"
LEGACY_BACKUP_KEEP = 3
# 旧 Run.RunTimeLimit 是「日志停滞」阈值（默认 10 分钟），MaaFW 的是整轮硬超时；照抄会把
# 整轮跑 10 分钟就杀掉，固定成 MaaFW 的默认。
MAAFW_RUN_TIME_LIMIT = 120
# 运行期由特调补上、迁移时从队列里剔掉的三个任务（按 entry 判）。
_RUNTIME_MANAGED_ENTRIES = {STARTUP_ENTRY, CLOSE_ENTRY, SWITCH_ACCOUNT_ENTRY}
_LEGACY_SCRIPT_KEYS = (
    "IfPsychubeDailyOnce",
    "IfSleepDreamMonthlyOnce",
    "IfAutoUpdateAfterQueue",
)
_DUPLICATE_SUFFIX = "__MAS_DUP__"


@dataclass
class MigrationReport:
    """一趟迁移的结果，给启动通知与日志用。"""

    migrated_scripts: list[str] = field(default_factory=list)
    migrated_uids: list[str] = field(default_factory=list)
    retyped_scripts: list[str] = field(default_factory=list)
    disabled_users: list[str] = field(default_factory=list)
    dropped_tasks: list[str] = field(default_factory=list)
    dropped_options: list[str] = field(default_factory=list)
    degraded_scripts: list[str] = field(default_factory=list)
    backup_path: Path | None = None
    #: 迁移函数自己抛了异常：原文件已另存，后续 connect() 会按新类加载。
    failure: str = ""

    @property
    def changed(self) -> bool:
        return bool(self.migrated_scripts or self.retyped_scripts)

    def summary_lines(self) -> list[str]:
        lines: list[str] = []
        if self.migrated_scripts:
            lines.append(f"已迁移 M9A 脚本：{'、'.join(self.migrated_scripts)}")
        if self.retyped_scripts:
            lines.append(
                f"已识别为 M9A 项目并切换为 M9A 专项：{'、'.join(self.retyped_scripts)}"
                "——这些脚本官服用户的「账号」会用于自动切换账号，如果原来只是备注请清空"
            )
        if self.degraded_scripts:
            lines.append(
                "读不到项目 interface、按内置别名迁移（任务选项已丢弃）："
                + "、".join(self.degraded_scripts)
            )
        if self.disabled_users:
            lines.append(
                "服务器与脚本资源不一致、已停用的用户："
                + "、".join(self.disabled_users)
            )
        if self.dropped_tasks:
            lines.append("找不到对应任务、已丢弃：" + "、".join(self.dropped_tasks))
        if self.dropped_options:
            lines.append("找不到对应选项、已丢弃：" + "、".join(self.dropped_options))
        return lines


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def migrate_legacy_m9a_scripts(
    script_config_path: Path,
    *,
    global_mirror_cdk: str = "",
    now: datetime | None = None,
) -> MigrationReport:
    """启动期入口：读文件、判定、改写、备份。任何异常都只记日志，不阻断启动。"""

    report = MigrationReport()
    path = Path(script_config_path)
    if not path.is_file():
        return report
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text) if text.strip() else {}
    except (OSError, ValueError) as exc:
        logger.warning(f"M9A 迁移跳过：ScriptConfig.json 读取失败：{exc}")
        return report
    if not isinstance(data, dict):
        return report

    try:
        changed = migrate_script_config_payload(
            data, report, global_mirror_cdk=global_mirror_cdk
        )
    except Exception as exc:  # noqa: BLE001 - 迁移炸了也要让程序起来
        # 「配置未改动」只保得住这一刻：紧接着 ScriptConfig.connect() 会按新类加载，
        # 旧键当场丢掉。所以失败也要先把原文件另存一份，并把失败带进启动通知。
        logger.opt(exception=True).warning(f"M9A 迁移失败：{exc}")
        # 文件没写回：出错前记下的「已迁移 / 已换类型 / 已停用」都没落盘，一条也不能报。
        report = MigrationReport(failure=f"{type(exc).__name__}: {exc}")
        stamp = (now or datetime.now()).strftime("%Y%m%d%H%M%S")
        failed_backup = path.with_name(
            f"{path.name}{LEGACY_BACKUP_SUFFIX}failed-{stamp}.bak"
        )
        try:
            shutil.copyfile(path, failed_backup)
            report.backup_path = failed_backup
        except OSError as copy_exc:
            logger.warning(f"M9A 迁移失败后的原文件备份也失败了：{copy_exc}")
        return report
    if not changed:
        return report

    stamp = (now or datetime.now()).strftime("%Y%m%d%H%M%S")
    backup = path.with_name(f"{path.name}{LEGACY_BACKUP_SUFFIX}{stamp}.bak")
    try:
        shutil.copyfile(path, backup)
        report.backup_path = backup
        _prune_backups(path)
        tmp = path.with_name(f"{path.name}.m9a-migrating")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        logger.opt(exception=True).warning(f"M9A 迁移写回失败，配置未改动：{exc}")
        return MigrationReport()
    for line in report.summary_lines():
        logger.info(f"M9A 迁移：{line}")
    return report


def _prune_backups(path: Path) -> None:
    backups = sorted(
        path.parent.glob(f"{path.name}{LEGACY_BACKUP_SUFFIX}*.bak"),
        key=lambda item: item.name,
    )
    for stale in backups[:-LEGACY_BACKUP_KEEP]:
        try:
            stale.unlink()
        except OSError:
            pass


def migrate_script_config_payload(
    data: dict[str, Any],
    report: MigrationReport,
    *,
    global_mirror_cdk: str = "",
) -> bool:
    """对整份 ``ScriptConfig.json`` 字典就地迁移；返回有没有改动。纯逻辑，方便单测。"""

    instances = data.get("instances")
    if not isinstance(instances, list):
        return False
    changed = False
    for instance in instances:
        if not isinstance(instance, dict):
            continue
        uid = str(instance.get("uid") or "")
        payload = data.get(uid)
        if not isinstance(payload, dict):
            continue
        type_name = str(instance.get("type") or "")
        if type_name == "M9AConfig" and _is_legacy_m9a_payload(payload):
            data[uid] = migrate_legacy_script(
                payload, report, global_mirror_cdk=global_mirror_cdk, script_uid=uid
            )
            _retag_users(data[uid], "M9AUserConfig")
            report.migrated_scripts.append(_script_label(payload, uid))
            report.migrated_uids.append(uid)
            changed = True
        elif type_name == "MaaFWConfig" and _project_is_m9a(payload, uid):
            instance["type"] = "M9AConfig"
            _retag_users(payload, "M9AUserConfig")
            report.retyped_scripts.append(_script_label(payload, uid))
            changed = True
    return changed


def _is_legacy_m9a_payload(payload: dict[str, Any]) -> bool:
    run = payload.get("Run")
    if isinstance(run, dict) and any(key in run for key in _LEGACY_SCRIPT_KEYS):
        return True
    for user in _iter_users(payload):
        task = user.get("Task")
        if isinstance(task, dict) and "Queue" in task:
            return True
    return False


def _project_is_m9a(payload: dict[str, Any], uid: str) -> bool:
    root = _project_root_for_detection(payload, uid)
    if root is None:
        return False
    interface = _read_interface_dict(root)
    return bool(interface) and is_m9a_project(interface)


def _project_root_for_detection(payload: dict[str, Any], uid: str) -> Path | None:
    """识别用的项目根：副本在就读副本（路径由脚本 ID 推出），否则读来源目录。"""

    candidates: list[Path] = []
    try:
        from app.task.MaaFW.tools.embedded.embedded_project import (
            embedded_project_dir,
        )

        candidates.append(embedded_project_dir(uid))
    except Exception:  # noqa: BLE001 - uid 不合法就只看来源目录
        pass
    info = payload.get("Info") or {}
    source = str(info.get("Path") or "").strip() if isinstance(info, dict) else ""
    if source:
        candidates.append(Path(source))
    for candidate in candidates:
        if (candidate / "interface.json").is_file():
            return candidate
    return None


def _script_label(payload: dict[str, Any], uid: str) -> str:
    info = payload.get("Info")
    name = str(info.get("Name") or "").strip() if isinstance(info, dict) else ""
    return name or uid[:8]


def _user_data_of(payload: dict[str, Any]) -> dict[str, Any] | None:
    """脚本数据块里的用户表：``ConfigBase.toDict`` 把子配置放在 ``SubConfigsInfo`` 下。"""

    sub = payload.get("SubConfigsInfo")
    user_data = sub.get("UserData") if isinstance(sub, dict) else None
    return user_data if isinstance(user_data, dict) else None


def _iter_users(payload: dict[str, Any]) -> list[dict[str, Any]]:
    user_data = _user_data_of(payload)
    if user_data is None or not isinstance(user_data.get("instances"), list):
        return []
    users: list[dict[str, Any]] = []
    for instance in user_data.get("instances") or []:
        if not isinstance(instance, dict):
            continue
        user = user_data.get(str(instance.get("uid") or ""))
        if isinstance(user, dict):
            users.append(user)
    return users


def _retag_users(payload: dict[str, Any], type_name: str) -> None:
    user_data = _user_data_of(payload)
    if user_data is None:
        return
    for instance in user_data.get("instances") or []:
        if isinstance(instance, dict):
            instance["type"] = type_name


# ---------------------------------------------------------------------------
# 旧 M9AConfig → MaaFW 形状
# ---------------------------------------------------------------------------


class _InterfaceIndex:
    """迁移要问 interface 的几件事：entry → 任务名、任务名集合、选项定义、资源名。"""

    def __init__(self, interface: dict[str, Any] | None) -> None:
        self.available = bool(interface)
        self.task_by_name: dict[str, dict[str, Any]] = {}
        self.name_by_entry: dict[str, str] = {}
        self.options: dict[str, dict[str, Any]] = {}
        self.resources: list[str] = []
        self.adb_controller: str = ""
        if not interface:
            return
        for task in interface.get("task") or []:
            if not isinstance(task, dict) or not task.get("name"):
                continue
            name = str(task["name"])
            self.task_by_name[name] = task
            entry = str(task.get("entry") or "")
            if entry and entry not in self.name_by_entry:
                self.name_by_entry[entry] = name
        options = interface.get("option")
        if isinstance(options, dict):
            self.options = {
                str(key): value
                for key, value in options.items()
                if isinstance(value, dict)
            }
        for resource in interface.get("resource") or []:
            if isinstance(resource, dict) and resource.get("name"):
                self.resources.append(str(resource["name"]))
        for controller in interface.get("controller") or []:
            if isinstance(controller, dict) and controller.get("type") == "Adb":
                self.adb_controller = str(controller.get("name") or "")
                break

    def task_name_for_entry(self, entry: str) -> str | None:
        if self.available:
            return self.name_by_entry.get(entry)
        return FALLBACK_TASK_NAMES.get(entry)

    def resolve_task_name(self, raw_name: str) -> str | None:
        """旧队列里的名字 → 现在的任务名；先按名字，再按旧别名反查 entry。"""

        name = str(raw_name or "").strip()
        if not name:
            return None
        if not self.available:
            entry = LEGACY_ENTRY_ALIASES.get(name)
            return FALLBACK_TASK_NAMES.get(entry, name) if entry else name
        if name in self.task_by_name:
            return name
        entry = LEGACY_ENTRY_ALIASES.get(name)
        if entry:
            return self.name_by_entry.get(entry)
        return None

    def entry_of(self, task_name: str) -> str:
        task = self.task_by_name.get(task_name)
        if task is not None:
            return str(task.get("entry") or "")
        return LEGACY_ENTRY_ALIASES.get(task_name, "")

    def match_resource(self, raw_name: str) -> str | None:
        name = str(raw_name or "").strip()
        if not name:
            return None
        if not self.available:
            return name
        if name in self.resources:
            return name
        squeezed = name.replace(" ", "")
        for candidate in self.resources:
            if candidate.replace(" ", "") == squeezed:
                return candidate
        return None


def migrate_legacy_script(
    payload: dict[str, Any],
    report: MigrationReport,
    *,
    global_mirror_cdk: str = "",
    script_uid: str = "",
) -> dict[str, Any]:
    """把一个旧 M9AConfig 数据块翻译成 MaaFW 形状（含全部用户）。"""

    info = payload.get("Info") if isinstance(payload.get("Info"), dict) else {}
    run = payload.get("Run") if isinstance(payload.get("Run"), dict) else {}
    emulator = (
        payload.get("Emulator") if isinstance(payload.get("Emulator"), dict) else {}
    )
    label = _script_label(payload, "")
    source_path = str(info.get("Path") or "").strip()
    interface = _read_interface_dict(Path(source_path)) if source_path else None
    index = _InterfaceIndex(interface)
    if not index.available:
        report.degraded_scripts.append(label or source_path or "未命名脚本")

    users = _iter_users(payload)
    resource_name = _choose_script_resource(users, index)

    daily_once: list[str] = []
    monthly_once: list[str] = []
    if _truthy(run.get("IfPsychubeDailyOnce")):
        name = index.task_name_for_entry("Psychube")
        if name:
            daily_once.append(name)
    if _truthy(run.get("IfSleepDreamMonthlyOnce")):
        for entry in ("Limbo", "Lucidscape"):
            name = index.task_name_for_entry(entry)
            if name:
                monthly_once.append(name)

    source, cdk = _seed_update_source(source_path, global_mirror_cdk)
    migrated: dict[str, Any] = {
        "Info": {
            "Name": str(info.get("Name") or "新 M9A 脚本"),
            "ProjectLabel": "",
            "Path": source_path,
            "Controller": index.adb_controller,
            "Resource": resource_name or "",
        },
        "Emulator": {
            "Id": str(emulator.get("Id") or "-"),
            "Index": str(emulator.get("Index") or "-"),
        },
        "Run": {
            "ProxyTimesLimit": _int(run.get("ProxyTimesLimit"), 0),
            "RunTimesLimit": _int(run.get("RunTimesLimit"), 3),
            "RunTimeLimit": MAAFW_RUN_TIME_LIMIT,
            "DailyOnceTasks": json.dumps(daily_once, ensure_ascii=False),
            "WeeklyOnceTasks": "[]",
            "MonthlyOnceTasks": json.dumps(monthly_once, ensure_ascii=False),
        },
        "Update": {
            "AutoUpdateMode": "AfterRun"
            if _truthy(run.get("IfAutoUpdateAfterQueue"))
            else "Off",
            "Source": source,
            "Channel": "stable",
            "MirrorChyanCDK": cdk,
        },
        "SubConfigsInfo": {
            "UserData": _migrate_users(
                payload, users, index, resource_name, label, script_uid, report
            )
        },
    }
    return migrated


def _choose_script_resource(users: list[dict[str, Any]], index: _InterfaceIndex) -> str:
    """启用用户里出现最多的服务器；没有启用用户取全部；并列取先出现的。"""

    def resource_of(user: dict[str, Any]) -> str:
        info = user.get("Info")
        return str(info.get("Resource") or "").strip() if isinstance(info, dict) else ""

    enabled = [u for u in users if _truthy((u.get("Info") or {}).get("Status", True))]
    pool = enabled or users
    counter: Counter[str] = Counter()
    order: list[str] = []
    for user in pool:
        name = resource_of(user)
        if not name:
            continue
        if name not in counter:
            order.append(name)
        counter[name] += 1
    if not counter:
        return ""
    best = max(counter.values())
    chosen = next(name for name in order if counter[name] == best)
    return index.match_resource(chosen) or chosen


def _migrate_users(
    payload: dict[str, Any],
    users: list[dict[str, Any]],
    index: _InterfaceIndex,
    script_resource: str,
    script_label: str,
    script_uid: str,
    report: MigrationReport,
) -> dict[str, Any]:
    user_data = _user_data_of(payload)
    if user_data is None:
        return {"instances": []}
    migrated: dict[str, Any] = {"instances": []}
    for instance in user_data.get("instances") or []:
        if not isinstance(instance, dict):
            continue
        uid = str(instance.get("uid") or "")
        user = user_data.get(uid)
        if not isinstance(user, dict):
            continue
        migrated["instances"].append({"uid": uid, "type": "M9AUserConfig"})
        migrated[uid] = _migrate_user(
            user, index, script_resource, script_label, payload, script_uid, uid, report
        )
    return migrated


def _migrate_user(
    user: dict[str, Any],
    index: _InterfaceIndex,
    script_resource: str,
    script_label: str,
    script_payload: dict[str, Any],
    script_uid: str,
    user_uid: str,
    report: MigrationReport,
) -> dict[str, Any]:
    info = user.get("Info") if isinstance(user.get("Info"), dict) else {}
    data = user.get("Data") if isinstance(user.get("Data"), dict) else {}
    notify = user.get("Notify") if isinstance(user.get("Notify"), dict) else {}
    name = str(info.get("Name") or "新用户")
    status = _truthy(info.get("Status", True))
    notes = str(info.get("Notes") or "无")

    user_resource = index.match_resource(str(info.get("Resource") or ""))
    raw_resource = str(info.get("Resource") or "").strip()
    if (
        raw_resource
        and script_resource
        and (user_resource or raw_resource) != script_resource
    ):
        status = False
        notes = (
            f"[迁移] 原服务器「{raw_resource}」与脚本资源「{script_resource}」不一致，已停用；"
            f"请新建 M9A 脚本（资源选 {raw_resource}）后重建该用户。"
            + ("" if notes in ("", "无") else f" {notes}")
        )
        report.disabled_users.append(f"{script_label} / {name}")

    snapshot = _build_snapshot(
        user, index, script_payload, script_uid, user_uid, script_label, report
    )

    period_records = {
        "daily": {},
        "weekly": {},
        "monthly": {},
    }
    psychube = index.task_name_for_entry("Psychube")
    limbo = index.task_name_for_entry("Limbo")
    lucidscape = index.task_name_for_entry("Lucidscape")
    if psychube and data.get("LastPsychubeDate"):
        period_records["daily"][psychube] = str(data["LastPsychubeDate"])
    if limbo and data.get("LastLimboMonth"):
        period_records["monthly"][limbo] = str(data["LastLimboMonth"])
    if lucidscape and data.get("LastLucidscapeMonth"):
        period_records["monthly"][lucidscape] = str(data["LastLucidscapeMonth"])

    migrated: dict[str, Any] = {
        "Info": {
            "Name": name,
            "Status": status,
            "RemainedDay": _int(info.get("RemainedDay"), -1),
            "IfScriptBeforeTask": _truthy(info.get("IfScriptBeforeTask")),
            "ScriptBeforeTask": str(info.get("ScriptBeforeTask") or ""),
            "IfScriptAfterTask": _truthy(info.get("IfScriptAfterTask")),
            "ScriptAfterTask": str(info.get("ScriptAfterTask") or ""),
            "Notes": notes,
            "Tag": str(info.get("Tag") or "[ ]"),
            "Account": str(info.get("Account") or ""),
            "Password": "",
            "IfQuickConfig": True,
            "Controller": "",
            "Resource": "",
        },
        "Task": {
            "SelectedPreset": "",
            "TaskSnapshot": json.dumps(snapshot, ensure_ascii=False),
        },
        "Data": {
            "LastProxyDate": str(data.get("LastProxyDate") or "2000-01-01"),
            "ProxyTimes": _int(data.get("ProxyTimes"), 0),
            "IfPassCheck": True,
            "LastProxyStatus": "未知",
            "PeriodTaskRecords": json.dumps(period_records, ensure_ascii=False),
        },
        "Notify": {
            key: notify[key]
            for key in (
                "Enabled",
                "IfSendStatistic",
                "IfSendMail",
                "ToAddress",
                "IfServerChan",
                "ServerChanKey",
            )
            if key in notify
        },
    }
    # 自定义 Webhook 是用户下的子配置，两边同形，整块照搬。
    sub = user.get("SubConfigsInfo")
    if isinstance(sub, dict) and isinstance(sub.get("Notify_CustomWebhooks"), dict):
        migrated["SubConfigsInfo"] = {
            "Notify_CustomWebhooks": sub["Notify_CustomWebhooks"]
        }
    return migrated


# ---------------------------------------------------------------------------
# 队列 → 快照
# ---------------------------------------------------------------------------


def _build_snapshot(
    user: dict[str, Any],
    index: _InterfaceIndex,
    script_payload: dict[str, Any],
    script_uid: str,
    user_uid: str,
    script_label: str,
    report: MigrationReport,
) -> dict[str, Any]:
    items = _legacy_queue_items(user, script_payload, script_uid, user_uid, report)
    order: list[str] = []
    checked: dict[str, bool] = {}
    options: dict[str, Any] = {}
    seen: Counter[str] = Counter()
    user_label = (
        f"{script_label} / {str((user.get('Info') or {}).get('Name') or user_uid[:8])}"
    )
    for raw_name, raw_options in items:
        task_name = index.resolve_task_name(raw_name)
        if not task_name:
            report.dropped_tasks.append(f"{user_label}：{raw_name}")
            continue
        if index.entry_of(task_name) in _RUNTIME_MANAGED_ENTRIES:
            continue  # 首尾与切号由特调运行期补，旧队列里的是陈旧数据
        task = index.task_by_name.get(task_name) or {}
        groups = task.get("group") or []
        if isinstance(groups, str):
            groups = [groups]
        if any("standalone" in str(group) for group in groups):
            continue
        seen[task_name] += 1
        task_id = (
            task_name
            if seen[task_name] == 1
            else f"{task_name}{_DUPLICATE_SUFFIX}{seen[task_name] - 1}"
        )
        order.append(task_id)
        checked[task_id] = True
        if index.available and raw_options:
            translated = _translate_options(raw_options, index, user_label, report)
            if translated:
                options[task_id] = translated
        elif raw_options and not index.available:
            report.dropped_options.append(f"{user_label}：{task_name}（无 interface）")
    return {"taskOrder": order, "taskChecked": checked, "taskOptions": options}


def _legacy_queue_items(
    user: dict[str, Any],
    script_payload: dict[str, Any],
    script_uid: str,
    user_uid: str,
    report: MigrationReport,
) -> list[tuple[str, list[dict[str, Any]]]]:
    """旧用户的任务来源：快速配置关闭时是 MFAA 实例文件，否则是 ``Task.Queue``。"""

    info = user.get("Info") if isinstance(user.get("Info"), dict) else {}
    if not _truthy(info.get("IfQuickConfig", True)):
        instance_items = _instance_file_items(
            user, script_payload, script_uid, user_uid
        )
        if instance_items is not None:
            return instance_items
        report.dropped_options.append(
            f"{str(info.get('Name') or user_uid[:8])}：找不到 MFAA 实例文件，改用任务队列"
        )
    task = user.get("Task") if isinstance(user.get("Task"), dict) else {}
    raw = task.get("Queue")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw.strip() else []
        except ValueError:
            raw = []
    if not isinstance(raw, list):
        return []
    items: list[tuple[str, list[dict[str, Any]]]] = []
    for entry in raw:
        if isinstance(entry, str):
            items.append((entry, []))
        elif isinstance(entry, dict) and entry.get("name"):
            raw_options = entry.get("options")
            items.append(
                (
                    str(entry["name"]),
                    [o for o in raw_options if isinstance(o, dict)]
                    if isinstance(raw_options, list)
                    else [],
                )
            )
    return items


def _instance_file_items(
    user: dict[str, Any],
    script_payload: dict[str, Any],
    script_uid: str,
    user_uid: str,
) -> list[tuple[str, list[dict[str, Any]]]] | None:
    """旧「配置来源」三态对应的 MFAA 实例文件里 ``default_check`` 为真的任务。"""

    info = user.get("Info") if isinstance(user.get("Info"), dict) else {}
    mode = str(info.get("Mode") or "用户")
    source_path = str((script_payload.get("Info") or {}).get("Path") or "").strip()
    candidates: list[Path] = []
    if mode == "脚本" and script_uid:
        candidates.append(
            Path.cwd() / "data" / script_uid / "Default" / "ConfigFile" / "default.json"
        )
    elif mode == "直控" and source_path:
        instances_dir = Path(source_path) / "config" / "instances"
        candidates.append(instances_dir / "default.json")
        if instances_dir.is_dir():
            only = [p for p in instances_dir.glob("*.json")]
            if len(only) == 1:
                candidates.append(only[0])
    elif script_uid:
        candidates.append(
            Path.cwd() / "data" / script_uid / user_uid / "ConfigFile" / "default.json"
        )
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            content = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        task_items = content.get("TaskItems") if isinstance(content, dict) else None
        if not isinstance(task_items, list):
            continue
        items: list[tuple[str, list[dict[str, Any]]]] = []
        for item in task_items:
            if not isinstance(item, dict) or not _truthy(item.get("default_check")):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            raw_options = (
                item.get("option") if isinstance(item.get("option"), list) else []
            )
            items.append((name, [o for o in raw_options if isinstance(o, dict)]))
        return items
    return None


def _translate_options(
    raw_options: list[dict[str, Any]],
    index: _InterfaceIndex,
    user_label: str,
    report: MigrationReport,
) -> dict[str, Any]:
    """旧 ``{name, index, selected_cases?, input_values?/data?, sub_options?}`` → ``{选项名: 值}``。"""

    translated: dict[str, Any] = {}
    for raw in raw_options:
        name = str(raw.get("name") or "").strip()
        definition = index.options.get(name)
        if not name or definition is None:
            report.dropped_options.append(f"{user_label}：{name or '(空)'}")
            continue
        option_type = str(definition.get("type") or "select")
        cases = (
            definition.get("cases") if isinstance(definition.get("cases"), list) else []
        )
        if option_type == "checkbox":
            selected = raw.get("selected_cases")
            if isinstance(selected, list):
                translated[name] = [str(item) for item in selected]
            elif selected is not None:
                report.dropped_options.append(f"{user_label}：{name}（勾选值格式不对）")
        elif option_type == "input":
            values = raw.get("data") if "data" in raw else raw.get("input_values")
            if isinstance(values, dict):
                translated[name] = _clean_input_values(definition, values)
            elif values is not None:
                report.dropped_options.append(f"{user_label}：{name}（输入值格式不对）")
        else:
            position = _int(raw.get("index"), 0)
            if 0 <= position < len(cases) and isinstance(cases[position], dict):
                case_name = cases[position].get("name")
                if case_name is not None:
                    translated[name] = str(case_name)
            else:
                report.dropped_options.append(f"{user_label}：{name}（index 越界）")
        sub_options = raw.get("sub_options")
        if isinstance(sub_options, list):
            translated.update(
                _translate_options(
                    _nested_options(sub_options, cases), index, user_label, report
                )
            )
    return translated


def _nested_options(sub_options: list[Any], cases: list[Any]) -> list[dict[str, Any]]:
    """把 ``sub_options`` 展平成真正的选项条目。

    MFAAvalonia 给 checkbox 选项写的 ``sub_options`` 是**各个 case 的容器**（名字就是 case 名，
    勾选状态另存在 ``selected_cases`` 里），不是选项；把它们当选项去查会一条条报「找不到」，
    把没丢的勾选说成丢了。case 容器自己再带的 ``sub_options`` 才是挂在该 case 下的选项。
    """

    case_names = {
        str(case.get("name") or "")
        for case in cases
        if isinstance(case, dict) and case.get("name") is not None
    }
    flattened: list[dict[str, Any]] = []
    for entry in sub_options:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("name") or "") in case_names:
            inner = entry.get("sub_options")
            if isinstance(inner, list):
                flattened.extend(o for o in inner if isinstance(o, dict))
            continue
        flattened.append(entry)
    return flattened


def _clean_input_values(
    definition: dict[str, Any], values: dict[str, Any]
) -> dict[str, str]:
    """input 选项的值：等于 interface 里声明的 ``default`` 的一律清空。

    旧前端把 ``default`` 预填进输入框（M9A 的兑换码 default 是字面量「占位」），旧引擎也照抄
    提交；MaaFW 引擎把 default 只当占位提示、不进执行值，真提交「占位」会让任务卡死。
    迁移是把这些预填值清掉的最后机会。
    """

    defaults: dict[str, str] = {}
    raw_inputs = definition.get("inputs")
    for item in raw_inputs if isinstance(raw_inputs, list) else []:
        if isinstance(item, dict) and item.get("name") is not None:
            defaults[str(item["name"])] = str(item.get("default") or "")
    cleaned: dict[str, str] = {}
    for key, value in values.items():
        text = "" if value is None else str(value)
        if text and defaults.get(str(key), None) == text:
            text = ""
        cleaned[str(key)] = text
    return cleaned


# ---------------------------------------------------------------------------
# 更新源推导与工具函数
# ---------------------------------------------------------------------------


#: EncryptValidator 解不开密文时写回的占位值，不是可用的 CDK。
_CORRUPT_SECRET_PLACEHOLDER = "数据损坏, 请重新设置"


def _seed_update_source(source_path: str, global_mirror_cdk: str) -> tuple[str, str]:
    """MFAA config.json 的 DownloadCDK → MAS 全局 CDK → GitHub。"""

    if source_path:
        config_path = Path(source_path) / "config" / "config.json"
        try:
            content = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            content = None
        if isinstance(content, dict):
            cdk = str(content.get("DownloadCDK") or "").strip()
            if cdk:
                return "MirrorChyan", cdk
    global_cdk = str(global_mirror_cdk or "").strip()
    if global_cdk and _CORRUPT_SECRET_PLACEHOLDER not in global_cdk:
        return "MirrorChyan", global_cdk
    return "GitHub", ""


def _read_interface_dict(root: Path) -> dict[str, Any] | None:
    """按 MaaFW 的加载器读 interface（含 import 合并）；读不到返回 None。"""

    try:
        from app.task.MaaFW.tools.core.interface.service import (
            MaaFWInterfaceService,
        )

        model = MaaFWInterfaceService().load(root)
    except Exception:  # noqa: BLE001 - 迁移只能降级，不能炸
        return None
    try:
        return model.model_dump(mode="json")
    except Exception:  # noqa: BLE001
        return None


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "on"}
    return bool(value)


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


__all__ = [
    "MigrationReport",
    "migrate_legacy_m9a_scripts",
    "migrate_legacy_script",
    "migrate_script_config_payload",
]
