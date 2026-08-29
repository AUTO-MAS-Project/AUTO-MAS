import unittest

import app.core

from app.task.MaaFW.tools.core.automas_maafw_interface import MaaFWInterface
from app.task.MaaFW.tools.external.mfaavalonia import (
    InstanceOrchestration,
    ShellMappingError,
    TaskSelection,
    UnknownControllerTypeError,
    build_current_tasks,
    build_instance_config,
    build_task_items,
    resolve_controller_code,
)

# ---------------------------------------------------------------------------
# fixture 内容来源：两个真实项目的 interface.json（裁剪精简版）
#   D:/MAS/reference/M9A-win-x86_64-v3.10.4/interface.json
#     controller: ADB / PC / PlayCover，resource: 官服 / B 服 / ...
#   D:/MAS/reference/MaaKes-win-x86_64-v1.1.11/interface.json
#     controller: 安卓端 / 桌面端，resource: 简中 / 繁中
# 真实文件的 task 走 import，这里内联少量 task 用于映射断言。
# ---------------------------------------------------------------------------

M9A_INTERFACE = {
    "interface_version": 2,
    "name": "m9a",
    "label": "M9A",
    "version": "v4.6.0",
    "controller": [
        {"name": "ADB", "label": "模拟器", "type": "Adb"},
        {
            "name": "PC",
            "label": "PC",
            "type": "Win32",
            "win32": {"class_regex": "UnityWndClass"},
            "permission_required": True,
        },
        {"name": "PlayCover", "type": "PlayCover"},
    ],
    "resource": [
        {"name": "官服", "path": ["./resource/base"], "controller": ["ADB", "PlayCover"]},
        {
            "name": "B 服",
            "path": ["./resource/base", "./resource/bilibili"],
            "controller": ["ADB", "PlayCover"],
        },
        {
            "name": "国际服（EN）",
            "path": ["./resource/base", "./resource/global_en"],
            "controller": ["ADB", "PC", "PlayCover"],
        },
    ],
    "task": [
        {"name": "启动游戏", "entry": "StartUp", "controller": ["ADB"]},
        {
            "name": "收取荒原",
            "entry": "Wilderness",
            "group": ["daily"],
            "option": ["好梦井", "魔精收菜"],
        },
        {
            "name": "切换账号",
            "entry": "SwitchAccount",
            "description": "留空时切到最后一个账号",
            "resource": ["官服"],
            "option": ["目标账号(可选)"],
        },
        {"name": "关闭游戏", "entry": "Close1999", "controller": ["ADB"]},
    ],
}

MAAKES_INTERFACE = {
    "interface_version": 2,
    "name": "Maa_Kes",
    "version": "v1.1.11",
    "controller": [
        {"name": "安卓端", "type": "Adb", "display_short_side": 720},
        {
            "name": "桌面端",
            "type": "Win32",
            "description": "一定要用管理员身份运行",
            "win32": {"class_regex": "GLFW30"},
        },
    ],
    "resource": [
        {"name": "简中", "path": ["./resource"]},
        {"name": "繁中", "path": ["./resource", "./resource_TC"]},
    ],
    "task": [
        {
            "name": "进入游戏",
            "label": "🎮进入游戏",
            "entry": "进游戏-任务开始层",
            "description": "分辨率一定要是16：9",
            "group": ["日常"],
            "option": ["模拟器自启动游戏"],
            "pipeline_override": {"进游戏-点击进入游戏": {"enabled": True}},
        },
        {
            "name": "日常-喝咖啡",
            "label": "☕️喝咖啡",
            "entry": "日常-喝咖啡-任务开始层",
            "group": ["日常"],
        },
        {
            "name": "自动战斗",
            "label": "⚔️自动战斗",
            "entry": "工具-自动战斗-任务开始层",
            "group": ["工具"],
            "option": ["自动战斗-自动释放EGO技能"],
        },
    ],
}


def m9a_model() -> MaaFWInterface:
    return MaaFWInterface.model_validate(M9A_INTERFACE)


def maakes_model() -> MaaFWInterface:
    return MaaFWInterface.model_validate(MAAKES_INTERFACE)


class ControllerCodeTest(unittest.TestCase):
    def test_adb_is_two(self) -> None:
        self.assertEqual(resolve_controller_code("Adb"), 2)

    def test_unknown_type_returns_none_not_a_guess(self) -> None:
        self.assertIsNone(resolve_controller_code("Win32"))
        self.assertIsNone(resolve_controller_code("PlayCover"))


