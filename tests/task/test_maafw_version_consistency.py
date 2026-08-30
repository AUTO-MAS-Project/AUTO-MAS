"""原生库与 Python binding 的版本一致性提示。

MaaFW 的 py binding 与原生库是绑定关系——PyPI 上的 `maafw` 包只对得上同版本的
`MaaFramework.dll`。跨 minor 混用**不会报错**，但行为可能不同，真机上表现为
「资源能导入、识别却不对」这类只在生产复现的问题。

而 AUTO-MAS 的内置运行天然会撞上这个：DLL 取自项目自带目录，binding 取自
runner venv（项目没有 requirements.txt 时装的是不带版本约束的 `maafw`）。
五个真实发行包实测：

    M9A-MFAA   DLL v5.12.3          binding v5.12.3   一致
    M9A-MXU    DLL v5.12.3          binding v5.12.3   一致
    MaaYYs     DLL v5.13.0-beta.2   binding v5.12.3   **不一致**
    MaaEnd     DLL v5.13.0-beta.5   binding v5.12.3   **不一致**
    Maa_bbb    DLL v5.12.3          binding v5.12.3   一致

真正的解法是让 runtime pool 按项目自带 DLL 的版本去钉 binding，那要先解决
beta 版能否从 PyPI 装到的问题，属于另一件事。在那之前至少要让它可见：
此前日志里的「使用 MaaFW: vX」报的是**依赖钉法**而非实际加载的库，
恰好在最需要看清的场景（没有 requirements.txt）报的是错的。
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


def load():
    patcher = mock.patch.dict(
        sys.modules, {name: mock.MagicMock() for name in MAA_MODULES}
    )
    patcher.start()
    import importlib

    return (
        importlib.import_module(
            "app.task.MaaFW.tools.core.automas_maafw_runner.runner"
        ),
        patcher,
    )


class VersionNormalisationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module, patcher = load()
        self.addCleanup(patcher.stop)

    def test_v_prefix_does_not_count_as_a_mismatch(self) -> None:
        """Library.version() 带 v 前缀，包版本不带，不能因此误报。"""

        normalize = self.module._normalize_maafw_version
        self.assertEqual(normalize("v5.12.3"), normalize("5.12.3"))
        self.assertNotEqual(normalize("v5.13.0"), normalize("5.12.3"))


class InitLoggingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module, patcher = load()
        self.addCleanup(patcher.stop)
        self.module._MAAFW_INITIALIZED = False

    def _run(self, loaded: str, binding: str, runtime_path=None):
        logs: list[str] = []
        with (
            mock.patch.object(
                self.module,
                "_ensure_maafw_client_library_mode",
                lambda *_: None,
            ),
            mock.patch.object(
                self.module,
                "_project_maafw_runtime_path",
                lambda *_: runtime_path,
            ),
            mock.patch.object(
                self.module,
                "describe_loaded_maafw",
                lambda: (loaded, binding),
            ),
            mock.patch.object(self.module, "_MAAFW_INITIALIZED", False),
            mock.patch(
                "pathlib.Path.write_text", lambda *a, **k: None
            ),
            mock.patch("pathlib.Path.mkdir", lambda *a, **k: None),
        ):
            try:
                self.module._ensure_maafw_global_init(None, logs.append)
            except Exception:
                # 初始化后半段要真的碰 MaaFW，本用例只关心日志部分
                pass
        return logs

    def test_actual_loaded_version_is_reported(self) -> None:
        logs = self._run("v5.13.0-beta.2", "5.12.3")
        self.assertTrue(
            any("实际加载" in line and "5.13.0-beta.2" in line for line in logs),
            logs,
        )

    def test_mismatch_is_warned_about(self) -> None:
        logs = self._run("v5.13.0-beta.2", "5.12.3")
        warning = [line for line in logs if line.startswith("⚠")]
        self.assertTrue(warning, logs)
        self.assertIn("5.13.0-beta.2", warning[0])
        self.assertIn("5.12.3", warning[0])

    def test_matching_versions_do_not_warn(self) -> None:
        logs = self._run("v5.12.3", "5.12.3")
        self.assertFalse([line for line in logs if line.startswith("⚠")], logs)

    def test_unknown_version_does_not_warn(self) -> None:
        """取不到版本时不能瞎报，也不能因此挡住运行。"""

        self.assertFalse([line for line in self._run("", "5.12.3") if line.startswith("⚠")])
        self.assertFalse([line for line in self._run("v5.12.3", "") if line.startswith("⚠")])


if __name__ == "__main__":
    unittest.main()
