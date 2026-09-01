"""运行环境闸门：装完要验真、跑之前要拦一道。

真机现场（2026-08-31）：用户的 Python 运行时标准库损坏，运行池却认为环境就绪，
直到 worker 起来才在 ``maa/library.py`` 第 1 行的 ``import ctypes`` 处炸掉，抛出
ctypes 内部的天书；而且模拟器和游戏已经先被拉起来了。

两道闸门：

- **装完即验**（``_verify_maafw_importable``）：``importlib.metadata.version``
  只读包元数据，装了一半或标准库坏掉时它照样报得出版本号。写 manifest 之前真的
  ``import maa`` 一次，坏环境就不会被记成好的。
- **跑前自检**（``describe_unusable_runtime``）：拦在 ``check()`` 里而不是只靠
  编辑页提示——队列与定时任务不经过编辑页，绕不过 check()，而且此时模拟器和游戏
  都还没启动。
"""

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import app.core  # noqa: F401  # 初始化宿主配置

from app.task.MaaFW import embedded_manager
from app.task.MaaFW.tools.core.automas_maafw_runtime_pool import installer


def _fake_python(tmp: Path, body: str) -> Path:
    """造一个只会按 body 行事的假解释器（.cmd 转发到真 Python）。"""

    script = tmp / "fake.py"
    script.write_text(body, encoding="utf-8")
    launcher = tmp / "fake.cmd"
    launcher.write_text(
        f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n', encoding="utf-8"
    )
    return launcher


class VerifyImportableTest(unittest.TestCase):
    """装完必须真的 import 得动 maa。"""

    def test_failure_is_raised_with_the_real_cause(self) -> None:
        with TemporaryDirectory() as name:
            tmp = Path(name)
            fake = _fake_python(
                tmp,
                "import sys\n"
                "sys.stderr.write(\"ModuleNotFoundError: No module named 'maa'\\n\")\n"
                "sys.exit(1)\n",
            )
            with self.assertRaises(RuntimeError) as caught:
                installer._verify_maafw_importable(fake)

        message = str(caught.exception)
        self.assertIn("import maa 不成功", message)
        self.assertIn("ModuleNotFoundError", message, "原始错误要带出去")

    def test_success_is_silent(self) -> None:
        with TemporaryDirectory() as name:
            tmp = Path(name)
            fake = _fake_python(tmp, "pass\n")
            self.assertIsNone(installer._verify_maafw_importable(fake))

    def test_it_runs_before_the_manifest_is_written(self) -> None:
        """源码级守卫：校验必须排在取版本号之前，否则坏环境仍会被记下来。"""

        import inspect

        source = inspect.getsource(installer)
        verify = source.index("_verify_maafw_importable(python_executable)\n    version")
        self.assertGreater(verify, 0, "校验要紧挨在取版本号之前")


class RuntimeGateTest(unittest.TestCase):
    """跑之前的自检。"""

    def _gate(self, *, requirement, runtimes, probe_error=None):
        probe = mock.Mock()
        if probe_error is not None:
            probe.side_effect = probe_error
        service = mock.Mock()
        service.return_value.list.return_value = runtimes
        with mock.patch.multiple(
            "app.task.MaaFW.tools.core.automas_maafw_runner.environment",
            resolve_project_maafw_requirement=mock.Mock(return_value=requirement),
        ):
            with mock.patch(
                "app.task.MaaFW.tools.core.automas_maafw_runtime_pool"
                ".MaaFWRuntimePoolService",
                service,
            ):
                with mock.patch(
                    "app.task.MaaFW.tools.core.automas_maafw_runtime_pool.installer"
                    ".probe_python_identity",
                    probe,
                ):
                    return (
                        embedded_manager.describe_unusable_runtime(Path("D:/proj")),
                        probe,
                    )

    @staticmethod
    def _runtime(requirement: str, executable: str = "D:/pool/python.exe"):
        return {"maafwRequirement": requirement, "pythonExecutable": executable}

    def test_broken_runtime_is_reported(self) -> None:
        problem, probe = self._gate(
            requirement="maafw==5.13.0b2",
            runtimes=[self._runtime("maafw==5.13.0b2")],
            probe_error=RuntimeError("标准库 ctypes 不可用"),
        )
        self.assertIsNotNone(problem)
        self.assertIn("MFW 运行环境不可用", problem)
        self.assertIn("标准库 ctypes 不可用", problem)
        probe.assert_called_once()

    def test_healthy_runtime_passes(self) -> None:
        problem, probe = self._gate(
            requirement="maafw==5.13.0b2",
            runtimes=[self._runtime("maafw==5.13.0b2")],
        )
        self.assertIsNone(problem)
        probe.assert_called_once()

    def test_unbuilt_runtime_is_not_blocked(self) -> None:
        """池里还没有匹配的 runtime 就不拦：那份环境会在运行时按需准备。"""

        problem, probe = self._gate(
            requirement="maafw==5.13.0b2",
            runtimes=[self._runtime("maafw==5.9.0")],
        )
        self.assertIsNone(problem)
        probe.assert_not_called()

    def test_unresolvable_requirement_is_not_blocked(self) -> None:
        problem, probe = self._gate(requirement=None, runtimes=[])
        self.assertIsNone(problem)
        probe.assert_not_called()

    def test_only_the_matching_runtime_is_probed(self) -> None:
        """池里通常有好几份 runtime，不该为了自检把它们全起一遍。"""

        problem, probe = self._gate(
            requirement="maafw==5.13.0b2",
            runtimes=[
                self._runtime("maafw==5.9.0"),
                self._runtime("maafw==5.13.0b2"),
                self._runtime("maafw==5.13.0b5"),
            ],
        )
        self.assertIsNone(problem)
        self.assertEqual(probe.call_count, 1)

    def test_self_check_failure_never_blocks_the_run(self) -> None:
        """自检自己出问题（池不可读等）不能反过来挡住运行。"""

        service = mock.Mock()
        service.return_value.list.side_effect = OSError("pool unreadable")
        with mock.patch.multiple(
            "app.task.MaaFW.tools.core.automas_maafw_runner.environment",
            resolve_project_maafw_requirement=mock.Mock(return_value="maafw==5.13.0b2"),
        ):
            with mock.patch(
                "app.task.MaaFW.tools.core.automas_maafw_runtime_pool"
                ".MaaFWRuntimePoolService",
                service,
            ):
                self.assertIsNone(
                    embedded_manager.describe_unusable_runtime(Path("D:/proj"))
                )


if __name__ == "__main__":
    unittest.main()
