import copy
import tempfile
import unittest
from pathlib import Path

import app.core

from app.task.MaaFW.tools.core.automas_maafw_interface import MaaFWInterface
from app.task.MaaFW.tools.external.models import ShellMappingError, TaskSelection
from app.task.MaaFW.tools.external.mxu import (
    append_instance,
    build_instance_entry,
    build_interface_task_snapshot,
    build_task_entries,
    default_instance_id,
)
from app.task.MaaFW.tools.external.shell import ShellFamily, detect_shell_family

# ---------------------------------------------------------------------------
# fixture 内容来源：两个真实 MXU 项目的 interface.json（裁剪精简版）
#   D:/MAS/reference/MaaEnd-win-x86_64-v1.16.0-beta.1/interface.json
#     controller: Win32-Front / ADB / CloudADB / PlayCover / MacOS-Front，resource: 官服
#   D:/MAS/reference/MaaYYs-win-x86_64-v3.10.2/interface.json
#     controller: Android，resource: 官服(雷电,mumu下载的选这个) / 官服2 / bilibili服 ...
# 两个项目的 task[] 全部经 import 引入，interface 本体内联 0 个 task，
# 这里内联少量 task（Chinese name + English entry 是 MaaYYs 的真实形态）用于映射断言。
# ---------------------------------------------------------------------------

MAAEND_INTERFACE = {
    "interface_version": 2,
    "name": "MaaEnd",
    "version": "v2.22.0",
    "controller": [
        {
            "name": "Win32-Front",
            "type": "Win32",
            "win32": {"class_regex": "UnityWndClass", "window_regex": "Endfield"},
            "permission_required": True,
        },
        {"name": "ADB", "type": "Adb", "attach_resource_path": ["./resource_adb"]},
        {"name": "CloudADB", "type": "Adb", "option": ["ClientVersionCloudLocked"]},
        {"name": "PlayCover", "type": "PlayCover", "playcover": {"uuid": "maa.playcover"}},
        {"name": "MacOS-Front", "type": "MacOS"},
    ],
    "resource": [
        {"name": "官服", "path": ["./resource"], "hash": "1b9d9bfb7cc532e"},
    ],
    "task": [
        {"name": "ReceiveProdManual", "entry": "ReceiveProdManual"},
        {"name": "BakerEntry", "entry": "BakerEntry"},
        {
            "name": "EssenceFilter",
            "entry": "EssenceFilter",
            "option": ["SelectInputLanguage"],
        },
        {"name": "SellProduct", "entry": "SellProduct", "group": ["valuables_vault"]},
    ],
}

MAAYYS_INTERFACE = {
    "interface_version": 2,
    "name": "MaaYYs",
    "label": "阴阳师",
    "version": "v3.10.2",
    "controller": [
        {
            "name": "Android",
            "label": "安卓设备",
            "type": "Adb",
            "description": "通过ADB连接的安卓设备",
        },
    ],
    "resource": [
        {
            "name": "官服(雷电,mumu下载的选这个)",
            "label": "官服",
            "path": ["./resource_pack/base", "./resource_pack/official"],
        },
        {"name": "官服2", "label": "官服2", "path": ["./resource_pack/base"]},
        {
            "name": "bilibili服",
            "label": "B站服",
            "path": ["./resource_pack/base", "./resource_pack/bilibili"],
        },
    ],
    "task": [
        {"name": "打开游戏", "entry": "OpenGame"},
        {"name": "关闭游戏", "entry": "CloseGame"},
        {"name": "式神委派", "entry": "AutoCommission", "option": ["委派数量"]},
    ],
}


def maaend_model() -> MaaFWInterface:
    return MaaFWInterface.model_validate(MAAEND_INTERFACE)


def maayys_model() -> MaaFWInterface:
    return MaaFWInterface.model_validate(MAAYYS_INTERFACE)


def counter_ids(*names: str):
    """按给定序列逐个返回 id 的可注入生成器。"""
    seq = iter(names)
    return lambda: next(seq)