class CrossProjectMappingTest(unittest.TestCase):
    """同一套映射代码对两个真实项目都产出正确的 controller / resource。"""

    def test_m9a_controller_and_resource(self) -> None:
        config = build_instance_config(
            m9a_model(),
            controller_name="ADB",
            resource_name="B 服",
            selected_tasks=[TaskSelection("收取荒原")],
        )
        self.assertEqual(config["CurrentControllerName"], "ADB")
        self.assertEqual(config["CurrentController"], 2)
        self.assertEqual(config["Resource"], "B 服")

    def test_maakes_controller_and_resource(self) -> None:
        config = build_instance_config(
            maakes_model(),
            controller_name="安卓端",
            resource_name="简中",
            selected_tasks=[TaskSelection("日常-喝咖啡")],
        )
        self.assertEqual(config["CurrentControllerName"], "安卓端")
        self.assertEqual(config["CurrentController"], 2)
        self.assertEqual(config["Resource"], "简中")

    def test_same_code_path_both_projects(self) -> None:
        cases = [
            (m9a_model(), "ADB", "官服"),
            (m9a_model(), "ADB", "国际服（EN）"),
            (maakes_model(), "安卓端", "繁中"),
        ]
        for interface, controller_name, resource_name in cases:
            with self.subTest(controller=controller_name, resource=resource_name):
                config = build_instance_config(
                    interface,
                    controller_name=controller_name,
                    resource_name=resource_name,
                )
                self.assertEqual(config["CurrentControllerName"], controller_name)
                self.assertEqual(config["Resource"], resource_name)
                self.assertEqual(config["CurrentController"], 2)


class FailClosedControllerTest(unittest.TestCase):
    def test_win32_controller_raises_instead_of_guessing(self) -> None:
        with self.assertRaises(UnknownControllerTypeError) as ctx:
            build_instance_config(m9a_model(), controller_name="PC")
        self.assertEqual(ctx.exception.controller_name, "PC")
        self.assertEqual(ctx.exception.controller_type, "Win32")

    def test_maakes_desktop_controller_also_fail_closed(self) -> None:
        with self.assertRaises(UnknownControllerTypeError):
            build_instance_config(maakes_model(), controller_name="桌面端")

    def test_unknown_controller_name_raises_mapping_error(self) -> None:
        with self.assertRaises(ShellMappingError):
            build_instance_config(m9a_model(), controller_name="不存在的端")

    def test_unknown_resource_name_raises_mapping_error(self) -> None:
        with self.assertRaises(ShellMappingError):
            build_instance_config(m9a_model(), resource_name="不存在的服")


class CurrentTasksFormatTest(unittest.TestCase):
    def test_join_format_uses_literal_separator(self) -> None:
        tasks = build_current_tasks(m9a_model())
        self.assertEqual(
            tasks,
            [
                "启动游戏<|||>StartUp",
                "收取荒原<|||>Wilderness",
                "切换账号<|||>SwitchAccount",
                "关闭游戏<|||>Close1999",
            ],
        )

    def test_current_tasks_covers_all_tasks_not_only_selected(self) -> None:
        config = build_instance_config(
            maakes_model(),
            selected_tasks=[TaskSelection("日常-喝咖啡")],
        )
        self.assertEqual(len(config["CurrentTasks"]), 3)
        self.assertEqual(len(config["TaskItems"]), 1)


class TaskItemsOptionalFieldsTest(unittest.TestCase):
    def test_label_kept_when_present_absent_when_not(self) -> None:
        items = build_task_items(
            maakes_model(),
            [TaskSelection("进入游戏"), TaskSelection("自动战斗")],
        )
        self.assertEqual(items[0]["name"], "进入游戏")
        self.assertEqual(items[0]["label"], "🎮进入游戏")

        m9a_items = build_task_items(m9a_model(), [TaskSelection("收取荒原")])
        self.assertNotIn("label", m9a_items[0])

    def test_default_check_reflects_selection(self) -> None:
        items = build_task_items(
            m9a_model(),
            [
                TaskSelection("启动游戏", checked=False),
                TaskSelection("收取荒原", checked=True),
            ],
        )
        self.assertFalse(items[0]["default_check"])
        self.assertTrue(items[1]["default_check"])

    def test_group_description_controller_passthrough(self) -> None:
        (item,) = build_task_items(m9a_model(), [TaskSelection("切换账号")])
        self.assertEqual(item["description"], "留空时切到最后一个账号")
        self.assertNotIn("group", item)
        self.assertNotIn("controller", item)

        (startup,) = build_task_items(m9a_model(), [TaskSelection("启动游戏")])
        self.assertEqual(startup["controller"], ["ADB"])
        self.assertNotIn("description", startup)

        (wild,) = build_task_items(m9a_model(), [TaskSelection("收取荒原")])
        self.assertEqual(wild["group"], ["daily"])

    def test_option_defaults_from_interface_names(self) -> None:
        (item,) = build_task_items(m9a_model(), [TaskSelection("收取荒原")])
        self.assertEqual(
            item["option"],
            [{"name": "好梦井", "index": 0}, {"name": "魔精收菜", "index": 0}],
        )

    def test_option_selection_overrides_interface_names(self) -> None:
        selection = TaskSelection(
            "切换账号",
            options=[{"name": "目标账号(可选)", "index": 0, "data": {"账号": "abc"}}],
        )
        (item,) = build_task_items(m9a_model(), [selection])
        self.assertEqual(
            item["option"],
            [{"name": "目标账号(可选)", "index": 0, "data": {"账号": "abc"}}],
        )

    def test_no_option_key_when_task_has_none(self) -> None:
        (item,) = build_task_items(maakes_model(), [TaskSelection("日常-喝咖啡")])
        self.assertNotIn("option", item)

    def test_pipeline_override_from_interface_and_override(self) -> None:
        (item,) = build_task_items(maakes_model(), [TaskSelection("进入游戏")])
        self.assertEqual(
            item["pipeline_override"], {"进游戏-点击进入游戏": {"enabled": True}}
        )

        custom = TaskSelection("进入游戏", pipeline_override={"X": {"enabled": False}})
        (overridden,) = build_task_items(maakes_model(), [custom])
        self.assertEqual(overridden["pipeline_override"], {"X": {"enabled": False}})

    def test_unknown_selected_task_raises(self) -> None:
        with self.assertRaises(ShellMappingError):
            build_task_items(m9a_model(), [TaskSelection("不存在的任务")])


