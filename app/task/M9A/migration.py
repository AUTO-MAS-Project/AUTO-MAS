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

v5.6.0-beta.1 的迁移把所有等于 interface default 的输入值都清空了（自定义作战关卡的章节号 2、
关卡号 6 也在内），还丢了实例文件里勾选的「切换账号」。已经按那版迁过的配置由
``repair_m9a_migration_losses`` 按上面的备份补回一次。

「启动游戏」「切换账号」「关闭游戏」由 MAS 控制、不留在用户队列里（规则见 ``managed.py``）：
迁移与补救按同一规则落地，另有 ``normalize_m9a_managed_entries`` 在每次启动时对全部 M9A 用户
整理一遍（beta.1 迁移留下的、#1012 补回的、手加的、通用 MaaFW 脚本换成 M9A 带过来的），幂等。
这几段都在文件末尾。
"""

from __future__ import annotations

import copy
import json
import os
import shutil
from collections import Counter
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from app.task.M9A.flavor import (
    CLOSE_ENTRY,
    FALLBACK_TASK_NAMES,
    LEGACY_ENTRY_ALIASES,
    OFFICIAL_RESOURCE_NAME,
    STARTUP_ENTRY,
    SWITCH_ACCOUNT_ENTRY,
    is_m9a_project,
)
from app.task.M9A.managed import (
    InfoChange,
    Settlement,
    first_text_value,
    settle_snapshot,
    settle_user_info,
    split_message,
)
from app.task.MaaFW.tools.core.interface.models import resolve_task_instance_name
from app.utils import get_logger

logger = get_logger("M9A 迁移")

LEGACY_BACKUP_SUFFIX = ".m9a-legacy-"
LEGACY_BACKUP_KEEP = 3
# 旧 Run.RunTimeLimit 是「日志停滞」阈值（默认 10 分钟），MaaFW 的是整轮硬超时；照抄会把
# 整轮跑 10 分钟就杀掉，固定成 MaaFW 的默认。
MAAFW_RUN_TIME_LIMIT = 120
# 快速配置的旧引擎自己在首尾补启动 / 关闭、按「账号」插切号，队列里这三个是陈旧数据，直接剔。
_RUNTIME_MANAGED_ENTRIES = {STARTUP_ENTRY, CLOSE_ENTRY, SWITCH_ACCOUNT_ENTRY}
# 实例文件来源先只剔首尾：旧版原样照跑实例文件，里面勾选的「切换账号」是用户自己配的，要先
# 带着选项翻译出来，再按 managed.py 的规则落地（1 个进「账号」，多个照搬并提示拆分）。
_INSTANCE_FILE_MANAGED_ENTRIES = {STARTUP_ENTRY, CLOSE_ENTRY}
# 旧前端把 input 的 default 预填进输入框、旧引擎照抄提交。只有兑换码的「占位」是哨兵（真提交会让
# 任务卡死），其余 default 都是能跑的真值（自定义作战关卡的章节号 2、关卡号 6），不能清。
_PREFILL_SENTINELS = frozenset({"占位"})
# 迁移通知与补救通知共用的一句：关了快速配置时旧版直接跑实例文件、不读「账号」。
_ACCOUNT_NOW_SWITCHES = (
    "「账号」在旧版不参与运行，现在会用于自动切换账号（仅官服），如果原来只是备注请清空"
)
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
    #: 关了快速配置、但找不到 MFAA 实例文件，退回任务队列的用户。
    instance_file_fallbacks: list[str] = field(default_factory=list)
    #: 关了快速配置的用户：旧版不读「账号」，迁移后特调会拿它切号。
    account_switch_users: list[str] = field(default_factory=list)
    #: 实例文件里恰好一个切号：目标账号进了「账号」（``用户（账号 a）``）。
    imported_accounts: list[str] = field(default_factory=list)
    #: 上一项里原「账号」非空且不同、被切号账号取代的（``用户（原 c → 现 a）``）。
    replaced_accounts: list[str] = field(default_factory=list)
    #: 实例文件里有多个切号、照搬进队列等用户拆分的（``用户：拆分提示``）。
    split_users: list[str] = field(default_factory=list)
    backup_path: Path | None = None
    #: 迁移函数自己抛了异常：原文件已另存，后续 connect() 会按新类加载。
    failure: str = ""

    @property
    def changed(self) -> bool:
        return bool(self.migrated_scripts or self.retyped_scripts)

    @property
    def needs_attention(self) -> bool:
        """通知要不要用 warning 级别。"""

        return bool(
            self.failure
            or self.disabled_users
            or self.dropped_tasks
            or self.degraded_scripts
            or self.instance_file_fallbacks
            or self.account_switch_users
            or self.replaced_accounts
            or self.split_users
        )

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
                "读不到项目 interface、按内置别名迁移（任务选项与实例文件里的「切换账号」已丢弃）："
                + "、".join(self.degraded_scripts)
            )
        if self.disabled_users:
            lines.append(
                "服务器与脚本资源不一致、已停用的用户："
                + "、".join(self.disabled_users)
            )
        if self.account_switch_users:
            lines.append(
                f"以下用户原先关闭了快速配置，{_ACCOUNT_NOW_SWITCHES}："
                + "、".join(self.account_switch_users)
            )
        if self.instance_file_fallbacks:
            lines.append(
                "关闭了快速配置但找不到 MFAA 实例文件、已改用任务队列的用户："
                + "、".join(self.instance_file_fallbacks)
            )
        lines.extend(
            managed_notice_lines(
                imported=self.imported_accounts,
                replaced=self.replaced_accounts,
                split=self.split_users,
            )
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
    tmp = path.with_name(f"{path.name}.m9a-migrating")
    try:
        shutil.copyfile(path, backup)
        report.backup_path = backup
        _prune_backups(path)
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        logger.opt(exception=True).warning(f"M9A 迁移写回失败，配置未改动：{exc}")
        # 与迁移函数抛异常同一口径：文件没写回，「已迁移」一条也不能报；但紧接着
        # connect() 会按新类加载、旧键当场丢掉，所以失败与备份要带进启动通知。
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return MigrationReport(
            failure=f"写回失败：{type(exc).__name__}: {exc}",
            backup_path=report.backup_path,
        )
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


def _project_root_for_detection(
    payload: dict[str, Any], uid: str, *, prefer_source: bool = False
) -> Path | None:
    """识别用的项目根：副本在就读副本（路径由脚本 ID 推出），否则读来源目录。

    ``prefer_source`` 反过来先读来源目录：补救要用迁移当时读的那份 interface 重算。
    """

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
        candidates.insert(0 if prefer_source else len(candidates), Path(source))
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
    settle_switches: bool = True,
) -> dict[str, Any]:
    """把一个旧 M9AConfig 数据块翻译成 MaaFW 形状（含全部用户）。

    ``settle_switches`` 为假时实例文件里的切号原样留在快照里、不按 ``managed.py`` 落地——
    只给补救用：它要拿「那版本该留下什么切号」和现状比。
    """

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
                payload,
                users,
                index,
                resource_name,
                label,
                script_uid,
                report,
                settle_switches=settle_switches,
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
    *,
    settle_switches: bool = True,
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
            user,
            index,
            script_resource,
            script_label,
            payload,
            script_uid,
            uid,
            report,
            settle_switches=settle_switches,
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
    *,
    settle_switches: bool = True,
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
    account = str(info.get("Account") or "")
    # 关了快速配置时旧版原样跑实例文件、不读「账号」；迁移后特调只看账号非空、资源是官服就补切号。
    # 实例文件里本来就勾了切号的，目标账号下面会收进「账号」，行为不变；没勾的要提醒一句。
    if (
        status
        and account.strip()
        and not _truthy(info.get("IfQuickConfig", True))
        and script_resource == OFFICIAL_RESOURCE_NAME
        and not _has_switch_account(snapshot["taskOrder"], index)
    ):
        report.account_switch_users.append(f"{script_label} / {name}")
    if settle_switches:
        settlement = _settle_with_index(
            snapshot, index, official=script_resource == OFFICIAL_RESOURCE_NAME
        )
        snapshot = settlement.snapshot
        change = settle_user_info(
            settlement, account=account, notes=notes, note_split=True
        )
        account = change.account if change.account is not None else account
        notes = change.notes if change.notes is not None else notes
        _record_settlement(
            f"{script_label} / {name}",
            settlement,
            change,
            imported=report.imported_accounts,
            replaced=report.replaced_accounts,
            split=report.split_users,
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
            "Account": account,
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
    items, source = _legacy_queue_items(user, script_payload, script_uid, user_uid)
    order: list[str] = []
    checked: dict[str, bool] = {}
    options: dict[str, Any] = {}
    seen: Counter[str] = Counter()
    user_label = (
        f"{script_label} / {str((user.get('Info') or {}).get('Name') or user_uid[:8])}"
    )
    if source == "queue_fallback":
        report.instance_file_fallbacks.append(user_label)
    # 快速配置的旧引擎自己在首尾补启动 / 关闭、按「账号」插切号，队列里这三个是陈旧数据；
    # 实例文件则原样照跑，其中的切号留下（选项要靠 interface 翻译，读不到就只能照旧剔掉）。
    managed_entries = (
        _INSTANCE_FILE_MANAGED_ENTRIES
        if source == "instance_file" and index.available
        else _RUNTIME_MANAGED_ENTRIES
    )
    for raw_name, raw_options in items:
        task_name = index.resolve_task_name(raw_name)
        if not task_name:
            report.dropped_tasks.append(f"{user_label}：{raw_name}")
            continue
        if index.entry_of(task_name) in managed_entries:
            continue  # 由特调运行期补
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
) -> tuple[
    list[tuple[str, list[dict[str, Any]]]],
    Literal["instance_file", "queue", "queue_fallback"],
]:
    """旧用户的任务来源：快速配置关闭时是 MFAA 实例文件，否则是 ``Task.Queue``。

    第二个返回值是来源；``queue_fallback`` 表示关了快速配置、却找不到实例文件，退回了任务队列。
    """

    info = user.get("Info") if isinstance(user.get("Info"), dict) else {}
    source: Literal["instance_file", "queue", "queue_fallback"] = "queue"
    if not _truthy(info.get("IfQuickConfig", True)):
        instance_items = _instance_file_items(
            user, script_payload, script_uid, user_uid
        )
        if instance_items is not None:
            return instance_items, "instance_file"
        source = "queue_fallback"
    task = user.get("Task") if isinstance(user.get("Task"), dict) else {}
    raw = task.get("Queue")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw.strip() else []
        except ValueError:
            raw = []
    if not isinstance(raw, list):
        return [], source
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
    return items, source


def _has_switch_account(task_order: list[str], index: _InterfaceIndex) -> bool:
    """快照的任务列表里有没有「切换账号」（按 entry 判，重复实例 id 先还原成任务名）。"""

    return any(
        index.entry_of(resolve_task_instance_name(task_id, index.task_by_name))
        == SWITCH_ACCOUNT_ENTRY
        for task_id in task_order
    )


def _settle_with_index(
    snapshot: dict[str, Any], index: _InterfaceIndex, *, official: bool
) -> Settlement:
    """按 ``managed.py`` 的规则整理一份快照（interface 是字典形状的迁移索引）。"""

    def entry_of(task_id: str) -> str:
        return index.entry_of(resolve_task_instance_name(task_id, index.task_by_name))

    def account_of(task_id: str, options: Any) -> str:
        if not isinstance(options, dict):
            return ""
        found = _account_field_of(
            index, resolve_task_instance_name(task_id, index.task_by_name)
        )
        if found is not None:
            value = options.get(found[0])
            if isinstance(value, dict):
                return str(value.get(found[1]) or "").strip()
            return first_text_value(value)
        return first_text_value(options)

    return settle_snapshot(
        snapshot, entry_of=entry_of, account_of=account_of, official=official
    )


def _account_field_of(index: _InterfaceIndex, task_name: str) -> tuple[str, str] | None:
    """切号任务第一个 input 选项与它的第一个输入字段（与 ``flavor._account_field`` 同口径）。"""

    task = index.task_by_name.get(task_name) or {}
    raw_options = task.get("option") if isinstance(task, dict) else None
    for option_name in raw_options if isinstance(raw_options, list) else []:
        definition = index.options.get(str(option_name)) or {}
        if definition.get("type") != "input":
            continue
        inputs = definition.get("inputs")
        if isinstance(inputs, list) and inputs and isinstance(inputs[0], dict):
            return str(option_name), str(inputs[0].get("name") or "账号")
    return None


def _record_settlement(
    label: str,
    settlement: Settlement,
    change: InfoChange,
    *,
    imported: list[str],
    replaced: list[str],
    split: list[str],
) -> None:
    """整理结果进通知清单：导入的账号、被取代的原账号、新写了拆分提示的用户。"""

    if change.account is not None:
        if change.replaced_account:
            replaced.append(
                f"{label}（原 {change.replaced_account} → 现 {change.account}）"
            )
        else:
            imported.append(f"{label}（账号 {change.account}）")
    if change.split_note:
        split.append(f"{label}：{split_message(settlement.split_accounts)}")


def managed_notice_lines(
    *,
    cleaned: Collection[str] = (),
    imported: Collection[str],
    replaced: Collection[str],
    split: Collection[str],
) -> list[str]:
    """受管任务整理的通知行；迁移、补救、启动整理共用。"""

    lines: list[str] = []
    if cleaned:
        lines.append(
            "「启动游戏」「切换账号」「关闭游戏」改由 MAS 按上方信息自动加入（启动在前、"
            "切号紧跟、关闭在最后），已从这些用户的任务队列里移除："
            + "、".join(cleaned)
        )
    if imported:
        lines.append(
            "任务队列里「切换账号」的目标账号已填进上方「账号」：" + "、".join(imported)
        )
    if replaced:
        lines.append(
            "以下用户的「账号」与任务队列里切换账号的目标账号不同，已改用后者"
            "（之前实际切换的就是它），原值记进了备注：" + "、".join(replaced)
        )
    lines.extend(split)
    return lines


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
    """input 选项的值转成字符串，只清掉预填进来的哨兵 default（兑换码的「占位」）。

    旧前端把 ``default`` 预填进输入框，旧引擎也照抄提交；MaaFW 引擎把 default 只当占位提示、
    不进执行值，真提交「占位」会让任务卡死，迁移是把它清掉的最后机会。别的 default 是能跑的
    真值（自定义作战关卡的章节号 2、关卡号 6），引擎对 string 空值又不回落 default，清掉就会
    下发 ``-12`` 这样的关卡。
    """

    defaults = _input_defaults(definition)
    cleaned: dict[str, str] = {}
    for key, value in values.items():
        text = "" if value is None else str(value)
        if text in _PREFILL_SENTINELS and defaults.get(str(key)) == text:
            text = ""
        cleaned[str(key)] = text
    return cleaned


def _input_defaults(definition: dict[str, Any] | None) -> dict[str, str]:
    """input 选项各字段在 interface 里声明的 ``default``（``{字段名: 值}``）。"""

    defaults: dict[str, str] = {}
    raw_inputs = definition.get("inputs") if isinstance(definition, dict) else None
    for item in raw_inputs if isinstance(raw_inputs, list) else []:
        if isinstance(item, dict) and item.get("name") is not None:
            defaults[str(item["name"])] = str(item.get("default") or "")
    return defaults


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

    return _dump_interface(_read_interface_model(root))


def _read_interface_model(root: Path) -> Any | None:
    try:
        from app.task.MaaFW.tools.core.interface.service import (
            MaaFWInterfaceService,
        )

        return MaaFWInterfaceService().load(root)
    except Exception:  # noqa: BLE001 - 迁移只能降级，不能炸
        return None


def _dump_interface(model: Any | None) -> dict[str, Any] | None:
    if model is None:
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


# ---------------------------------------------------------------------------
# 补救：v5.6.0-beta.1 迁移丢掉的东西
# ---------------------------------------------------------------------------

#: 补救看过备份就在 ``ScriptConfig.json`` 旁留这个标记，此后不再做：用户后来自己删掉的切号、
#: 清空的值不能再被补回来。
REPAIR_MARKER_SUFFIX = ".m9a-repaired"
REPAIR_BACKUP_SUFFIX = ".m9a-repair-"


@dataclass
class RepairReport:
    """一次补救的结果，给启动通知与日志用。"""

    restored_inputs: list[str] = field(default_factory=list)
    #: 实例文件里恰好一个切号：目标账号找回进了「账号」（``用户（账号 a）``）。
    restored_accounts: list[str] = field(default_factory=list)
    #: 上一项里原「账号」非空且不同、被切号账号取代的（``用户（原 c → 现 a）``）。
    replaced_accounts: list[str] = field(default_factory=list)
    #: 实例文件里有多个切号：原样补回任务队列，等用户拆分（拆分提示由启动整理写）。
    restored_switches: list[str] = field(default_factory=list)
    #: 升级后改过任务列表或「账号」、切号不自动找回的用户（带原来的目标账号）。
    manual_switches: list[str] = field(default_factory=list)
    account_switch_users: list[str] = field(default_factory=list)
    #: 来源目录与内嵌副本都读不到 interface、没法按备份核对的脚本。
    unchecked_scripts: list[str] = field(default_factory=list)
    backup_path: Path | None = None

    @property
    def needs_notice(self) -> bool:
        return bool(
            self.restored_inputs
            or self.restored_accounts
            or self.replaced_accounts
            or self.restored_switches
            or self.manual_switches
            or self.account_switch_users
            or self.unchecked_scripts
        )

    def summary_lines(self) -> list[str]:
        lines: list[str] = []
        if self.restored_inputs:
            lines.append(
                "升级时被清空的输入值（如自定义作战关卡的章节号、关卡号）已按迁移前的备份找回："
                + "、".join(self.restored_inputs)
            )
        if self.restored_accounts:
            lines.append(
                "升级时丢掉的「切换账号」（关闭快速配置时在 M9A 里配的）已找回，"
                "目标账号填进了上方「账号」，由 MAS 自动切换："
                + "、".join(self.restored_accounts)
            )
        lines.extend(
            managed_notice_lines(imported=(), replaced=self.replaced_accounts, split=())
        )
        if self.restored_switches:
            lines.append(
                "升级时丢掉的多个「切换账号」已原样补回任务队列，需要拆成多个用户才能运行"
                "（见「M9A 任务队列已按新规则整理」通知）："
                + "、".join(self.restored_switches)
            )
        if self.manual_switches:
            lines.append(
                "以下用户升级后改过任务列表或「账号」，「切换账号」的目标账号没有自动找回，"
                "需要的话请填进上方「账号」：" + "、".join(self.manual_switches)
            )
        if self.account_switch_users:
            lines.append(
                f"以下用户原先关闭了快速配置，{_ACCOUNT_NOW_SWITCHES}："
                + "、".join(self.account_switch_users)
            )
        if self.unchecked_scripts:
            lines.append(
                "以下脚本读不到项目文件，没能按迁移前的备份核对，请检查自定义作战关卡的"
                "章节号、关卡号与「切换账号」：" + "、".join(self.unchecked_scripts)
            )
        return lines

    def notice(self) -> dict[str, Any]:
        lines = self.summary_lines()
        if self.backup_path is not None:
            lines.append(f"补救前的配置已备份为 {self.backup_path.name}")
        return {
            "level": "warning"
            if self.manual_switches
            or self.account_switch_users
            or self.unchecked_scripts
            or self.replaced_accounts
            or self.restored_switches
            else "info",
            "title": "已找回 M9A 升级时丢掉的设置"
            if self.restored_inputs or self.restored_accounts or self.restored_switches
            else "M9A 升级后请确认设置",
            "lines": lines,
        }


def repair_m9a_migration_losses(
    script_config_path: Path,
    *,
    skip_uids: Collection[str] = (),
    now: datetime | None = None,
) -> RepairReport:
    """启动期入口：按迁移备份补回 v5.6.0-beta.1 迁移丢掉的东西，只做一次。

    那版迁移把等于 interface default 的输入值一律清空（自定义作战关卡的章节号 2、关卡号 6
    也在内），还把实例文件里勾选的「切换账号」当成首尾任务剔掉了。原料还在
    ``ScriptConfig.json.m9a-legacy-*.bak`` 里，补法见 ``repair_script_config_payload``。

    必须排在 ``migrate_legacy_m9a_scripts`` 之后、``ScriptConfig.connect()`` 之前；``skip_uids``
    传这次启动刚迁过的脚本，它们用的就是修好的迁移，通知也已经发过。没有迁移备份就什么都
    不做；看过备份就留标记，哪怕这次没东西可补。出错只记日志，下次启动再试。
    """

    report = RepairReport()
    path = Path(script_config_path)
    marker = path.with_name(f"{path.name}{REPAIR_MARKER_SUFFIX}")
    if marker.exists() or not path.is_file():
        return report
    failed_prefix = f"{path.name}{LEGACY_BACKUP_SUFFIX}failed-"
    backups = sorted(
        (
            item
            for item in path.parent.glob(f"{path.name}{LEGACY_BACKUP_SUFFIX}*.bak")
            if not item.name.startswith(failed_prefix)
        ),
        key=lambda item: item.name,
        reverse=True,
    )
    if not backups:
        return report

    tmp = path.with_name(f"{path.name}.m9a-repairing")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        legacy_scripts = {
            uid: payload
            for uid, payload in _collect_legacy_scripts(backups).items()
            if uid not in skip_uids
        }
        changed = isinstance(data, dict) and repair_script_config_payload(
            data, legacy_scripts, report
        )
        stamp = now or datetime.now()
        if changed:
            backup = path.with_name(
                f"{path.name}{REPAIR_BACKUP_SUFFIX}{stamp.strftime('%Y%m%d%H%M%S')}.bak"
            )
            shutil.copyfile(path, backup)
            report.backup_path = backup
            tmp.write_text(
                json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8"
            )
            os.replace(tmp, path)
        marker.write_text(
            json.dumps(
                {
                    "repairedAt": stamp.isoformat(timespec="seconds"),
                    "lines": report.summary_lines(),
                },
                ensure_ascii=False,
                indent=4,
            ),
            encoding="utf-8",
        )
    except Exception as exc:  # noqa: BLE001 - 补救失败不该挡住启动
        logger.opt(exception=True).warning(f"M9A 迁移补救失败，下次启动再试：{exc}")
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return RepairReport()
    for line in report.summary_lines():
        logger.info(f"M9A 迁移补救：{line}")
    return report


def _collect_legacy_scripts(backups: list[Path]) -> dict[str, dict[str, Any]]:
    """从新到旧读迁移备份，每个 M9A 脚本取最新一份迁移前的旧数据块。"""

    legacy: dict[str, dict[str, Any]] = {}
    for backup in backups:
        try:
            content = json.loads(backup.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(content, dict):
            continue
        for instance in content.get("instances") or []:
            if not isinstance(instance, dict) or instance.get("type") != "M9AConfig":
                continue
            uid = str(instance.get("uid") or "")
            payload = content.get(uid)
            if (
                uid not in legacy
                and isinstance(payload, dict)
                and _is_legacy_m9a_payload(payload)
            ):
                legacy[uid] = payload
    return legacy


def repair_script_config_payload(
    data: dict[str, Any],
    legacy_scripts: dict[str, dict[str, Any]],
    report: RepairReport,
) -> bool:
    """按迁移前的旧数据块就地补 ``data``，返回有没有改动。

    用修好的迁移把旧数据块重算一遍当答案，逐个用户与现状比，只动两类地方：

    1. input 字段：答案里的值等于 interface default（beta.1 就是清的这种）、现状是空的 → 填回；
       用户升级后自己填过的不动。
    2. 「切换账号」：答案里有、现状一个都没有 → 按 ``managed.py`` 的规则落地：恰好一个有效切号
       就把目标账号填进「账号」（不回队列）；多个（官服）时现状的任务顺序恰好等于答案去掉切号，
       才按答案原位补回队列等用户拆分。用户升级后改过「账号」，或多个切号时调过顺序、增删过
       任务，就不猜，提醒用户自己填。
    """

    changed = False
    for instance in data.get("instances") or []:
        if not isinstance(instance, dict) or instance.get("type") != "M9AConfig":
            continue
        uid = str(instance.get("uid") or "")
        payload = data.get(uid)
        legacy = legacy_scripts.get(uid)
        user_data = _user_data_of(payload) if isinstance(payload, dict) else None
        if legacy is None or user_data is None:
            continue
        script_label = _script_label(payload, uid)
        # 用迁移当时读的来源目录重算，答案才和那版的输出逐项对得上；来源目录删了就退到副本
        # （副本里也有 interface 与直控用的 config/instances）
        root = _project_root_for_detection(legacy, uid, prefer_source=True)
        index = _InterfaceIndex(_read_interface_dict(root) if root else None)
        if root is None or not index.available:
            report.unchecked_scripts.append(script_label)  # 认不出 default 与切号，不猜
            continue
        answer_source = copy.deepcopy(legacy)
        if isinstance(answer_source.get("Info"), dict):
            answer_source["Info"]["Path"] = str(root)
        # 切号不在答案里落地：要拿「那版本该留下什么切号」和现状比
        answer = migrate_legacy_script(
            answer_source, MigrationReport(), script_uid=uid, settle_switches=False
        )
        answer_users = _user_data_of(answer) or {}
        legacy_users = _user_data_of(legacy) or {}
        official = (payload.get("Info") or {}).get("Resource") == OFFICIAL_RESOURCE_NAME
        for user_uid, user in user_data.items():
            answer_user = answer_users.get(user_uid)
            if not isinstance(user, dict) or not isinstance(answer_user, dict):
                continue
            info = user.get("Info") if isinstance(user.get("Info"), dict) else {}
            legacy_info = (legacy_users.get(user_uid) or {}).get("Info") or {}
            label = f"{script_label} / {str(info.get('Name') or user_uid[:8])}"
            account = str(info.get("Account") or "").strip()
            # 升级后自己填了别的「账号」：补回实例文件里的切号会压过它，交给用户决定
            account_changed = account != str(legacy_info.get("Account") or "").strip()
            answer_snapshot = _load_snapshot(
                (answer_user.get("Task") or {}).get("TaskSnapshot")
            )
            if _repair_user_snapshot(
                user,
                answer_user,
                index,
                keep_account=bool(account and account_changed),
                official=official,
                label=label,
                report=report,
            ):
                changed = True

            # 旧版不读的「账号」beta.1 起被拿去切号了，补一句提醒（判据同迁移）；升级后
            # 自己改过账号的，是有意要切，不提醒；实例文件里本来就配了切号的，「账号」
            # 已经是（或该是）那个切号的目标账号，也不提醒
            if (
                official
                and _truthy(info.get("Status", True))
                and account
                and not account_changed
                and not _truthy(legacy_info.get("IfQuickConfig", True))
                and not _has_switch_account(
                    list((answer_snapshot or {}).get("taskOrder") or []), index
                )
            ):
                report.account_switch_users.append(label)
    return changed


def _repair_user_snapshot(
    user: dict[str, Any],
    answer_user: dict[str, Any],
    index: _InterfaceIndex,
    *,
    keep_account: bool,
    official: bool,
    label: str,
    report: RepairReport,
) -> bool:
    """单个用户的两类补救；队列有改动就写回 ``user`` 的 ``Task.TaskSnapshot``，账号写 ``Info``。

    ``keep_account`` 为真（用户升级后自己改了「账号」）时切号不自动找回，只提醒。
    """

    task = user.get("Task")
    current = (
        _load_snapshot(task.get("TaskSnapshot")) if isinstance(task, dict) else None
    )
    answer = _load_snapshot((answer_user.get("Task") or {}).get("TaskSnapshot"))
    if current is None or answer is None or not isinstance(task, dict):
        return False
    current_options = current.setdefault("taskOptions", {})
    answer_options = answer.get("taskOptions") or {}
    if not isinstance(current_options, dict) or not isinstance(answer_options, dict):
        return False

    # 一、被清空的 input 字段
    restored = False
    for task_id, answer_task_options in answer_options.items():
        current_task_options = current_options.get(task_id)
        if not isinstance(answer_task_options, dict) or not isinstance(
            current_task_options, dict
        ):
            continue
        for option_name, answer_value in answer_task_options.items():
            current_value = current_task_options.get(option_name)
            if not isinstance(answer_value, dict) or not isinstance(
                current_value, dict
            ):
                continue
            defaults = _input_defaults(index.options.get(option_name))
            for field_name, text in answer_value.items():
                if (
                    text
                    and text == defaults.get(field_name)
                    and not current_value.get(field_name)
                ):
                    current_value[field_name] = text
                    restored = True
    if restored:
        report.restored_inputs.append(label)

    # 二、被剔掉的切换账号：按 managed.py 落地——一个进「账号」，多个（官服）原样回队列
    switched = False
    account_restored = False
    answer_order = [str(task_id) for task_id in answer.get("taskOrder") or []]
    switch_ids = [
        task_id for task_id in answer_order if _has_switch_account([task_id], index)
    ]
    current_order = current.get("taskOrder")
    if (
        switch_ids
        and isinstance(current_order, list)
        and not _has_switch_account(current_order, index)
    ):
        settlement = _settle_with_index(answer, index, official=official)
        accounts = [
            str(value)
            for task_id in switch_ids
            for option_value in (answer_options.get(task_id) or {}).values()
            if isinstance(option_value, dict)
            for value in option_value.values()
            if str(value).strip()
        ]
        manual_line = (
            f"{label}（原目标账号：{'、'.join(accounts)}）" if accounts else label
        )
        if settlement.account:
            if keep_account:
                report.manual_switches.append(manual_line)
            else:
                info = user.get("Info")
                if not isinstance(info, dict):
                    info = user["Info"] = {}
                change = settle_user_info(
                    settlement,
                    account=str(info.get("Account") or ""),
                    notes=str(info.get("Notes") or ""),
                    note_split=False,
                )
                if change.account is not None:  # 「账号」已经是它就没什么可找回的
                    info.update(change.updates())
                    if change.replaced_account:
                        report.replaced_accounts.append(
                            f"{label}（原 {change.replaced_account} → 现 {settlement.account}）"
                        )
                    report.restored_accounts.append(
                        f"{label}（账号 {settlement.account}）"
                    )
                    account_restored = True
        elif settlement.split_accounts:
            if not keep_account and current_order == [
                task_id for task_id in answer_order if task_id not in switch_ids
            ]:
                current["taskOrder"] = answer_order
                checked = current.setdefault("taskChecked", {})
                for task_id in switch_ids:
                    checked[task_id] = True
                    if task_id in answer_options:
                        current_options[task_id] = answer_options[task_id]
                report.restored_switches.append(label)
                switched = True
            else:
                report.manual_switches.append(manual_line)
        # 没有有效切号（没勾或账号空）、或多个切号但资源不是官服（从来没生效过）：无可找回

    if restored or switched:
        task["TaskSnapshot"] = json.dumps(current, ensure_ascii=False)
    return restored or switched or account_restored


def _load_snapshot(raw: Any) -> dict[str, Any] | None:
    """``Task.TaskSnapshot`` 的 JSON 串 → 字典；空串或坏数据返回 None。"""

    try:
        snapshot = json.loads(raw) if isinstance(raw, str) and raw.strip() else None
    except ValueError:
        return None
    return snapshot if isinstance(snapshot, dict) else None


# ---------------------------------------------------------------------------
# 每次启动：受管任务整理（启动游戏 / 切换账号 / 关闭游戏不留在用户队列里）
# ---------------------------------------------------------------------------

MANAGED_BACKUP_SUFFIX = ".m9a-managed-"
MANAGED_BACKUP_KEEP = 3


@dataclass
class ManagedEntriesReport:
    """一次受管任务整理的结果，给启动通知与日志用。"""

    #: 队列里的受管任务被移除的用户。
    cleaned_users: list[str] = field(default_factory=list)
    imported_accounts: list[str] = field(default_factory=list)
    replaced_accounts: list[str] = field(default_factory=list)
    #: 新写了拆分提示的用户（整行文案）。
    split_users: list[str] = field(default_factory=list)
    backup_path: Path | None = None

    @property
    def needs_notice(self) -> bool:
        return bool(
            self.cleaned_users
            or self.imported_accounts
            or self.replaced_accounts
            or self.split_users
        )

    def summary_lines(self) -> list[str]:
        return managed_notice_lines(
            cleaned=self.cleaned_users,
            imported=self.imported_accounts,
            replaced=self.replaced_accounts,
            split=self.split_users,
        )

    def notice(self) -> dict[str, Any]:
        lines = self.summary_lines()
        if self.backup_path is not None:
            lines.append(f"整理前的配置已备份为 {self.backup_path.name}")
        return {
            "level": "warning"
            if self.split_users or self.replaced_accounts
            else "info",
            "title": "M9A 任务队列已按新规则整理",
            "lines": lines,
        }


def normalize_m9a_managed_entries(
    script_config_path: Path, *, now: datetime | None = None
) -> ManagedEntriesReport:
    """启动期入口：全部 M9A 用户按 ``managed.py`` 的规则整理一遍，幂等，改了才写盘。

    排在迁移与补救之后、``ScriptConfig.connect()`` 之前（同样改原始 JSON）。读不到 interface
    的脚本这次跳过（视图还没建时下次启动再整理；运行期同一口径，不会跑错）。出错只记日志。
    """

    report = ManagedEntriesReport()
    path = Path(script_config_path)
    if not path.is_file():
        return report
    tmp = path.with_name(f"{path.name}.m9a-normalizing")
    try:
        raw = path.read_bytes()
        if b'"M9AConfig"' not in raw:
            return report  # 没有 M9A 脚本就不读 interface
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict) or not normalize_script_config_payload(
            data, report
        ):
            return report
        stamp = (now or datetime.now()).strftime("%Y%m%d%H%M%S")
        backup = path.with_name(f"{path.name}{MANAGED_BACKUP_SUFFIX}{stamp}.bak")
        shutil.copyfile(path, backup)
        report.backup_path = backup
        _prune_managed_backups(path)
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")
        os.replace(tmp, path)
    except Exception as exc:  # noqa: BLE001 - 整理失败不该挡住启动，运行期照样按规则跑
        logger.opt(exception=True).warning(f"M9A 受管任务整理失败，下次启动再试：{exc}")
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return ManagedEntriesReport()
    for line in report.summary_lines():
        logger.info(f"M9A 受管任务整理：{line}")
    return report


def _run_resource(model: Any, payload: dict[str, Any]) -> str | None:
    """脚本运行时实际生效的资源：与建运行计划同一个 ``resolve_run_selection``（原始 JSON 版）。"""

    from app.task.MaaFW.tools.core.runner.run_plan import resolve_run_selection

    info = payload.get("Info") if isinstance(payload.get("Info"), dict) else {}
    emulator = (
        payload.get("Emulator") if isinstance(payload.get("Emulator"), dict) else {}
    )
    _, resource = resolve_run_selection(
        model,
        configured_controller=str(info.get("Controller") or ""),
        emulator_selected=str(emulator.get("Id") or "-") != "-",
        configured_resource=str(info.get("Resource") or ""),
    )
    return resource


def _prune_managed_backups(path: Path) -> None:
    backups = sorted(
        path.parent.glob(f"{path.name}{MANAGED_BACKUP_SUFFIX}*.bak"),
        key=lambda item: item.name,
    )
    for stale in backups[:-MANAGED_BACKUP_KEEP]:
        try:
            stale.unlink()
        except OSError:
            pass


def normalize_script_config_payload(
    data: dict[str, Any], report: ManagedEntriesReport
) -> bool:
    """对整份 ``ScriptConfig.json`` 字典就地整理全部 M9A 用户；返回有没有改动。"""

    changed = False
    for instance in data.get("instances") or []:
        if not isinstance(instance, dict) or instance.get("type") != "M9AConfig":
            continue
        uid = str(instance.get("uid") or "")
        payload = data.get(uid)
        user_data = _user_data_of(payload) if isinstance(payload, dict) else None
        if not isinstance(payload, dict) or user_data is None:
            continue
        if not any(
            _load_snapshot((user.get("Task") or {}).get("TaskSnapshot"))
            for user in _iter_users(payload)
        ):
            continue  # 没有一个用户有队列：不必读 interface
        root = _project_root_for_detection(payload, uid)
        model = _read_interface_model(root) if root else None
        index = _InterfaceIndex(_dump_interface(model))
        if model is None or not index.available:
            logger.info(
                f"M9A 受管任务整理跳过「{_script_label(payload, uid)}」：读不到项目 interface"
            )
            continue
        script_label = _script_label(payload, uid)
        official = _run_resource(model, payload) == OFFICIAL_RESOURCE_NAME
        for user_uid in [
            str(item.get("uid") or "")
            for item in user_data.get("instances") or []
            if isinstance(item, dict)
        ]:
            user = user_data.get(user_uid)
            if isinstance(user, dict) and _normalize_user(
                user,
                index,
                official=official,
                label=f"{script_label} / {str((user.get('Info') or {}).get('Name') or user_uid[:8])}",
                report=report,
            ):
                changed = True
    return changed


def _normalize_user(
    user: dict[str, Any],
    index: _InterfaceIndex,
    *,
    official: bool,
    label: str,
    report: ManagedEntriesReport,
) -> bool:
    task = user.get("Task")
    snapshot = (
        _load_snapshot(task.get("TaskSnapshot")) if isinstance(task, dict) else None
    )
    if snapshot is None or not isinstance(task, dict):
        return False
    info = user.get("Info")
    if not isinstance(info, dict):
        info = {}
    settlement = _settle_with_index(snapshot, index, official=official)
    change = settle_user_info(
        settlement,
        account=str(info.get("Account") or ""),
        notes=str(info.get("Notes") or ""),
        note_split=True,
    )
    updates = change.updates()
    if not settlement.changed and not updates:
        return False
    if settlement.changed:
        task["TaskSnapshot"] = json.dumps(settlement.snapshot, ensure_ascii=False)
        # 只移除了一个切号、账号已写进「账号」的，「已填进账号」那一行就说清了，不再重复
        only_absorbed_switch = change.account is not None and all(
            _has_switch_account([task_id], index) for task_id in settlement.removed
        )
        if settlement.removed and not only_absorbed_switch:
            report.cleaned_users.append(label)
    if updates:
        user["Info"] = {**info, **updates}
    _record_settlement(
        label,
        settlement,
        change,
        imported=report.imported_accounts,
        replaced=report.replaced_accounts,
        split=report.split_users,
    )
    return True


__all__ = [
    "ManagedEntriesReport",
    "MigrationReport",
    "RepairReport",
    "migrate_legacy_m9a_scripts",
    "migrate_legacy_script",
    "migrate_script_config_payload",
    "normalize_m9a_managed_entries",
    "normalize_script_config_payload",
    "repair_m9a_migration_losses",
    "repair_script_config_payload",
]