# ---------------------------------------------------------------------------
# 1. 跨项目通用性：同一套映射代码对两个真实项目都产出正确结果
# ---------------------------------------------------------------------------
class CrossProjectMxuMappingTest(unittest.TestCase):
    def test_maaend_controller_resource_task(self) -> None:
        entry = build_instance_entry(
            maaend_model(),
            controller_name="Win32-Front",
            resource_name="官服",
            selected_tasks=[TaskSelection("ReceiveProdManual")],
            name="配置 1",
            id_factory=counter_ids("i-maaend", "t-0"),
        )
        self.assertEqual(entry["controllerName"], "Win32-Front")
        self.assertEqual(entry["resourceName"], "官服")
        self.assertEqual(entry["name"], "配置 1")
        self.assertEqual(entry["id"], "i-maaend")
        self.assertEqual([t["taskName"] for t in entry["tasks"]], ["ReceiveProdManual"])

    def test_maayys_controller_resource_task(self) -> None:
        entry = build_instance_entry(
            maayys_model(),
            controller_name="Android",
            resource_name="官服2",
            selected_tasks=[TaskSelection("打开游戏")],
            id_factory=counter_ids("i-maayys", "t-0"),
        )
        self.assertEqual(entry["controllerName"], "Android")
        self.assertEqual(entry["resourceName"], "官服2")
        self.assertEqual([t["taskName"] for t in entry["tasks"]], ["打开游戏"])

    def test_same_code_path_both_projects(self) -> None:
        cases = [
            (maaend_model(), "ADB", "官服", "ReceiveProdManual"),
            (maaend_model(), "Win32-Front", "官服", "SellProduct"),
            (maayys_model(), "Android", "bilibili服", "关闭游戏"),
            (maayys_model(), "Android", "官服(雷电,mumu下载的选这个)", "式神委派"),
        ]
        for interface, controller_name, resource_name, task_name in cases:
            with self.subTest(controller=controller_name, resource=resource_name):
                entry = build_instance_entry(
                    interface,
                    controller_name=controller_name,
                    resource_name=resource_name,
                    selected_tasks=[TaskSelection(task_name)],
                    id_factory=counter_ids("i", "t"),
                )
                self.assertEqual(entry["controllerName"], controller_name)
                self.assertEqual(entry["resourceName"], resource_name)
                self.assertEqual(entry["tasks"][0]["taskName"], task_name)


# ---------------------------------------------------------------------------
# 2. 追加不破坏：原有实例逐字段不变、数量 +1、lastActiveInstanceId 指向新实例
# ---------------------------------------------------------------------------
def _container_with_existing() -> dict:
    return {
        "version": "1.0",
        "customAccents": [],
        "settings": {"theme": "light", "webServerPort": 12701},
        "interfaceTaskSnapshot": ["ReceiveProdManual", "BakerEntry"],
        "newTaskNames": [],
        "recentlyClosed": [{"id": "closed1", "name": "已关闭"}],
        "lastActiveInstanceId": "keep-2",
        "instances": [
            {
                "id": "keep-1",
                "name": "全套日常",
                "controllerName": "Win32-Front",
                "resourceName": "官服",
                "preActions": [
                    {
                        "id": "pa-1",
                        "customName": "启动 Endfield.exe",
                        "enabled": False,
                        "program": "D:\\games\\Endfield.exe",
                    }
                ],
                "savedDevice": {
                    "windowName": "Endfield",
                    "connectedProgramPath": "D:\\games\\Endfield.exe",
                },
                "tasks": [
                    {
                        "id": "tk-1",
                        "taskName": "SellProduct",
                        "enabled": True,
                        "enabledByController": {"Win32-Front": True},
                        "optionValues": {"X": {"type": "switch", "value": True}},
                    }
                ],
            },
            {
                "id": "keep-2",
                "name": "配置 2",
                "controllerName": "",
                "resourceName": "官服",
                "tasks": [],
            },
            {
                "id": "keep-3",
                "name": "配置 3",
                "controllerName": "ADB",
                "resourceName": "官服",
                "savedDevice": {"adbDeviceName": "雷电模拟器-LDPlayer"},
                "tasks": [],
            },
        ],
    }


