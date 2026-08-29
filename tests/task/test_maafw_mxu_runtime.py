import json
import tempfile
from types import SimpleNamespace
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
        # 写运行配置时会顺手关掉外壳自更新，需要项目根定位 interface.json。
        self.manager.project_root = self.root
        self.manager.backup_path = self.root / "no-backup"
        self.manager.controller_name = "Android"
        self.manager.resource_name = "官服3"
        self.manager.task_selections = [TaskSelection(name="打开游戏")]
        self.manager.mxu_instance_id = None
        self.manager.emulator_info = None

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


class MxuSavedDeviceTest(unittest.TestCase):
    """MXU 的设备匹配是地址优先、名字兜底，本层必须写地址。

    MistEO/MXU src/utils/controller.ts 的 findMatchingAdbDevice 注释原文：
    「ADB 地址优先，兼容旧配置按名称匹配」。只继承老配置里的 adbDeviceName，
    外壳一换版本改了命名就再也匹配不上 —— 2026-08-29 真机实测：外壳扫到
    `ldplayer-LDPlayer`，继承来的是 `雷电模拟器-LDPlayer`，「未找到设备」。
    """

    def setUp(self) -> None:
        self.manager = MaaFWManager.__new__(MaaFWManager)
        self.manager.emulator_info = SimpleNamespace(adb_address="emulator-5554")

    def test_writes_the_address_and_drops_the_stale_name(self) -> None:
        """名字必须清掉，留着就是硬失败。

        旧版外壳没有 adbDeviceAddress，只按名字匹配且命中唯一才连；而外壳里的
        设备名由 MaaFramework 枚举生成（ldplayer-LDPlayer），本层不加载 MaaFW DLL，
        复现不了也不猜。清掉后旧版外壳退化成「自动选第一个设备」，而本层刚把目标
        模拟器起起来；新版外壳则靠地址精确匹配。
        """

        base = {"savedDevice": {"adbDeviceName": "雷电模拟器-LDPlayer"}}
        self.manager._apply_mxu_saved_device(base)
        self.assertEqual(base["savedDevice"]["adbDeviceAddress"], "emulator-5554")
        self.assertNotIn("adbDeviceName", base["savedDevice"])

    def test_creates_saved_device_when_absent(self) -> None:
        base = {}
        self.manager._apply_mxu_saved_device(base)
        self.assertEqual(base["savedDevice"], {"adbDeviceAddress": "emulator-5554"})

    def test_does_not_touch_other_base_fields(self) -> None:
        base = {"id": "keep", "tasks": [{"taskName": "x"}], "savedDevice": {"a": 1}}
        self.manager._apply_mxu_saved_device(base)
        self.assertEqual(base["id"], "keep")
        self.assertEqual(base["tasks"], [{"taskName": "x"}])
        # savedDevice 里除设备标识外的键原样保留。
        self.assertEqual(base["savedDevice"]["a"], 1)

    def test_no_emulator_leaves_base_untouched(self) -> None:
        # Win32 / PlayCover 等没有 adb 地址的控制方式原样跳过。
        for info in (None, SimpleNamespace(adb_address=""), SimpleNamespace(adb_address="Unknown")):
            with self.subTest(info=info):
                self.manager.emulator_info = info
                base = {"savedDevice": {"adbDeviceName": "x"}}
                self.manager._apply_mxu_saved_device(base)
                self.assertNotIn("adbDeviceAddress", base["savedDevice"])


