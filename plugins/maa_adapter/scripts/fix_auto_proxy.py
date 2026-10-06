"""Second pass fixes on task/auto_proxy.py."""

from __future__ import annotations

import re
from pathlib import Path

DST = Path(__file__).resolve().parents[1] / "src" / "maa_adapter" / "task" / "auto_proxy.py"

TASK_IF = {t: f"if_{t.lower()}" if t != "StartUp" else "if_start_up" for t in [
    "StartUp", "DepotMaintain", "Fight", "Infrast", "Recruit", "Mall", "Award", "Roguelike", "SwitchTheme"
]}
# MAA_TASKS mapping
for i, t in enumerate(["StartUp", "DepotMaintain", "Fight", "Infrast", "Recruit", "Mall", "Award", "Roguelike", "SwitchTheme"]):
    TASK_IF[t] = f"if_{t[0].lower() + t[1:]}" if t != "StartUp" else "if_start_up"
TASK_IF["StartUp"] = "if_start_up"
TASK_IF["DepotMaintain"] = "if_depot_maintain"
TASK_IF["SwitchTheme"] = "if_switch_theme"

RUN_LIMIT = {
    "RunTimesLimit": "run_times_limit",
    "AnnihilationTimeLimit": "annihilation_time_limit",
    "RoutineTimeLimit": "routine_time_limit",
    "GameUpdateTimeLimit": "game_update_time_limit",
}