class AppendInstanceTest(unittest.TestCase):
    def test_append_preserves_existing_instances_and_sets_active(self) -> None:
        container = _container_with_existing()
        original_instances = copy.deepcopy(container["instances"])

        new_entry = build_instance_entry(
            maaend_model(),
            controller_name="Win32-Front",
            resource_name="官服",
            selected_tasks=[TaskSelection("BakerEntry")],
            name="新增配置",
            id_factory=counter_ids("brand-new", "tk-new"),
        )
        out = append_instance(container, new_entry)

        self.assertEqual(len(out["instances"]), 4)
        for i, before in enumerate(original_instances):
            self.assertEqual(out["instances"][i], before)
        self.assertEqual(out["instances"][3]["id"], "brand-new")
        self.assertEqual(out["lastActiveInstanceId"], "brand-new")
        # 容器其它键原样保留
        self.assertEqual(out["settings"], container["settings"])
        self.assertEqual(out["recentlyClosed"], container["recentlyClosed"])
        self.assertEqual(out["interfaceTaskSnapshot"], container["interfaceTaskSnapshot"])

    def test_append_without_set_active_keeps_previous_active(self) -> None:
        container = _container_with_existing()
        new_entry = build_instance_entry(
            maaend_model(), instance_id="x1", id_factory=counter_ids()
        )
        out = append_instance(container, new_entry, set_active=False)
        self.assertEqual(out["lastActiveInstanceId"], "keep-2")
        self.assertEqual(len(out["instances"]), 4)

    def test_append_into_container_without_instances_key(self) -> None:
        out = append_instance(
            {"version": "1.0"},
            build_instance_entry(maaend_model(), instance_id="only-1"),
        )
        self.assertEqual([i["id"] for i in out["instances"]], ["only-1"])
        self.assertEqual(out["lastActiveInstanceId"], "only-1")

    def test_append_rejects_duplicate_instance_id(self) -> None:
        container = _container_with_existing()
        clash = build_instance_entry(maaend_model(), instance_id="keep-2")
        with self.assertRaises(ShellMappingError):
            append_instance(container, clash)


# ---------------------------------------------------------------------------
# 3. 不修改入参：容器 dict 与 base dict 调用后保持原样
# ---------------------------------------------------------------------------
class NoInputMutationTest(unittest.TestCase):
    def test_append_does_not_mutate_container_or_instance(self) -> None:
        container = _container_with_existing()
        container_snapshot = copy.deepcopy(container)
        instance = build_instance_entry(maaend_model(), instance_id="new-x")
        instance_snapshot = copy.deepcopy(instance)

        append_instance(container, instance)

        self.assertEqual(container, container_snapshot)
        self.assertEqual(instance, instance_snapshot)

    def test_build_instance_entry_does_not_mutate_base_or_option_values(self) -> None:
        base = {
            "id": "b1",
            "name": "配置 1",
            "controllerName": "Win32-Front",
            "resourceName": "官服",
            "preActions": [{"id": "pa", "enabled": False}],
            "savedDevice": {"windowName": "Endfield"},
            "tasks": [],
        }
        base_snapshot = copy.deepcopy(base)
        option_values = {"SelectInputLanguage": {"type": "select", "caseName": "CN"}}
        option_snapshot = copy.deepcopy(option_values)

        build_instance_entry(
            maaend_model(),
            resource_name="官服",
            selected_tasks=[
                TaskSelection("EssenceFilter", option_values=option_values)
            ],
            base=base,
            id_factory=counter_ids("tk-0"),
        )

        self.assertEqual(base, base_snapshot)
        self.assertEqual(option_values, option_snapshot)


# ---------------------------------------------------------------------------
# 4. base 覆盖语义：未涉及字段（preActions / savedDevice 等）被保留
# ---------------------------------------------------------------------------
class BaseOverlayTest(unittest.TestCase):
    def _base(self) -> dict:
        return {
            "id": "orig-id",
            "name": "原名",
            "controllerName": "Win32-Front",
            "resourceName": "官服",
            "preActions": [
                {
                    "id": "pa-1",
                    "customName": "启动游戏",
                    "enabled": True,
                    "program": "C:\\Endfield.exe",
                    "skipIfRunning": True,
                }
            ],
            "savedDevice": {
                "windowName": "Endfield",
                "connectedProgramPath": "C:\\Endfield.exe",
            },
            "tasks": [{"id": "old-tk", "taskName": "BakerEntry", "enabled": True}],
        }

    def test_untouched_fields_preserved(self) -> None:
        base = self._base()
        entry = build_instance_entry(
            maayys_model(),
            resource_name=None,  # 不动 base
            base=base,
        )
        # 未涉及字段原样保留
        self.assertEqual(entry["preActions"], base["preActions"])
        self.assertEqual(entry["savedDevice"], base["savedDevice"])
        self.assertEqual(entry["id"], "orig-id")
        self.assertEqual(entry["name"], "原名")
        self.assertEqual(entry["controllerName"], "Win32-Front")
        self.assertEqual(entry["resourceName"], "官服")
        # selected_tasks 未给 -> base 的 tasks 不动
        self.assertEqual(entry["tasks"], base["tasks"])

    def test_overlay_updates_only_given_fields(self) -> None:
        base = self._base()
        entry = build_instance_entry(
            maaend_model(),
            resource_name="官服",
            selected_tasks=[TaskSelection("SellProduct", checked=False)],
            base=base,
            id_factory=counter_ids("tk-new"),
        )
        # 覆盖了 tasks
        self.assertEqual([t["taskName"] for t in entry["tasks"]], ["SellProduct"])
        self.assertFalse(entry["tasks"][0]["enabled"])
        # 但 preActions / savedDevice / id / name 仍是 base 的
        self.assertEqual(entry["preActions"], base["preActions"])
        self.assertEqual(entry["savedDevice"], base["savedDevice"])
        self.assertEqual(entry["id"], "orig-id")
        self.assertEqual(entry["name"], "原名")


