import hashlib
import os
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

from .scheduled_task import (
    delete_task,
    list_tasks,
    register_task,
    task_definition,
    task_exists,
)


def _powershell_path(path: Path) -> str:
    """保留 PowerShell 引号及任务计划会展开的百分号。"""
    literal = str(path)
    for quote in "'\u2018\u2019\u201a\u201b":
        literal = literal.replace(quote, quote * 2)
    return "('" + literal.replace("%", "' + [char]37 + '") + "')"


class WindowsStartupManager:
    supported = True

    _task_name = "AUTO-MAS_AutoStart"

    async def set_enabled(self, enabled: bool) -> None:
        if enabled:
            from app.core import Config

            trigger = ET.Element("LogonTrigger")
            ET.SubElement(trigger, "Enabled").text = "true"
            await register_task(
                self._task_name,
                task_definition(
                    name=self._task_name,
                    description="AUTO-MAS自启动服务",
                    executable=Config.work_path / "AUTO-MAS.exe",
                    arguments="--auto-start",
                    triggers=[trigger],
                    wake_to_run=False,
                ),
            )
        elif await self.is_enabled():
            await delete_task(self._task_name)

    async def is_enabled(self) -> bool:
        return await task_exists(self._task_name)

    async def sync_wakeup(
        self, *, executable: Path, times: tuple[tuple[int, int, int], ...]
    ) -> None:
        """按本地星期（周一为 0）、时、分对账，空计划移除本安装的唤醒任务。"""
        identifier = hashlib.sha256(
            str(executable.resolve()).casefold().encode()
        ).hexdigest()[:12]
        prefix = f"AUTO-MAS_Wakeup_{identifier}_"
        existing = await list_tasks(prefix)
        days_by_time: dict[tuple[int, int], set[int]] = defaultdict(set)
        for weekday, hour, minute in times:
            days_by_time[hour, minute].add(weekday)

        triggers = []
        weekday_names = (
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        )
        for (hour, minute), days in sorted(days_by_time.items()):
            trigger = ET.Element("CalendarTrigger")
            ET.SubElement(
                trigger, "StartBoundary"
            ).text = f"2000-01-03T{hour:02}:{minute:02}:00"
            ET.SubElement(trigger, "Enabled").text = "true"
            weekly = ET.SubElement(trigger, "ScheduleByWeek")
            ET.SubElement(weekly, "WeeksInterval").text = "1"
            weekdays = ET.SubElement(weekly, "DaysOfWeek")
            for day in sorted(days):
                ET.SubElement(weekdays, weekday_names[day])
            triggers.append(trigger)

        # 通过短暂启动器拉起 GUI；等待定时期间由 GUI 自己申请保活。
        script = (
            "$ErrorActionPreference = 'Stop'; "
            f"Start-Process -FilePath {_powershell_path(executable)} "
            f"-WorkingDirectory {_powershell_path(executable.parent)} "
            "-ArgumentList '--scheduled-wakeup' -WindowStyle Hidden"
        )
        powershell = (
            Path(os.environ.get("SystemRoot", "C:/Windows"))
            / "System32/WindowsPowerShell/v1.0/powershell.exe"
        )
        desired = set()
        # 隐藏窗口与编码命令组合可能被拒绝；保留可读命令和隐藏启动。
        # Windows 每条任务最多 48 个触发器；时间项较多时继续分组，不丢失定时。
        for index in range(0, len(triggers), 48):
            name = f"{prefix}{index // 48}"
            await register_task(
                name,
                task_definition(
                    name=name,
                    description="AUTO-MAS 定时前五分钟唤醒并启动",
                    executable=powershell,
                    arguments=f'-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -Command "{script}"',
                    triggers=triggers[index : index + 48],
                    wake_to_run=True,
                ),
            )
            desired.add(name)
        for name in existing - desired:
            await delete_task(name)


startup = WindowsStartupManager()
