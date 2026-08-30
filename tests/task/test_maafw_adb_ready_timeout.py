"""等待 adb 认出设备的耐心预算。

真机（M9A + 雷电）冷启动失败：`LDPlayer.open()` 在 `in_android == 1` 之后
只 sleep 3 秒就返回「启动完成」（不传 `package_name` 时不走那个 30 秒分支），
此时 Android 里的 adbd 往往还没起来。runner 随后只等 30 秒就放弃，
报 `device 'emulator-5554' not found`；手动确认设备最终是能出现的。

插件版同样是固定 30 秒（`ADB_READY_RETRY_COUNT = 30`），没有更好的上游模式可抄；
M9A 专项则根本不等 adb——它把等待交给项目外壳。内置运行这条等待是唯一的缓冲，
因此改为按该模拟器自己的 `Info.MaxWaitTime`（默认 300 秒）下发。
"""

import sys
import unittest
from unittest import mock

import app.core  # noqa: F401  # 初始化宿主配置

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


def load(module_name: str):
    patcher = mock.patch.dict(
        sys.modules, {name: mock.MagicMock() for name in MAA_MODULES}
    )
    patcher.start()
    import importlib

    return importlib.import_module(module_name), patcher


class HostSuppliedTimeoutTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module, patcher = load("app.task.MaaFW.tools.embedded.runner_task")
        self.addCleanup(patcher.stop)

    def _task(self, emulator_manager):
        task = object.__new__(self.module.MaaFWPluginAutoProxyTask)
        task.emulator_manager = emulator_manager
        return task

    def test_uses_the_emulator_max_wait_time(self) -> None:
        config = mock.Mock()
        config.get.return_value = 300
        timeout = self._task(mock.Mock(config=config))._resolve_adb_ready_timeout()
        self.assertEqual(timeout, 300)
        config.get.assert_called_with("Info", "MaxWaitTime")

    def test_no_emulator_falls_back_to_the_runner_constant(self) -> None:
        self.assertIsNone(self._task(None)._resolve_adb_ready_timeout())

    def test_missing_config_falls_back(self) -> None:
        self.assertIsNone(
            self._task(mock.Mock(spec=[]))._resolve_adb_ready_timeout()
        )

    def test_unreadable_config_falls_back(self) -> None:
        config = mock.Mock()
        config.get.side_effect = KeyError("Info")
        self.assertIsNone(
            self._task(mock.Mock(config=config))._resolve_adb_ready_timeout()
        )

    def test_non_positive_value_falls_back(self) -> None:
        config = mock.Mock()
        config.get.return_value = 0
        self.assertIsNone(
            self._task(mock.Mock(config=config))._resolve_adb_ready_timeout()
        )


class RunnerBudgetTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module, patcher = load(
            "app.task.MaaFW.tools.core.automas_maafw_runner.runner"
        )
        self.addCleanup(patcher.stop)

    def test_fallback_constant_is_generous_enough_for_a_cold_boot(self) -> None:
        """插件带来的 30 秒在冷启动上实测不够。"""

        self.assertGreaterEqual(self.module.ADB_READY_RETRY_COUNT, 120)
        self.assertEqual(self.module.ADB_READY_RETRY_INTERVAL, 1.0)

    def test_device_config_carries_the_budget(self) -> None:
        from app.task.MaaFW.tools.core.automas_maafw_runner.models import (
            MaaFWDeviceConfig,
        )

        self.assertIsNone(MaaFWDeviceConfig(type="Adb").adbReadyTimeout)
        self.assertEqual(
            MaaFWDeviceConfig(type="Adb", adbReadyTimeout=300).adbReadyTimeout, 300
        )

    def test_budget_survives_the_job_file(self) -> None:
        """预算要跨进程传到 worker，序列化丢了等于没配。"""

        import json

        from app.task.MaaFW.tools.core.automas_maafw_runner.models import (
            MaaFWDeviceConfig,
        )

        payload = MaaFWDeviceConfig(type="Adb", adbReadyTimeout=300)
        restored = MaaFWDeviceConfig.model_validate(
            json.loads(json.dumps(payload.model_dump(mode="json")))
        )
        self.assertEqual(restored.adbReadyTimeout, 300)


class PreflightOrderTest(unittest.TestCase):
    """设备连通性必须排在加载插件与资源之前。

    此前顺序是「全局初始化 -> 原生插件 -> 资源 -> 连接设备」，设备没起来时
    先白加载几秒的 DLL 与资源，等待失败后再逐个拆掉。冷启动可能要等几分钟，
    更不该压在已经初始化了一半的 MaaFramework 上。
    """

    def test_device_preflight_runs_before_plugins_and_resources(self) -> None:
        import ast
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[2]
            / "app/task/MaaFW/tools/core/automas_maafw_runner/runner.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        target = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_ensure_initialized"
        )
        calls = [
            node.func.attr
            for node in ast.walk(target)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        ]
        order = [name for name in calls if name.startswith("_")]
        self.assertIn("_preflight_device", order)
        for later in ("_load_native_plugins", "_load_resources", "_start_agents"):
            self.assertLess(
                order.index("_preflight_device"),
                order.index(later),
                f"设备连通性必须早于 {later}",
            )

    def test_preflight_only_touches_the_device(self) -> None:
        """前置检查不能依赖 resource/tasker/controller，否则前移就不成立。"""

        import ast
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[2]
            / "app/task/MaaFW/tools/core/automas_maafw_runner/runner.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        target = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_preflight_device"
        )
        attrs = {
            node.attr
            for node in ast.walk(target)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
        }
        for forbidden in ("resource", "tasker", "controller"):
            self.assertNotIn(forbidden, attrs)


if __name__ == "__main__":
    unittest.main()