# ---------------------------------------------------------------------------
# 5. task 条目结构：taskName 正确、enabled 反映选择、不产出 entry 字段
# ---------------------------------------------------------------------------
class TaskEntryStructureTest(unittest.TestCase):
    def test_task_name_only_never_entry(self) -> None:
        model = maayys_model()
        # 源模型里 entry 是有值的
        self.assertEqual(model.task[0].entry, "OpenGame")

        entries = build_task_entries(
            model,
            [TaskSelection("打开游戏", checked=True), TaskSelection("关闭游戏", checked=False)],
            id_factory=counter_ids("a", "b"),
        )
        self.assertEqual(entries[0]["taskName"], "打开游戏")
        self.assertEqual(entries[1]["taskName"], "关闭游戏")
        self.assertTrue(entries[0]["enabled"])
        self.assertFalse(entries[1]["enabled"])
        for e in entries:
            self.assertNotIn("entry", e)
            self.assertIn("optionValues", e)
            self.assertEqual(e["optionValues"], {})

    def test_entry_field_absent_in_full_instance_output(self) -> None:
        entry = build_instance_entry(
            maaend_model(),
            controller_name="Win32-Front",
            resource_name="官服",
            selected_tasks=[
                TaskSelection("ReceiveProdManual"),
                TaskSelection("BakerEntry", checked=False),
            ],
            id_factory=counter_ids("i", "t1", "t2"),
        )
        for t in entry["tasks"]:
            self.assertNotIn("entry", t)

    def test_option_values_passthrough_and_custom_name(self) -> None:
        ov = {"SelectInputLanguage": {"type": "select", "caseName": "CN"}}
        (entry,) = build_task_entries(
            maaend_model(),
            [
                TaskSelection(
                    "EssenceFilter",
                    checked=True,
                    option_values=ov,
                    custom_name="过滤基质",
                )
            ],
            id_factory=counter_ids("tk"),
        )
        self.assertEqual(entry["optionValues"], ov)
        self.assertIsNot(entry["optionValues"], ov)  # 深拷贝，非同一引用
        self.assertEqual(entry["customName"], "过滤基质")

    def test_enabled_by_controller_mirrors_enabled_when_controller_set(self) -> None:
        entry = build_instance_entry(
            maaend_model(),
            controller_name="Win32-Front",
            resource_name="官服",
            selected_tasks=[TaskSelection("ReceiveProdManual", checked=True)],
            id_factory=counter_ids("i", "t"),
        )
        self.assertEqual(
            entry["tasks"][0]["enabledByController"], {"Win32-Front": True}
        )

    def test_no_enabled_by_controller_when_controller_empty(self) -> None:
        entry = build_instance_entry(
            maaend_model(),
            controller_name="",
            resource_name="官服",
            selected_tasks=[TaskSelection("ReceiveProdManual")],
            id_factory=counter_ids("i", "t"),
        )
        self.assertEqual(entry["controllerName"], "")
        self.assertNotIn("enabledByController", entry["tasks"][0])

    def test_enabled_by_controller_can_be_disabled(self) -> None:
        entry = build_instance_entry(
            maaend_model(),
            controller_name="Win32-Front",
            resource_name="官服",
            selected_tasks=[TaskSelection("ReceiveProdManual")],
            emit_enabled_by_controller=False,
            id_factory=counter_ids("i", "t"),
        )
        self.assertNotIn("enabledByController", entry["tasks"][0])


