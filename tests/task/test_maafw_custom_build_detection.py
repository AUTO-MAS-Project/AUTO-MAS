"""项目自带的原生库是不是官方那份。

按版本钉 binding 只能保证「官方发布的同版本」。项目若塞进一份自己改的构建，
它报的版本串照样是 X，版本一致性检查看不出任何异常——只有比字节能发现。

好在两份文件此时都在本地（一份在项目目录，一份在 runner venv 的 maa/bin），
比对不需要联网。

对 MaaFramework 官方目录里 46 个 Windows 发行包做过全量比对（HTTP Range 读
zip，不下整包）：能确定版本的 44 个**全部与对应 PyPI wheel 逐字节相同**，
哈希与字节数都一致，覆盖 4.5.3 / 4.5.6 / 5.6.0 / 5.10.2 / 5.10.5 / 5.12.1 /
5.12.2 / 5.12.3 / 5.13.0b2 / 5.13.0b5 十个版本。另两个没有原生库（一个是
.7z 套 .zip，一个是单独的 wheels 包），不参与比对。

所以这个检查平时不会响；它是给「哪天真有人这么干」留的。
"""

import sys
import tempfile
import unittest
from pathlib import Path
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


class CustomBuildDetectionTest(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.dict(
            sys.modules, {name: mock.MagicMock() for name in MAA_MODULES}
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        import importlib

        self.module = importlib.import_module(
            "app.task.MaaFW.tools.core.automas_maafw_runner.runner"
        )
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)

    def _binding_dir(self, blob: bytes) -> Path:
        pkg = self.base / "site-packages" / "maa"
        (pkg / "bin").mkdir(parents=True, exist_ok=True)
        (pkg / "bin" / "MaaFramework.dll").write_bytes(blob)
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        return pkg

    def _project_dir(self, blob: bytes) -> Path:
        d = self.base / "proj" / "maafw"
        d.mkdir(parents=True, exist_ok=True)
        (d / "MaaFramework.dll").write_bytes(blob)
        return d

    def _detect(self, project_blob, binding_blob):
        pkg = self._binding_dir(binding_blob)
        runtime = self._project_dir(project_blob) if project_blob is not None else None
        fake = mock.MagicMock()
        fake.__file__ = str(pkg / "__init__.py")
        with mock.patch.object(self.module, "maa_package", fake):
            return self.module.detect_custom_maafw_build(runtime)

    def test_identical_binaries_are_not_flagged(self) -> None:
        self.assertIs(self._detect(b"official bytes", b"official bytes"), False)

    def test_different_binaries_are_flagged(self) -> None:
        """同版本、不同字节 —— 版本号抓不到的那种情况。"""

        self.assertIs(self._detect(b"custom build", b"official bytes"), True)

    def test_same_length_but_different_content_is_flagged(self) -> None:
        """长度相同也要比内容，不能只看大小。"""

        self.assertIs(self._detect(b"AAAAAAAA", b"BBBBBBBB"), True)

    def test_no_project_runtime_means_no_divergence(self) -> None:
        """没有项目自带的库，本来就用 binding 那份。"""

        self.assertIs(self._detect(None, b"official bytes"), False)

    def test_unreadable_project_library_yields_unknown(self) -> None:
        pkg = self._binding_dir(b"official")
        missing = self.base / "nowhere"
        fake = mock.MagicMock()
        fake.__file__ = str(pkg / "__init__.py")
        with mock.patch.object(self.module, "maa_package", fake):
            self.assertIsNone(self.module.detect_custom_maafw_build(missing))

    def test_detection_never_raises(self) -> None:
        """这是诊断信息，不能因为它挡住运行。"""

        fake = mock.MagicMock()
        fake.__file__ = str(self.base / "no-such-pkg" / "__init__.py")
        with mock.patch.object(self.module, "maa_package", fake):
            self.assertIsNone(
                self.module.detect_custom_maafw_build(self.base / "also-missing")
            )


class SupportBoundaryIsRecordedTest(unittest.TestCase):
    """支持边界要写在代码里，可查可引用。"""

    def test_minimum_version_constant_exists(self) -> None:
        from app.task.MaaFW.tools.core.automas_maafw_runner.environment import (
            MINIMUM_SUPPORTED_MAAFW_VERSION,
        )
        from packaging.version import Version

        self.assertEqual(Version(MINIMUM_SUPPORTED_MAAFW_VERSION), Version("5.0.0"))

    def test_the_reason_is_the_event_sink_module(self) -> None:
        """下限来自 runner 真的 import 了 maa.event_sink，而它 5.0.0 才有。"""

        root = Path(__file__).resolve().parents[2]
        runner = (
            root / "app/task/MaaFW/tools/core/automas_maafw_runner/runner.py"
        ).read_text(encoding="utf-8")
        self.assertIn("from maa.event_sink import", runner)
        env = (
            root / "app/task/MaaFW/tools/core/automas_maafw_runner/environment.py"
        ).read_text(encoding="utf-8")
        self.assertIn("event_sink", env)


if __name__ == "__main__":
    unittest.main()