def main() -> None:
    text = DST.read_text(encoding="utf-8")

    # imports block
    old_utils = """from auto_mas_core.services import Notify, System
from auto_mas_core.utils import (
    ARKNIGHTS_PACKAGE_NAME,
    LogMonitor,
    MAA_ANNIHILATION_FIGHT_BASE,
    MAA_GREEN_TICKET_STORE_TASK,
    MAA_MODE_TIME_LIMIT_BOOK,
    MAA_RUN_MOOD_BOOK,
    MAA_STAGE_KEY,
    MAA_TASK_TRANSITION_METHOD_BOOK,
    MAA_TASKS,
    MAA_TASKS_ZH,
    ProcessManager,
    UTC4,
    get_logger,
    mark_native_config_injected,
    read_file,
    write_file,
)"""
    new_utils = """from auto_mas_core import (
    Config as HostConfig,
    HistoryRecordData,
    LogRecordEntry,
    Publisher,
    TaskMode,
    protocol,
    WSTaskNoticeData,
)
from auto_mas_core.adapters.script import AutoProxyWorker
from auto_mas_core.services import Notify, System
from auto_mas_core.utils import (
    LogMonitor,
    ProcessManager,
    get_logger,
    mark_native_config_injected,
    read_file,
    write_file,
)
from ..constants import (
    ARKNIGHTS_PACKAGE_NAME,
    MAA_ANNIHILATION_FIGHT_BASE,
    MAA_GREEN_TICKET_STORE_TASK,
    MAA_MODE_TIME_LIMIT_BOOK,
    MAA_RUN_MOOD_BOOK,
    MAA_STAGE_KEY,
    MAA_TASK_TRANSITION_METHOD_BOOK,
    MAA_TASKS,
    MAA_TASKS_ZH,
    UTC4,
    game_now,
)
from ..schema import MaaPlan, MaaScript, MaaUser"""
    text = text.replace(old_utils, new_utils)
    text = text.replace("from maa_adapter.tools.notify import", "from ..features.notify import")

    # duplicate final_task → _maa_final (the long cleanup one)
    text = text.replace(
        "\n    async def final_task(self):\n        if self._check_result != \"Pass\":",
        "\n    async def _maa_final(self) -> None:\n        if self._check_result != \"Pass\":",
        1,
    )

    # strip old stats block in _maa_final
    start = text.find("        user_logs_list = []")
    end = text.find("        if self.run_book[\"Annihilation\"] and self.run_book[\"Routine\"]:")
    if start != -1 and end != -1 and start < end:
        text = text[:start] + text[end:]

    text = text.replace("self.user_item.name", "self.user_item.info.name")
    text = text.replace("log_item.status", "log_item.info.status")
    text = text.replace("log_item.content", "log_item.info.content")

    text = re.sub(
        r"\s*self\.user_item\.log_record\[self\.log_start_time\] = \(\s*self\._cur_log\.info\s*\) = LogRecord\(\)",
        "\n                await self._begin_log_record()",
        text,
    )

    text = text.replace(
        'self.user_entry.get(\'Data\', \'AnnihilationCompletedWeek\')',
        "self.user_entry.data.annihilation_completed_week",
    )

    # task dict comprehension
    text = re.sub(
        r'self\.user_entry\.get\("Task", f"If\{task\}"\)',
        r"getattr(self.user_entry.task, f'if_{task.lower()}') if task != 'StartUp' else self.user_entry.task.if_start_up",
        text,
    )

    text = text.replace(
        "self.script_entry.get('Run', 'RunTimesLimit')",
        "self.script_entry.run.run_times_limit",
    )

    for old, new in RUN_LIMIT.items():
        text = text.replace(
            f'self.script_entry.get("Run", MAA_MODE_TIME_LIMIT_BOOK[self.mode])',
            f"getattr(self.script_entry.run, '{RUN_LIMIT.get('RoutineTimeLimit')}')" ,
        )
    # fix mode time limit book - use getattr with mapping
    text = text.replace(
        """max(
                    self.script_entry.get("Run", MAA_MODE_TIME_LIMIT_BOOK[self.mode]),
                    self.script_entry.get("Run", "GameUpdateTimeLimit"),
                )
                if self.if_game_hot_update
                else self.script_entry.get("Run", MAA_MODE_TIME_LIMIT_BOOK[self.mode])""",
        """max(
                    getattr(
                        self.script_entry.run,
                        {
                            "GreenTicketStore": "routine_time_limit",
                            "Annihilation": "annihilation_time_limit",
                            "Routine": "routine_time_limit",
                        }[self.mode],
                    ),
                    self.script_entry.run.game_update_time_limit,
                )
                if self.if_game_hot_update
                else getattr(
                    self.script_entry.run,
                    {
                        "GreenTicketStore": "routine_time_limit",
                        "Annihilation": "annihilation_time_limit",
                        "Routine": "routine_time_limit",
                    }[self.mode],
                )""",
    )

    text = text.replace(
        'f"{self.script_entry.get(\'Emulator\', \'Index\')}"',
        "str(self.script_entry.info.game_device_id)",
    )

    # stage keys on user info
    text = re.sub(
        r'stage_key: self\.user_entry\.get\("Info", stage_key\)',
        "stage_key: getattr(self.user_entry.info, stage_key.lower())",
        text,
    )

    # _has_completed_sanity_task fix
    text = text.replace(
        "for log_record in log_records:\n        lines = log_record.content",
        "for log_record in log_records:\n        lines = log_record.info.content if hasattr(log_record, 'info') else log_record.content",
    )

    # device helpers at end of class methods - insert before _maa_check if missing get_adb
    if "_adb_path" not in text:
        adb_block = '''
    def _adb_path(self) -> str:
        handle = self.runtime.device if self.runtime else None
        if handle is None:
            return ""
        try:
            dev = handle.control.config.devices[handle.device_uid]
        except Exception:
            return ""
        return str(getattr(getattr(dev, "info", None), "adb_path", "") or "")

    async def _open_emulator(self, package: str | None):
        handle = self._device()
        ctrl = handle.control
        uid = handle.device_uid
        ticket = handle.ticket
        try:
            await ctrl.open(uid, package, ticket=ticket)
        except TypeError:
            await handle.open()
            if package and hasattr(ctrl, "launch_app"):
                await ctrl.launch_app(uid, package, ticket=ticket)
        try:
            dev = ctrl.config.devices[uid]
            info = getattr(dev, "info", None)
            from types import SimpleNamespace
            return SimpleNamespace(
                adb_path=str(getattr(info, "adb_path", "") or ""),
                adb_address=str(getattr(info, "adb_address", "") or ""),
                index=str(uid),
            )
        except Exception:
            from types import SimpleNamespace
            return SimpleNamespace(adb_path=self._adb_path(), adb_address="", index=str(uid))

    async def _set_emulator_visible(self, visible: bool) -> None:
        handle = self.runtime.device if self.runtime else None
        if handle is None:
            return
        if visible:
            await handle.show()
        else:
            await handle.hide()

'''
        text = text.replace("\n    async def _maa_check(self)", adb_block + "\n    async def _maa_check(self)")

    text = text.replace(
        "await self._device().open(",
        "await self._open_emulator(",
    )
    text = text.replace(
        "await self._device().setVisible(\n                            self.script_entry.info.game_device_id, False\n                        )",
        "await self._set_emulator_visible(False)",
    )
    text = text.replace("self._device().get_adb_path()", "self._adb_path()")

    # append history helpers before last on_crash or at end
    if "async def build_history_data" not in text:
        tail = '''
_HISTORY_OK = frozenset({"Success!"})


    async def build_history_data(self, script_item):
        if self.user_uid not in script_item.users:
            return {}
        user_item = script_item.users[self.user_uid]
        book = {}
        for uid, rec in user_item.log_record.items():
            stats, _six = parse_maa_log(list(rec.info.content), rec.info.status)
            status = "success" if rec.info.status in _HISTORY_OK else "error"
            book[uid] = HistoryRecordData(
                status=status,
                message=rec.info.status or "",
                data=stats,
            )
        return book

    async def _rewrite_running_logs(self) -> None:
        for rec in self.user_item.log_record.values():
            if rec.info.status == "MAA 正常运行中":
                rec.info.status = "任务被用户手动中止"
        await self.user_item.commit()

    async def _send_stat_notifications(self) -> None:
        from ..features.notify import load_screenshot_images, push_notification, screenshot_entries

        merged: dict = {}
        if_six_star = False
        for rec in self.user_item.log_record.values():
            stats, six = parse_maa_log(list(rec.info.content), rec.info.status)
            if stats:
                merged.update(stats)
            if six:
                if_six_star = True
        if self._cultivate_achievement_summary:
            merged["cultivate_achievement"] = "、".join(self._cultivate_achievement_summary)
        if not merged and not if_six_star:
            return
        merged["user_info"] = self.user_item.info.name
        merged["start_time"] = self.user_start_time.strftime("%Y-%m-%d %H:%M:%S")
        merged["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if_six = if_six_star
        try:
            await push_notification(
                "统计信息",
                f"{datetime.now().strftime('%m-%d')} |  {self.user_item.info.name} 的自动代理统计报告",
                merged,
                self.user_entry,
            )
        except Exception as e:
            logger.warning(f"推送统计通知失败: {e}")
        if if_six:
            try:
                await push_notification(
                    "公招六星",
                    f"喜报: 用户 {self.user_item.info.name} 公招出六星啦！",
                    {"user_name": self.user_item.info.name},
                    self.user_entry,
                )
            except Exception as e:
                logger.warning(f"推送六星通知失败: {e}")
'''
        text = text.rstrip() + tail

    text = text.replace("from ..tools import (\n    agree_bilibili,\n    ensure_game_updated,\n    log_statistics,\n    push_notification,\n    update_maa,\n)", "from ..tools import (\n    agree_bilibili,\n    ensure_game_updated,\n    update_maa,\n)")

    DST.write_text(text, encoding="utf-8")
    print("fixed", DST)

if __name__ == "__main__":
    main()