class BaseOverlayTest(unittest.TestCase):
    def _base(self) -> dict:
        return {
            "AdbDevice": {"Name": "雷电模拟器-LDPlayer", "AdbSerial": "emulator-5554"},
            "Connect.Address": "127.0.0.1:5555",
            "InstanceName": "配置 1",
            "UI.LiveView.RefreshRate": 10.0,
            "AgentTcpMode": False,
            "Resource": "官服",
        }

    def test_untouched_base_fields_are_preserved(self) -> None:
        base = self._base()
        config = build_instance_config(
            m9a_model(),
            controller_name="ADB",
            resource_name="B 服",
            selected_tasks=[TaskSelection("收取荒原")],
            base=base,
        )
        # C 类设备连接字段原样保留
        self.assertEqual(config["AdbDevice"], base["AdbDevice"])
        self.assertEqual(config["Connect.Address"], "127.0.0.1:5555")
        self.assertEqual(config["UI.LiveView.RefreshRate"], 10.0)
        self.assertEqual(config["AgentTcpMode"], False)
        # 覆盖了关心的字段
        self.assertEqual(config["Resource"], "B 服")
        self.assertEqual(config["CurrentController"], 2)

    def test_does_not_mutate_base(self) -> None:
        base = self._base()
        build_instance_config(
            m9a_model(),
            controller_name="ADB",
            selected_tasks=[TaskSelection("收取荒原")],
            base=base,
        )
        self.assertEqual(base["Resource"], "官服")
        self.assertNotIn("CurrentTasks", base)
        self.assertNotIn("CurrentController", base)

    def test_base_orchestration_kept_when_orchestration_not_given(self) -> None:
        base = self._base()
        base["BeforeTask"] = "StartupSoftwareAndScript"
        base["RememberAdb"] = False
        config = build_instance_config(m9a_model(), base=base)
        self.assertEqual(config["BeforeTask"], "StartupSoftwareAndScript")
        self.assertFalse(config["RememberAdb"])
        # 缺失的编排键仍被补齐
        self.assertEqual(config["AfterTask"], "None")

    def test_minimal_defaults_without_base(self) -> None:
        config = build_instance_config(m9a_model(), selected_tasks=[])
        self.assertEqual(config["TaskItems"], [])
        self.assertEqual(config["ResourceOptionItems"], {})
        self.assertEqual(config["InstanceName"], "MAS")
        self.assertEqual(config["BeforeTask"], "None")
        self.assertTrue(config["RememberAdb"])
        self.assertNotIn("CurrentController", config)
        self.assertNotIn("Resource", config)


class OrchestrationOverrideTest(unittest.TestCase):
    def test_explicit_orchestration_overwrites_base(self) -> None:
        base = {"InstanceName": "配置 1", "BeforeTask": "None", "RememberAdb": True}
        config = build_instance_config(
            m9a_model(),
            base=base,
            orchestration=InstanceOrchestration(
                instance_name="MAS-代理",
                before_task="StartupSoftwareAndScript",
                after_task="CloseEmulatorAndMFA",
                remember_adb=False,
            ),
        )
        self.assertEqual(config["InstanceName"], "MAS-代理")
        self.assertEqual(config["BeforeTask"], "StartupSoftwareAndScript")
        self.assertEqual(config["AfterTask"], "CloseEmulatorAndMFA")
        self.assertFalse(config["RememberAdb"])


if __name__ == "__main__":
    unittest.main()