# ---------------------------------------------------------------------------
# 6. 未知任务名：选中 interface 中不存在的任务应报错，不静默跳过
# ---------------------------------------------------------------------------
class UnknownNameTest(unittest.TestCase):
    def test_unknown_task_name_raises_not_skipped(self) -> None:
        with self.assertRaises(ShellMappingError):
            build_instance_entry(
                maaend_model(),
                controller_name="Win32-Front",
                resource_name="官服",
                selected_tasks=[TaskSelection("不存在的任务")],
            )

    def test_unknown_task_name_raises_in_build_task_entries(self) -> None:
        with self.assertRaises(ShellMappingError):
            build_task_entries(maayys_model(), [TaskSelection("NoSuchTask")])

    def test_partial_selection_with_one_unknown_still_raises(self) -> None:
        with self.assertRaises(ShellMappingError):
            build_task_entries(
                maaend_model(),
                [TaskSelection("ReceiveProdManual"), TaskSelection("ghost")],
            )

    def test_unknown_controller_name_raises(self) -> None:
        with self.assertRaises(ShellMappingError):
            build_instance_entry(maaend_model(), controller_name="不存在的端")

    def test_unknown_resource_name_raises(self) -> None:
        with self.assertRaises(ShellMappingError):
            build_instance_entry(maayys_model(), resource_name="不存在的服")


# ---------------------------------------------------------------------------
# 附加：id 可注入 / 最小骨架 / interfaceTaskSnapshot / 外壳识别
# ---------------------------------------------------------------------------
class IdInjectionTest(unittest.TestCase):
    def test_explicit_instance_id_wins(self) -> None:
        entry = build_instance_entry(maaend_model(), instance_id="fixed-1")
        self.assertEqual(entry["id"], "fixed-1")

    def test_id_factory_feeds_instance_and_each_task(self) -> None:
        entry = build_instance_entry(
            maaend_model(),
            controller_name="Win32-Front",
            resource_name="官服",
            selected_tasks=[
                TaskSelection("ReceiveProdManual"),
                TaskSelection("BakerEntry"),
            ],
            id_factory=counter_ids("inst", "task-a", "task-b"),
        )
        self.assertEqual(entry["id"], "inst")
        self.assertEqual([t["id"] for t in entry["tasks"]], ["task-a", "task-b"])

    def test_default_instance_id_shape(self) -> None:
        got = default_instance_id()
        self.assertEqual(len(got), 7)
        self.assertTrue(got.isalnum())
        self.assertEqual(got, got.lower())

    def test_minimal_skeleton_without_base(self) -> None:
        entry = build_instance_entry(maaend_model(), instance_id="s1")
        self.assertEqual(
            set(entry),
            {"id", "name", "controllerName", "resourceName", "tasks"},
        )
        self.assertEqual(entry["controllerName"], "")
        self.assertEqual(entry["resourceName"], "")
        self.assertEqual(entry["tasks"], [])
        self.assertEqual(entry["name"], "MAS")


class InterfaceTaskSnapshotTest(unittest.TestCase):
    def test_snapshot_is_task_name_list(self) -> None:
        self.assertEqual(
            build_interface_task_snapshot(maayys_model()),
            ["打开游戏", "关闭游戏", "式神委派"],
        )
        self.assertEqual(
            build_interface_task_snapshot(maaend_model()),
            ["ReceiveProdManual", "BakerEntry", "EssenceFilter", "SellProduct"],
        )


def _touch(root: Path, *names: str) -> None:
    for name in names:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("", encoding="utf-8")


class MxuShellDetectionTest(unittest.TestCase):
    def test_mxu_detected_by_config_glob(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _touch(root, "interface.json", "MaaEnd.exe", "config/mxu-MaaEnd.json")
            self.assertEqual(detect_shell_family(root), ShellFamily.MXU)

    def test_mxu_detection_ignores_exe_name(self) -> None:
        # MaaEnd 的外壳 exe 是 MaaEnd.exe，MaaYYs 的是 mxu.exe，两者同为 MXU。
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _touch(root, "mxu.exe", "config/mxu-MaaYYs.json")
            self.assertEqual(detect_shell_family(root), ShellFamily.MXU)

    def test_config_dir_without_mxu_file_is_not_mxu(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _touch(root, "config/maa_option.json", "interface.json", "main.exe")
            self.assertEqual(detect_shell_family(root), ShellFamily.UNKNOWN)

    def test_mfaavalonia_still_detected_regression_guard(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _touch(root, "MFAAvalonia.dll", "appsettings.json", "interface.json")
            self.assertEqual(detect_shell_family(root), ShellFamily.MFAAVALONIA)

    def test_bare_project_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _touch(root, "interface.json", "main.exe")
            self.assertEqual(detect_shell_family(root), ShellFamily.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