class MxuInstanceUpsertTest(unittest.TestCase):
    """同名实例必须就地替换，不能越追加越多。

    MXU 的 `--instance` 按**显示名**匹配，重名时取先出现的那个。MAS 每轮都用
    固定名 MAS 追加实例，只要上一轮的残留还在，外壳匹配到的就是旧那个，跑的是
    上一轮的任务 —— 2026-08-29 真机实测：MAS 选的是 CreditShoppingN2，外壳却跑了
    残留实例里的 SellProduct，外壳日志里的实例 id 正是那个残留 id。
    """

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name) / "project"
        (self.root / "config").mkdir(parents=True)
        self.container = self.root / "config" / "mxu-Demo.json"
        # 容器里已经躺着一个上一轮留下的同名实例，任务是旧的。
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
                },
                {
                    "id": "stale-mas",
                    "name": manager_module._MXU_INSTANCE_NAME,
                    "controllerName": "Android",
                    "resourceName": "官服3",
                    "tasks": [{"id": "t9", "taskName": "寮三十捐材料", "enabled": True}],
                },
            ],
            "settings": {"autoRunOnLaunch": False},
            "lastActiveInstanceId": "keepme",
        }
        self.container.write_text(
            json.dumps(self.original, ensure_ascii=False), encoding="utf-8"
        )

        self.manager = MaaFWManager.__new__(MaaFWManager)
        self.manager.shell_family = ShellFamily.MXU
        self.manager.interface_model = _interface()
        self.manager.mxu_container_path = self.container
        self.manager.project_root = self.root
        self.manager.backup_path = self.root / "no-backup"
        self.manager.controller_name = "Android"
        self.manager.resource_name = "官服3"
        self.manager.task_selections = [TaskSelection(name="打开游戏")]
        self.manager.mxu_instance_id = None
        self.manager.emulator_info = None

    def _written(self) -> dict:
        return json.loads(self.container.read_text(encoding="utf-8"))

    def test_same_name_instance_is_replaced_not_duplicated(self) -> None:
        self.manager._write_runtime_config()
        written = self._written()

        named = [
            i
            for i in written["instances"]
            if i["name"] == manager_module._MXU_INSTANCE_NAME
        ]
        # 只能有一个候选，否则 --instance 会匹配到旧的那个。
        self.assertEqual(len(named), 1)
        self.assertEqual(len(written["instances"]), 2)
        self.assertEqual([t["taskName"] for t in named[0]["tasks"]], ["打开游戏"])

    def test_replacement_keeps_the_old_id(self) -> None:
        # 外壳的 lastActiveInstanceId 与每实例日志都按 id 索引，换 id 会每轮失联。
        self.manager._write_runtime_config()
        written = self._written()
        named = next(
            i
            for i in written["instances"]
            if i["name"] == manager_module._MXU_INSTANCE_NAME
        )
        self.assertEqual(named["id"], "stale-mas")
        self.assertEqual(written["lastActiveInstanceId"], "stale-mas")

    def test_user_instances_are_untouched(self) -> None:
        self.manager._write_runtime_config()
        written = self._written()
        kept = next(i for i in written["instances"] if i["id"] == "keepme")
        self.assertEqual(kept, self.original["instances"][0])

    def test_repeated_runs_do_not_grow_the_container(self) -> None:
        for _ in range(3):
            self.manager._write_runtime_config()
        self.assertEqual(len(self._written()["instances"]), 2)


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
    """任务的**任何一种写法**命中即算露过面。

    外壳按自己的界面语言打任务名，落盘的调试行又打 entry，而 MAS 手里存的是
    interface 里的 name —— 四者互不相同。只认一种，换个界面语言就会把跑成功的
    运行误判成「选中任务未出现」（2026-08-29 真机实测，外壳跑的是英文界面：
    `Task started: 🛍️ Credit Shopping`）。
    """

    def setUp(self) -> None:
        self.manager = MaaFWManager.__new__(MaaFWManager)
        self.manager.shell_family = ShellFamily.MXU
        self.manager.interface_model = _interface()
        self.manager.project_root = Path("C:/proj")
        self.manager.task_selections = [TaskSelection(name="打开游戏")]
        self.manager._alias_index = {}
        self.manager._alias_index_token = None
        self._patch = patch.object(
            manager_module,
            "build_task_alias_index",
            return_value={"打开游戏": ("打开游戏", "启动游戏", "🎮 Open Game")},
        )
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def test_entry_in_log_counts_as_present(self) -> None:
        log = "2026-07-04 10:25:44 DEBUG [MAA]   任务[0]: entry=启动游戏\n"
        self.assertEqual(self.manager._selected_tasks_absent(log), [])

    def test_localized_label_counts_as_present(self) -> None:
        # 外壳跑英文界面时日志里只有这一种写法，name 和 entry 都不出现。
        log = "[2026-08-29 21:30:30.345] Task started: 🎮 Open Game\n"
        self.assertEqual(self.manager._selected_tasks_absent(log), [])

    def test_absent_when_no_alias_appears(self) -> None:
        log = "[2026-08-29 21:30:30.345] Task started: Credit Shopping\n"
        self.assertEqual(self.manager._selected_tasks_absent(log), ["打开游戏"])

    def test_display_name_also_accepted(self) -> None:
        log = "任务：打开游戏\n"
        self.assertEqual(self.manager._selected_tasks_absent(log), [])

    def test_falls_back_to_the_name_when_aliases_cannot_be_built(self) -> None:
        # 语言文件缺失 / interface 读不到时不能静默放行，退回只比任务名。
        self._patch.stop()
        try:
            with patch.object(
                manager_module, "build_task_alias_index", side_effect=OSError("boom")
            ):
                self.manager._alias_index_token = None
                self.assertEqual(self.manager._selected_tasks_absent("任务：打开游戏"), [])
                self.manager._alias_index_token = None
                self.assertEqual(
                    self.manager._selected_tasks_absent("Task started: x"), ["打开游戏"]
                )
        finally:
            self._patch.start()


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
        self.manager.log_monitor = SimpleNamespace(
            time_start=1, time_end=24, time_format="%Y-%m-%d %H:%M:%S.%f"
        )

    def _await_path(self):
        import asyncio as _asyncio

        async def _no_sleep(_delay):
            return None

        with patch.object(manager_module.asyncio, "sleep", _no_sleep), patch.object(
            manager_module, "_SHELL_LOG_WAIT_SECONDS", 0
        ):
            return _asyncio.run(self.manager._await_shell_log_path())

    def test_picks_the_frontend_log_when_stdout_is_unavailable(self) -> None:
        """判据串只出现在前端那份 debug/<日期>-<序号>.log 里。

        debug/mxu-tauri.log 是 Rust 后端经 tauri-plugin-log 写的，只有启动、
        web_server、MaaFramework 加载那类行 —— 盯着它会永远等不到任务标记。
        两份文件同时存在时（后端那份是常态，前端启动时的 auto-clear 才会删它）
        必须选前端那份。
        """

        from datetime import datetime

        today = datetime.now().strftime("%Y-%m-%d")
        (self.root / "debug" / "mxu-tauri.log").write_text("x", encoding="utf-8")
        for name in (
            f"{today}-1.log",
            f"{today}-2.log",
            "maafw.log",
            "mxu-agent-0-19728.log",
        ):
            (self.root / "debug" / name).write_text("x", encoding="utf-8")
        resolved = self._await_path()
        self.assertIsNotNone(resolved)
        # 当日启动序号最大的那份才是本轮的。
        self.assertEqual(resolved.name, f"{today}-2.log")
        # 落到文件就得换成文件那套切片，否则一行都解析不出来。
        self.assertEqual(
            (
                self.manager.log_monitor.time_start,
                self.manager.log_monitor.time_end,
                self.manager.log_monitor.time_format,
            ),
            (0, 19, "%Y-%m-%d %H:%M:%S"),
        )

    def test_backend_log_is_never_picked(self) -> None:
        """mxu-tauri.log 是 Rust 后端日志，一条任务判据串都没有，不能选它。"""

        (self.root / "debug" / "mxu-tauri.log").write_text("x", encoding="utf-8")
        self.assertIsNone(self._await_path())

    def test_returns_none_when_nothing_matches(self) -> None:
        (self.root / "debug" / "2000-01-01-1.log").write_text("x", encoding="utf-8")
        self.assertIsNone(self._await_path())

    def test_stdout_and_file_slices_do_not_cross(self) -> None:
        """首选切片对 stdout 行，兜底切片对日志文件行，两边不能串。"""

        from datetime import datetime

        from app.task.MaaFW.tools.external.profile import MXU_LOG_PROFILE

        stdout_line = "[2026-08-29 20:39:22.123] 任务开始: CreditShoppingN2"
        start, end = MXU_LOG_PROFILE.time_stamp_range
        self.assertEqual(
            datetime.strptime(stdout_line[start:end], MXU_LOG_PROFILE.time_format),
            datetime(2026, 8, 29, 20, 39, 22, 123000),
        )

        file_line = "2026-08-29 19:56:31 INFO  [Task] 实例 MAS: 开始执行任务, 数量: 1"
        start, end = MXU_LOG_PROFILE.fallback_time_stamp_range
        self.assertEqual(
            datetime.strptime(file_line[start:end], MXU_LOG_PROFILE.fallback_time_format),
            datetime(2026, 8, 29, 19, 56, 31),
        )


class UnknownShellRejectionTest(unittest.TestCase):
    """未登记家族是能力边界，不是故障。"""

    def test_message_names_the_supported_families(self) -> None:
        from app.task.MaaFW.tools.external.profile import get_shell_log_profile

        self.assertIsNone(get_shell_log_profile(ShellFamily.UNKNOWN))
        self.assertIsNotNone(get_shell_log_profile(ShellFamily.MXU))
        self.assertIsNotNone(get_shell_log_profile(ShellFamily.MFAAVALONIA))


if __name__ == "__main__":
    unittest.main()
