import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app.core  # noqa: F401

from app.task.MaaFW import manager as manager_module
from app.task.MaaFW.manager import MaaFWManager
from app.task.MaaFW.tools.core.automas_maafw_interface.models import (
    MaaFWController,
    MaaFWInterface,
    MaaFWResource,
    MaaFWTask,
)
from app.task.MaaFW.tools.external.models import TaskSelection
from app.task.MaaFW.tools.external.shell import ShellFamily


def _interface() -> MaaFWInterface:
    """MXU 项目的最小 interface：**name 与 entry 刻意不同**。

    实测 MaaYYs 只有 10/27、MaaEnd 只有 6/41 的 name==entry，而 MXU 的 UI 日志
    打的是 entry —— 这正是显示名匹配会全线误判的原因。
    """

    return MaaFWInterface(
        interface_version=2,
        name="mxu-project",
        controller=[MaaFWController(name="Android", type="Adb")],
        resource=[MaaFWResource(name="官服3")],
        task=[
            MaaFWTask(name="打开游戏", entry="启动游戏"),
            MaaFWTask(name="寮三十捐材料", entry="寮三十-开始任务"),
        ],
    )


class MxuRuntimeConfigTest(unittest.TestCase):
    """MXU 运行配置：追加而非删除，且清掉继承来的 preActions。"""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name) / "project"
        (self.root / "config").mkdir(parents=True)
        self.container = self.root / "config" / "mxu-Demo.json"
        self.original = {
            "version": "1.0",
            "instances": [
                {
                    "id": "keepme",
                    "name": "用户配置",
                    "controllerName": "Android",
                    "resourceName": "官服3",
                    "tasks": [{"id": "t1", "taskName": "打开游戏", "enabled": True}],
                    "savedDevice": {"adbDeviceName": "雷电模拟器-LDPlayer"},
                    "preActions": [
                        {"id": "p1", "enabled": True, "program": "C:/game/game.exe"}
                    ],
                }
            ],
            "settings": {"autoRunOnLaunch": False},
            "customAccents": [],
            "lastActiveInstanceId": "keepme",
        }
        self.container.write_text(
            json.dumps(self.original, ensure_ascii=False), encoding="utf-8"
        )

        self.manager = MaaFWManager.__new__(MaaFWManager)
        self.manager.shell_family = ShellFamily.MXU
        self.manager.interface_model = _interface()
        self.manager.mxu_container_path = self.container
        self.manager.backup_path = self.root / "no-backup"
        self.manager.controller_name = "Android"
        self.manager.resource_name = "官服3"
        self.manager.task_selections = [TaskSelection(name="打开游戏")]
        self.manager.mxu_instance_id = None

    def _written(self) -> dict:
        return json.loads(self.container.read_text(encoding="utf-8"))

    def test_appends_without_touching_existing(self) -> None:
        self.manager._write_runtime_config()
        written = self._written()

        self.assertEqual(len(written["instances"]), 2)
        kept = next(i for i in written["instances"] if i["id"] == "keepme")
        self.assertEqual(kept, self.original["instances"][0])
        # 其余顶层键零触碰。
        self.assertEqual(written["customAccents"], [])
        self.assertEqual(written["version"], "1.0")

    def test_new_instance_is_active_and_named_for_the_cli(self) -> None:
        self.manager._write_runtime_config()
        written = self._written()

        new = next(i for i in written["instances"] if i["id"] != "keepme")
        self.assertEqual(written["lastActiveInstanceId"], new["id"])
        # -i 按显示名匹配，名字必须与 manager 传给命令行的一致。
        self.assertEqual(new["name"], manager_module._MXU_INSTANCE_NAME)

    def test_inherits_saved_device_but_drops_pre_actions(self) -> None:
        self.manager._write_runtime_config()
        new = next(i for i in self._written()["instances"] if i["id"] != "keepme")

        # savedDevice 要继承——MXU 的设备按名存，不继承就没有连接目标。
        self.assertEqual(new["savedDevice"], {"adbDeviceName": "雷电模拟器-LDPlayer"})
        # preActions 必须清掉：那是外壳自己的「起程序」钩子，继承下来外壳会
        # 重复启动游戏，与 MFAAvalonia 路径靠 SoftwarePath="" 防的是同一类问题。
        self.assertNotIn("preActions", new)


