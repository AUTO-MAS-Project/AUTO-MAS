"""外壳家族识别：MXU 的 exe 不一定叫 mxu。

真机症状：M9A 的 MXU 包检查更新时报

    暂无可安装更新包: GitHub release package selection is ambiguous:
    M9A-win-x86_64-v4.7.1-MFAA.zip, M9A-win-x86_64-v4.7.1-MXU.zip

原先只按根目录文件名判定外壳，而 MXU 把 exe 命名为项目名：MaaYYs 是
``mxu.exe``（能认出），M9A 是 ``m9a.exe``、MaaEnd 是 ``MaaEnd.exe``（认不出）。
认不出 → 没有 project_shell_hint → 同版本两个包无法消歧。

（被本次清理删掉的旧 `tools/external/shell.py` 更差：它按 ``config/mxu-*.json``
这个**运行期才生成**的文件判 MXU、按 ``MFAAvalonia.dll`` + ``appsettings.json``
两者齐全判 MFAAvalonia，对五个真实发行包全部返回 unknown。）

补的是结构化兜底：MXU 把 MaaFramework 运行时放在根目录 ``maafw/`` 里，
MFAAvalonia 不这么做（它是 ``MaaAgentBinary/`` + ``libs/`` + ``runtimes/``）。
兜底只在文件名特征全部落空时生效，所以同样带 ``maafw/`` 的 MFW/CFA 包不受影响
——它们已被 ``MFW.exe`` / ``CFA.exe`` 认出。
"""

import tempfile
import unittest
from pathlib import Path

import app.core  # noqa: F401  # 初始化宿主配置

from app.task.MaaFW.tools.core.automas_maafw_project_update.updater import (
    detect_maafw_project_shell_hint,
)


def make(root: Path, files=(), dirs=()) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for name in files:
        (root / name).write_text("", encoding="utf-8")
    for name in dirs:
        (root / name).mkdir(exist_ok=True)
    return root


class ShellHintDetectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)

    def test_mxu_named_after_the_project_is_detected(self) -> None:
        """M9A 的 MXU 包：exe 叫 m9a.exe，只能靠 maafw/ 认出来。"""

        root = make(
            self.base / "m9a-mxu",
            files=("m9a.exe", "interface.json", "requirements.txt"),
            dirs=("maafw", "python", "agent", "resource"),
        )
        self.assertEqual(detect_maafw_project_shell_hint(root), "MXU")

    def test_maaend_is_detected(self) -> None:
        root = make(
            self.base / "maaend",
            files=("MaaEnd.exe", "interface.json"),
            dirs=("maafw", "agent", "resource", "locales"),
        )
        self.assertEqual(detect_maafw_project_shell_hint(root), "MXU")

    def test_mxu_named_mxu_still_works(self) -> None:
        root = make(
            self.base / "maayys",
            files=("mxu.exe", "interface.json"),
            dirs=("maafw", "agent"),
        )
        self.assertEqual(detect_maafw_project_shell_hint(root), "MXU")

    def test_mfaavalonia_is_unaffected(self) -> None:
        """MFAAvalonia 包没有 maafw/，文件名特征直接命中。"""

        root = make(
            self.base / "m9a-mfaa",
            files=("m9a.exe", "MFAAvalonia.dll", "MFAAvalonia.deps.json"),
            dirs=("libs", "runtimes", "MaaAgentBinary", "plugins"),
        )
        self.assertEqual(detect_maafw_project_shell_hint(root), "MFAAvalonia")

    def test_mfw_keeps_its_own_answer_despite_having_maafw(self) -> None:
        """识宝同样带 maafw/，但已被 MFW.exe 认出，兜底不得把它改成 MXU。"""

        root = make(
            self.base / "maa-bbb",
            files=("MFW.exe", "MFWUpdater.exe", "CFA_setting.json"),
            dirs=("maafw", "agent", "resource"),
        )
        self.assertEqual(detect_maafw_project_shell_hint(root), "MFW")

    def test_ambiguous_file_markers_still_yield_nothing(self) -> None:
        """两个外壳的文件特征同时命中时不猜，兜底也不该介入。"""

        root = make(
            self.base / "weird",
            files=("MFAAvalonia.dll", "mxu.exe"),
            dirs=("maafw",),
        )
        self.assertEqual(detect_maafw_project_shell_hint(root), "")

    def test_plain_project_without_any_shell_is_unknown(self) -> None:
        root = make(
            self.base / "bare",
            files=("interface.json",),
            dirs=("resource", "agent"),
        )
        self.assertEqual(detect_maafw_project_shell_hint(root), "")

    def test_missing_directory_is_unknown(self) -> None:
        self.assertEqual(
            detect_maafw_project_shell_hint(self.base / "nope"), ""
        )


class AssetDisambiguationEndToEndTest(unittest.TestCase):
    """识别结果要真的让选包不再 ambiguous。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)

    def _select(self, root: Path):
        from app.task.MaaFW.tools.core.automas_maafw_project_update.updater import (
            _select_github_release_asset,
        )

        release = {
            "assets": [
                {
                    "name": "M9A-win-x86_64-v4.7.1-MFAA.zip",
                    "browser_download_url": "https://x/MFAA.zip",
                },
                {
                    "name": "M9A-win-x86_64-v4.7.1-MXU.zip",
                    "browser_download_url": "https://x/MXU.zip",
                },
            ]
        }
        return _select_github_release_asset(
            release,
            r"\.zip$",
            project_name="M9A",
            project_shell_hint=detect_maafw_project_shell_hint(root),
            prefer_windows_x64=True,
        )

    def test_mxu_project_selects_the_mxu_package(self) -> None:
        root = make(
            self.base / "m9a-mxu",
            files=("m9a.exe", "interface.json"),
            dirs=("maafw", "python"),
        )
        url, reason = self._select(root)
        self.assertEqual(url, "https://x/MXU.zip")
        self.assertEqual(reason, "")

    def test_mfaa_project_selects_the_mfaa_package(self) -> None:
        root = make(
            self.base / "m9a-mfaa",
            files=("m9a.exe", "MFAAvalonia.dll"),
            dirs=("libs", "runtimes"),
        )
        url, reason = self._select(root)
        self.assertEqual(url, "https://x/MFAA.zip")
        self.assertEqual(reason, "")


if __name__ == "__main__":
    unittest.main()
