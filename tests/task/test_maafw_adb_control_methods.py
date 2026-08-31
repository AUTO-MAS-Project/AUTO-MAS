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

# 真机验证过的两个取值（最早由第一层 manager.py 写死，第一层删除后本文件即出处）
VERIFIED_SCREENCAP = 64
VERIFIED_INPUT = 18446744073709551607


def load_runner_task():
    patcher = mock.patch.dict(
        sys.modules, {name: mock.MagicMock() for name in MAA_MODULES}
    )
    patcher.start()
    import importlib

    module = importlib.import_module("app.task.MaaFW.tools.embedded.runner_task")
    return module, patcher


def load_core_runner():
    patcher = mock.patch.dict(
        sys.modules, {name: mock.MagicMock() for name in MAA_MODULES}
    )
    patcher.start()
    import importlib

    module = importlib.import_module(
        "app.task.MaaFW.tools.core.automas_maafw_runner.runner"
    )
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

        self.assertTrue(self.module._ADB_SCREENCAP_DEFAULT & VERIFIED_SCREENCAP)

    def test_ldplayer_with_extras_uses_emulator_extras_only(self) -> None:
        task = self._task()
        methods = task._resolve_adb_screencap_methods(
            self._profile("ldplayer", screencap_extra=True)
        )
        self.assertEqual(
            methods,
            VERIFIED_SCREENCAP,
            "雷电必须只用模拟器增强截图，否则 MaaFW 会按测速选到抓不到画面的 ADB 截图",
        )

    def test_mumu_with_extras_uses_emulator_extras_only(self) -> None:
        task = self._task()
        methods = task._resolve_adb_screencap_methods(
            self._profile("mumu", screencap_extra=True)
        )
        self.assertEqual(methods, VERIFIED_SCREENCAP)

    def test_emulator_without_extras_drops_the_extras_bit(self) -> None:
        """探测不到增强能力时不能再传 64，否则 MaaFW 会去用一个不存在的通道。"""

        task = self._task()
        methods = task._resolve_adb_screencap_methods(
            self._profile("ldplayer", screencap_extra=False)
        )
        self.assertFalse(methods & VERIFIED_SCREENCAP)

    def test_unknown_emulator_falls_back_to_configured_value(self) -> None:
        task = self._task(screencap_cfg=-57)
        methods = task._resolve_adb_screencap_methods(
            self._profile("other", screencap_extra=False)
        )
        self.assertFalse(methods & VERIFIED_SCREENCAP)


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
            VERIFIED_INPUT,
            "输入方法必须是真机验证的 18446744073709551607",
        )


class VerifiedValuesUnchangedTest(unittest.TestCase):
    """这两个取值是真机基准，改动必须是有意识的。

    原先锚在第一层 `manager.py` 的源码上（那是它们最早被真机验证的地方）。
    第一层删除后改锚到本文件顶部的常量——取值不变，只是出处从「抄第一层」
    变成「本层自己的基准」。解析行为由上面的 AdbScreencapMethodTest 覆盖，
    这里只钉住数值本身。
    """

    def test_constants_still_hold_the_verified_values(self) -> None:
        self.assertEqual(VERIFIED_SCREENCAP, 64)
        self.assertEqual(VERIFIED_INPUT, 18446744073709551607)


class ConnectionLogWordingTest(unittest.TestCase):
    """连接日志要按实际位数说话。

    MaaFW 的 ADB controller 收的是候选集合，原生层测速后择一，Python binding
    不暴露选中项——所以传多个时要提示去框架日志看。但模拟器截图现在只传
    EmulatorExtras(64) 一个，既没有候选也没有测速，再说「测速后选中」就是误导。
    """

    def setUp(self) -> None:
        self.module, patcher = load_core_runner()
        self.addCleanup(patcher.stop)

    def test_single_method_detection(self) -> None:
        self.assertTrue(self.module._is_single_method(VERIFIED_SCREENCAP))
        self.assertTrue(self.module._is_single_method(1))
        # Default 是多位掩码
        self.assertFalse(self.module._is_single_method(-57))
        self.assertFalse(self.module._is_single_method(-9))
        self.assertFalse(self.module._is_single_method(0))

    def test_wording_switches_on_bit_count(self) -> None:
        source = (
            REPO_ROOT / "app/task/MaaFW/tools/core/automas_maafw_runner/runner.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            '"截图方法=" if screencap_single else "传入截图候选集合="', source
        )
        self.assertIn('"输入方法=" if input_single else "传入输入候选集合="', source)
        # 测速提示只在确实传了多个候选时才出现
        self.assertIn("if not (screencap_single and input_single):", source)

    def test_preconnect_line_uses_the_same_rule(self) -> None:
        """连接前那条「传入」日志也得按位数措辞，两处不能互相打架。"""

        source = (
            REPO_ROOT / "app/task/MaaFW/tools/core/automas_maafw_runner/runner.py"
        ).read_text(encoding="utf-8")
        # 折叠空白，免得断言绑死在换行与缩进上
        flat = " ".join(source.split())
        self.assertIn(
            '"截图方法" if _is_single_method(screencap_methods) else "截图候选集合"',
            flat,
        )
        self.assertIn(
            '"输入方法" if _is_single_method(input_methods) else "输入候选集合"',
            flat,
        )
        # 旧的无条件措辞不该再有
        self.assertNotIn("ADB controller 传入候选集合", source)


if __name__ == "__main__":
    unittest.main()