class MxuLaunchArgvTest(unittest.TestCase):
    """MXU 的自动执行只认命令行。"""

    def _manager(self, family: ShellFamily) -> MaaFWManager:
        manager = MaaFWManager.__new__(MaaFWManager)
        manager.shell_family = family
        manager.exe_path = Path("C:/proj/mxu.exe")
        manager.instance_path = Path("C:/proj/config/instances/adbe33bf.json")
        return manager

    def test_mxu_uses_autostart_named_instance_and_quit(self) -> None:
        argv = self._manager(ShellFamily.MXU)._build_launch_argv()
        self.assertEqual(
            argv[1:],
            ["--autostart", "-i", manager_module._MXU_INSTANCE_NAME, "-q"],
        )

    def test_mfaavalonia_keeps_instance_only(self) -> None:
        argv = self._manager(ShellFamily.MFAAVALONIA)._build_launch_argv()
        # 回归守护：--autostart 一旦被加回 MFAAvalonia，外壳会跳过设备恢复。
        self.assertEqual(argv[1:], ["--instance", "adbe33bf"])
        self.assertNotIn("--autostart", argv)


class MxuSelectedTaskProbeTest(unittest.TestCase):
    """MXU 按 entry 判「选中任务露过面」，不按显示名。"""

    def setUp(self) -> None:
        self.manager = MaaFWManager.__new__(MaaFWManager)
        self.manager.shell_family = ShellFamily.MXU
        self.manager.interface_model = _interface()
        self.manager.task_selections = [TaskSelection(name="打开游戏")]

    def test_entry_in_log_counts_as_present(self) -> None:
        log = "2026-07-04 10:25:44 DEBUG [MAA]   任务[0]: entry=启动游戏\n"
        self.assertEqual(self.manager._selected_tasks_absent(log), [])

    def test_absent_when_neither_entry_nor_name_appears(self) -> None:
        log = "2026-07-04 10:25:44 INFO  [Task] 实例 MAS: 开始执行任务, 数量: 1\n"
        self.assertEqual(self.manager._selected_tasks_absent(log), ["打开游戏"])

    def test_display_name_also_accepted(self) -> None:
        # 有些项目 name 与 entry 相同，或外壳另打了显示名，两者命中其一即算露面。
        log = "任务：打开游戏\n"
        self.assertEqual(self.manager._selected_tasks_absent(log), [])


class MxuLogPathTest(unittest.TestCase):
    """MXU 日志文件名带当日启动序号，必须起进程之后再解析。"""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name)
        (self.root / "debug").mkdir()
        self.manager = MaaFWManager.__new__(MaaFWManager)
        self.manager.shell_family = ShellFamily.MXU
        self.manager.project_root = self.root
        from app.task.MaaFW.tools.external.profile import MXU_LOG_PROFILE

        self.manager.log_profile = MXU_LOG_PROFILE

    def test_pre_launch_path_is_unknown(self) -> None:
        self.assertIsNone(self.manager._resolve_log_path())

    def test_picks_todays_latest_sequence(self) -> None:
        from datetime import datetime

        today = datetime.now().strftime("%Y-%m-%d")
        for name in (
            f"{today}-1.log",
            f"{today}-2.log",
            "maafw.log",
            "mxu-agent-0-19728.log",
        ):
            (self.root / "debug" / name).write_text("x", encoding="utf-8")
        resolved = self.manager._resolve_mxu_log_path()
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.name, f"{today}-2.log")

    def test_returns_none_when_no_log_for_today(self) -> None:
        (self.root / "debug" / "2000-01-01-1.log").write_text("x", encoding="utf-8")
        self.assertIsNone(self.manager._resolve_mxu_log_path())


class UnknownShellRejectionTest(unittest.TestCase):
    """未登记家族是能力边界，不是故障。"""

    def test_message_names_the_supported_families(self) -> None:
        from app.task.MaaFW.tools.external.profile import get_shell_log_profile

        self.assertIsNone(get_shell_log_profile(ShellFamily.UNKNOWN))
        self.assertIsNotNone(get_shell_log_profile(ShellFamily.MXU))
        self.assertIsNotNone(get_shell_log_profile(ShellFamily.MFAAVALONIA))


if __name__ == "__main__":
    unittest.main()
