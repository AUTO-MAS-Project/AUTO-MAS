"""自启与定时唤醒共用的 Windows 任务计划定义及注册。"""

import csv
import getpass
import io
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

from app.utils.common.process import runner


def task_definition(
    *,
    name: str,
    description: str,
    executable: Path,
    arguments: str,
    triggers: list[ET.Element],
    wake_to_run: bool,
) -> ET.Element:
    task = ET.Element(
        "Task",
        version="1.2",
        xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task",
    )
    registration = ET.SubElement(task, "RegistrationInfo")
    ET.SubElement(registration, "Author").text = getpass.getuser()
    ET.SubElement(registration, "Description").text = description
    ET.SubElement(registration, "URI").text = "\\" + name
    ET.SubElement(task, "Triggers").extend(triggers)
    principal = ET.SubElement(
        ET.SubElement(task, "Principals"), "Principal", id="Author"
    )
    ET.SubElement(principal, "LogonType").text = "InteractiveToken"
    ET.SubElement(principal, "RunLevel").text = "HighestAvailable"
    settings = ET.SubElement(task, "Settings")
    for key, value in {
        "MultipleInstancesPolicy": "IgnoreNew",
        "DisallowStartIfOnBatteries": "false",
        "StopIfGoingOnBatteries": "false",
        "AllowHardTerminate": "false",
        "StartWhenAvailable": "false" if wake_to_run else "true",
        "RunOnlyIfNetworkAvailable": "false",
        "AllowStartOnDemand": "true",
        "Enabled": "true",
        "Hidden": "false",
        "RunOnlyIfIdle": "false",
        "WakeToRun": str(wake_to_run).lower(),
        "ExecutionTimeLimit": "PT0S",
        "Priority": "7",
    }.items():
        ET.SubElement(settings, key).text = value
    idle = ET.SubElement(settings, "IdleSettings")
    ET.SubElement(idle, "StopOnIdleEnd").text = "false"
    ET.SubElement(idle, "RestartOnIdle").text = "false"
    action = ET.SubElement(ET.SubElement(task, "Actions", Context="Author"), "Exec")
    ET.SubElement(action, "Command").text = str(executable)
    ET.SubElement(action, "Arguments").text = arguments
    ET.SubElement(action, "WorkingDirectory").text = str(executable.parent)
    return task


async def register_task(name: str, definition: ET.Element) -> None:
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as file:
        path = Path(file.name)
        file.write(ET.tostring(definition, encoding="utf-16", xml_declaration=True))
    try:
        result = await runner.ProcessRunner.run_process(
            "schtasks", "/create", "/tn", name, "/xml", str(path), "/f"
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr or result.stdout)
    finally:
        path.unlink(missing_ok=True)


async def task_exists(name: str) -> bool:
    result = await runner.ProcessRunner.run_process("schtasks", "/query", "/tn", name)
    return result.returncode == 0


async def delete_task(name: str) -> None:
    result = await runner.ProcessRunner.run_process(
        "schtasks", "/delete", "/tn", name, "/f"
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)


async def list_tasks(prefix: str) -> set[str]:
    result = await runner.ProcessRunner.run_process(
        "schtasks", "/query", "/fo", "CSV", "/nh"
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    return {
        row[0].removeprefix("\\")
        for row in csv.reader(io.StringIO(result.stdout))
        if row and row[0].removeprefix("\\").startswith(prefix)
    }
