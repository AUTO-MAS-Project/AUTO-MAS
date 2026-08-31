"""ADB / Win32 控制器服务的导入与纯逻辑回归。

两个包由插件 `dev2/maafw-fixes-20260728` 移入（基准对照 §2，MAS 三边此前都没有），
已按移植指南 §4 丢弃 `plugin.py`/`schema.py`、改写跨包导入、手写最小 `__init__`。

窗口枚举依赖 `maa.toolkit`，按测试纪律 **不做全进程/全窗口枚举**，
所有匹配用例都注入构造好的窗口列表。
"""

import ast
import inspect
import unittest
from pathlib import Path

import app.core  # noqa: F401  # 初始化宿主配置

from app.task.MaaFW.tools.core.automas_maafw_controller_adb import (
    MaaFWAdbControllerService,
)
from app.task.MaaFW.tools.core.automas_maafw_controller_win32 import (
    MaaFWWin32ControllerService,
    MaaFWWin32Window,
    MaaFWWindowMatch,
)
from app.task.MaaFW.tools.core.automas_maafw_controller_win32.service import (
    _normalize_hwnd,
)


def win32_controller(class_regex=None, window_regex=None, name="Win32") -> dict:
    return {
        "name": name,
        "type": "Win32",
        "win32": {"class_regex": class_regex, "window_regex": window_regex},
    }


class ControllerPackageImportTest(unittest.TestCase):
    def test_maa_toolkit_import_stays_inside_list_windows(self) -> None:
        """导入本包不得触发 maa DLL 加载。

        用静态检查而非 `sys.modules` 断言：`app/core/maa_manager.py` 是上游基线
        既有的原生集成，全量跑时会合法地把 maa 载入进程。
        """

        source = Path(inspect.getfile(MaaFWWin32ControllerService)).read_text(
            encoding="utf-8"
        )
        module = ast.parse(source)
        top_level_imports = [
            node
            for node in module.body
            if isinstance(node, (ast.Import, ast.ImportFrom))
        ]
        for node in top_level_imports:
            names = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
            )
            for name in names:
                self.assertFalse(
                    name == "maa" or name.startswith("maa."),
                    "maa 不得在模块级导入: " + name,
                )
        self.assertIn("from maa.toolkit import Toolkit", source)

    def test_provider_definitions_are_stable(self) -> None:
        self.assertEqual(
            MaaFWAdbControllerService().get_provider_definition(),
            {
                "key": "adb",
                "displayName": "ADB",
                "controllerTypes": ["Adb"],
                "capabilities": ["device_spec", "emulator_service_consumption"],
            },
        )
        self.assertEqual(
            MaaFWWin32ControllerService().get_provider_definition(),
            {
                "key": "win32",
                "displayName": "Win32",
                "controllerTypes": ["Win32"],
                "capabilities": ["window_scan", "device_spec"],
            },
        )


class AdbDeviceSpecTest(unittest.TestCase):
    def test_defaults(self) -> None:
        self.assertEqual(
            MaaFWAdbControllerService().build_device_spec(),
            {
                "type": "Adb",
                "adbPath": None,
                "address": None,
                "screencapMethods": 0,
                "inputMethods": 0,
                "config": {},
            },
        )

    def test_config_is_copied_not_aliased(self) -> None:
        config = {"extras": {"mumu": {}}}
        spec = MaaFWAdbControllerService().build_device_spec(
            adb_path="adb.exe",
            address="127.0.0.1:16384",
            screencap_methods=1,
            input_methods=2,
            config=config,
        )
        self.assertEqual(spec["address"], "127.0.0.1:16384")
        spec["config"]["extras"] = None
        self.assertEqual(config["extras"], {"mumu": {}})


class Win32DeviceSpecTest(unittest.TestCase):
    def test_device_spec_shape(self) -> None:
        self.assertEqual(
            MaaFWWin32ControllerService().build_device_spec(
                h_wnd=1234,
                screencap_method=1,
                mouse_method=2,
                keyboard_method=3,
            ),
            {
                "type": "Win32",
                "hWnd": 1234,
                "screencapMethod": 1,
                "mouseMethod": 2,
                "keyboardMethod": 3,
            },
        )


class Win32WindowMatchTest(unittest.TestCase):
    WINDOWS = [
        MaaFWWin32Window(hWnd=1, className="UnityWndClass", windowName="明日方舟"),
        MaaFWWin32Window(hWnd=2, className="Chrome_WidgetWin_1", windowName="Chrome"),
        MaaFWWin32Window(hWnd=1, className="UnityWndClass", windowName="明日方舟"),
    ]

    def setUp(self) -> None:
        self.service = MaaFWWin32ControllerService()

    def test_both_regexes_must_match(self) -> None:
        matched = self.service.match_controller_windows(
            win32_controller(class_regex="^Unity", window_regex="明日"),
            self.WINDOWS,
        )
        self.assertEqual([window.hWnd for window in matched], [1])
        self.assertIsInstance(matched[0], MaaFWWindowMatch)
        self.assertEqual(matched[0].controllerType, "Win32")

    def test_absent_regex_matches_everything(self) -> None:
        matched = self.service.match_controller_windows(
            win32_controller(),
            self.WINDOWS,
        )
        self.assertEqual([window.hWnd for window in matched], [1, 2])

    def test_duplicate_hwnds_are_collapsed(self) -> None:
        matched = self.service.match_controller_windows(
            win32_controller(class_regex="Unity"),
            self.WINDOWS,
        )
        self.assertEqual(len(matched), 1)

    def test_non_win32_controller_matches_nothing(self) -> None:
        matched = self.service.match_controller_windows(
            {"name": "Adb", "type": "Adb"},
            self.WINDOWS,
        )
        self.assertEqual(matched, [])

    def test_no_match_returns_empty(self) -> None:
        matched = self.service.match_controller_windows(
            win32_controller(class_regex="^NoSuchClass$"),
            self.WINDOWS,
        )
        self.assertEqual(matched, [])

    def test_overlong_pattern_is_refused(self) -> None:
        with self.assertRaises(RuntimeError):
            self.service.match_controller_windows(
                win32_controller(class_regex="a" * 257),
                self.WINDOWS,
            )

    def test_nested_quantifier_redos_pattern_is_refused(self) -> None:
        with self.assertRaises(RuntimeError):
            self.service.match_controller_windows(
                win32_controller(class_regex="(a+)+"),
                self.WINDOWS,
            )

    def test_invalid_regex_is_reported_as_runtime_error(self) -> None:
        with self.assertRaises(RuntimeError):
            self.service.match_controller_windows(
                win32_controller(class_regex="["),
                self.WINDOWS,
            )


class NormalizeHwndTest(unittest.TestCase):
    def test_plain_and_ctypes_like_values(self) -> None:
        class Handle:
            value = 4321

        self.assertEqual(_normalize_hwnd(1234), 1234)
        self.assertEqual(_normalize_hwnd(Handle()), 4321)
        self.assertEqual(_normalize_hwnd(None), 0)


if __name__ == "__main__":
    unittest.main()
