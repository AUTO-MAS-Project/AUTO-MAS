"""ADB 控制器的截图/输入方法选型，必须与第一层已真机验证的取值一致。

真机（M9A + 雷电）跑出来的缺陷：embedded 把**全部**截图方法交给 MaaFW 测速，
它按快慢选了 RawWithGzip。雷电上 ADB 系截图拿不到游戏的 GPU 渲染层——
图有正常的 1280x720，内容却是空的，于是识别全程无命中、一次点击都没发出，
每个任务空转到超时。

第一层（`manager.py`，已在 M9A/MaaKes/MaaEnd/MaaYYs 四个项目真机验证）
对模拟器写死 ``ScreencapMethods=64`` 与 ``InputMethods=18446744073709551607``，
本文件把 embedded 钉到同一组取值上。
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

import app.core  # noqa: F401  # 初始化宿主配置

REPO_ROOT = Path(__file__).resolve().parents[2]

MAA_MODULES = (
    "maa",
    "maa.agent_client",
    "maa.context",
    "maa.controller",
    "maa.custom_action",
    "maa.custom_recognition",
    "maa.define",
    "maa.event_sink",
    "maa.job",
    "maa.library",
    "maa.notification_handler",
    "maa.resource",
    "maa.tasker",
    "maa.toolkit",
)

# 第一层 manager.py 里写死的两个值
FIRST_LAYER_SCREENCAP = 64
FIRST_LAYER_INPUT = 18446744073709551607


def load_runner_task():
    patcher = mock.patch.dict(
        sys.modules, {name: mock.MagicMock() for name in MAA_MODULES}
    )
    patcher.start()
    import importlib

    module = importlib.import_module("app.task.MaaFW.tools.embedded.runner_task")
    return module, patcher


class AdbScreencapMethodTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module, patcher = load_runner_task()
        self.addCleanup(patcher.stop)

    def _profile(self, emulator_type: str, screencap_extra: bool, input_extra=False):
        return self.module.MaaFWAdbControlProfile(
            emulator_type=emulator_type,
            screencap_extra=screencap_extra,
            input_extra=input_extra,
            config={},
        )

    def _task(self, screencap_cfg: int = -57, input_cfg: int = -9):
        task = object.__new__(self.module.MaaFWPluginAutoProxyTask)
        task.script_config = mock.Mock()
        task.script_config.get.side_effect = lambda group, key: {
            ("Device", "AdbScreencapMethods"): screencap_cfg,
            ("Device", "AdbInputMethods"): input_cfg,
        }[(group, key)]
        return task

    def test_default_already_contains_emulator_extras(self) -> None:
        """旧实现写的是 DEFAULT | EXTRAS，而 DEFAULT 本就含 EXTRAS —— 空操作。"""

        self.assertTrue(self.module._ADB_SCREENCAP_DEFAULT & FIRST_LAYER_SCREENCAP)

    def test_ldplayer_with_extras_uses_emulator_extras_only(self) -> None:
        task = self._task()
        methods = task._resolve_adb_screencap_methods(
            self._profile("ldplayer", screencap_extra=True)
        )
        self.assertEqual(
            methods,
            FIRST_LAYER_SCREENCAP,
            "雷电必须只用模拟器增强截图，否则 MaaFW 会按测速选到抓不到画面的 ADB 截图",
        )

    def test_mumu_with_extras_uses_emulator_extras_only(self) -> None:
        task = self._task()
        methods = task._resolve_adb_screencap_methods(
            self._profile("mumu", screencap_extra=True)
        )
        self.assertEqual(methods, FIRST_LAYER_SCREENCAP)

    def test_emulator_without_extras_drops_the_extras_bit(self) -> None:
        """探测不到增强能力时不能再传 64，否则 MaaFW 会去用一个不存在的通道。"""

        task = self._task()
        methods = task._resolve_adb_screencap_methods(
            self._profile("ldplayer", screencap_extra=False)
        )
        self.assertFalse(methods & FIRST_LAYER_SCREENCAP)

    def test_unknown_emulator_falls_back_to_configured_value(self) -> None:
        task = self._task(screencap_cfg=-57)
        methods = task._resolve_adb_screencap_methods(
            self._profile("other", screencap_extra=False)
        )
        self.assertFalse(methods & FIRST_LAYER_SCREENCAP)


class AdbInputMethodTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module, patcher = load_runner_task()
        self.addCleanup(patcher.stop)

    def _profile(self, emulator_type: str, input_extra: bool = False):
        return self.module.MaaFWAdbControlProfile(
            emulator_type=emulator_type,
            screencap_extra=True,
            input_extra=input_extra,
            config={},
        )

    def _task(self):
        task = object.__new__(self.module.MaaFWPluginAutoProxyTask)
        task.script_config = mock.Mock()
        task.script_config.get.return_value = -9
        return task

    def test_ldplayer_input_matches_the_first_layer(self) -> None:
        methods = self._task()._resolve_adb_input_methods(self._profile("ldplayer"))
        self.assertEqual(
            methods & 0xFFFFFFFFFFFFFFFF,
            FIRST_LAYER_INPUT,
            "输入方法必须与第一层写死的 18446744073709551607 一致",
        )


class FirstLayerValuesUnchangedTest(unittest.TestCase):
    """第一层的既验证取值是本文件的基准，改动它必须是有意识的。"""

    def test_manager_still_hardcodes_the_verified_values(self) -> None:
        source = (REPO_ROOT / "app/task/MaaFW/manager.py").read_text(encoding="utf-8")
        self.assertIn('"ScreencapMethods": 64', source)
        self.assertIn('"InputMethods": 18446744073709551607', source)


if __name__ == "__main__":
    unittest.main()
