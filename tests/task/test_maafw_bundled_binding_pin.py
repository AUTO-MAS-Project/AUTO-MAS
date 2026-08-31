"""项目没声明依赖时，按它自带原生库的版本钉 Python binding。

MaaFW 的 py binding 与原生库是绑定关系——PyPI 的 `maafw` 包只对得上同版本的
`MaaFramework.dll`。跨 minor 混用不报错，但行为可能不同。

MaaYYs / MaaEnd 的 agent 是 Go / C++，不带 Python binding，也就没有
`requirements.txt` 可读；无约束的 `maafw` 会被解析成当时的最新正式版 5.12.3，
而它们自带的原生库是 v5.13.0-beta.x —— 实测中的真实错配。

版本从原生库二进制里读（不加载它），再规范化成 PEP 440：
`v5.13.0-beta.2` -> `5.13.0b2`，正好对得上 PyPI 上的预发布号。

这个提取方式有三重印证：
1. 来自 `maafw==5.12.3` 包的原生库，提取出的正是 `5.12.3`（已知答案的样本）
2. M9A 的 `requirements.txt` 声明 `maafw==5.12.3`，从它自带的库里也读出 `5.12.3`
3. M9A 还自带 `maafw-5.12.3.dist-info`，与前两者一致
"""

import tempfile
import unittest
from pathlib import Path

import app.core  # noqa: F401  # 初始化宿主配置

from app.task.MaaFW.tools.core.automas_maafw_runner.environment import (
    _bundled_project_maafw_requirement,
    _declared_project_maafw_requirement,
    probe_bundled_maafw_version,
)

TARGETS = Path("D:/MAS/tmp/maafw-embedded-target")


class VersionProbeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)

    def _project(self, blob: bytes, relative: str = "maafw") -> Path:
        root = self.base / str(abs(hash(blob + relative.encode())))
        target = root / relative
        target.mkdir(parents=True, exist_ok=True)
        (target / "MaaFramework.dll").write_bytes(blob)
        return root

    def test_release_version_is_normalized(self) -> None:
        root = self._project(b"\x00\x01padding v5.12.3 more\x00")
        self.assertEqual(probe_bundled_maafw_version(root), "5.12.3")
        self.assertEqual(_bundled_project_maafw_requirement(root), "maafw==5.12.3")

    def test_prerelease_maps_to_pep440(self) -> None:
        """v5.13.0-beta.2 -> 5.13.0b2，PyPI 上正是这个号。"""

        root = self._project(b"xx v5.13.0-beta.2 yy")
        self.assertEqual(probe_bundled_maafw_version(root), "5.13.0b2")

    def test_ambiguous_matches_are_refused(self) -> None:
        """出现多个版本串说明这个提取方式对该构建不成立，宁可不猜。"""

        root = self._project(b"v5.12.3 and also v5.13.0")
        self.assertIsNone(probe_bundled_maafw_version(root))
        self.assertIsNone(_bundled_project_maafw_requirement(root))

    def test_no_version_string_is_tolerated(self) -> None:
        self.assertIsNone(probe_bundled_maafw_version(self._project(b"nothing here")))

    def test_project_without_a_bundled_library_yields_nothing(self) -> None:
        root = self.base / "bare"
        root.mkdir()
        self.assertIsNone(probe_bundled_maafw_version(root))

    def test_version_inside_a_longer_token_is_not_matched(self) -> None:
        """避免把 ``xv5.12.3`` 或 ``v5.12.3.4`` 这类误当成版本。"""

        self.assertIsNone(probe_bundled_maafw_version(self._project(b"xxv5.12.3yy")))

    def test_dotnet_layout_is_probed_too(self) -> None:
        root = self._project(b"v5.12.3", relative="runtimes/win-x64/native")
        self.assertEqual(probe_bundled_maafw_version(root), "5.12.3")


@unittest.skipUnless(TARGETS.is_dir(), "靶子不在本机")
class RealTargetsTest(unittest.TestCase):
    """真靶子回归：这些数字是实测的，不是推的。"""

    EXPECTED = {
        "M9A-win-x86_64-v4.7.1-MFAA": "5.12.3",
        "M9A-win-x86_64-v4.7.1-MXU": "5.12.3",
        "MaaYYs-win-x86_64-v3.14.8-MXU": "5.13.0b2",
        "MaaEnd-win-x86_64-v2.26.0": "5.13.0b5",
        "Maa_bbb-win-x86_64-v1.12.14": "5.12.3",
    }

    def test_probed_versions(self) -> None:
        for name, expected in self.EXPECTED.items():
            root = TARGETS / name
            if not root.is_dir():
                self.skipTest(f"靶子不在本机: {name}")
            with self.subTest(target=name):
                self.assertEqual(probe_bundled_maafw_version(root), expected)

    def test_declaration_and_probe_agree_where_both_exist(self) -> None:
        """M9A 两个外壳都既声明了又自带库，两个独立来源必须一致。"""

        for name in ("M9A-win-x86_64-v4.7.1-MFAA", "M9A-win-x86_64-v4.7.1-MXU"):
            root = TARGETS / name
            if not root.is_dir():
                self.skipTest(f"靶子不在本机: {name}")
            with self.subTest(target=name):
                self.assertEqual(
                    _declared_project_maafw_requirement(root),
                    _bundled_project_maafw_requirement(root),
                )

    def test_native_agent_projects_have_nothing_to_declare(self) -> None:
        """MaaYYs / MaaEnd 没有 requirements.txt，正是要靠探测补上的那类。"""

        for name in ("MaaYYs-win-x86_64-v3.14.8-MXU", "MaaEnd-win-x86_64-v2.26.0"):
            root = TARGETS / name
            if not root.is_dir():
                self.skipTest(f"靶子不在本机: {name}")
            with self.subTest(target=name):
                self.assertIsNone(_declared_project_maafw_requirement(root))
                self.assertIsNotNone(_bundled_project_maafw_requirement(root))


class ResolutionOrderTest(unittest.TestCase):
    """探测优先于声明：我们加载的是项目自带的库，binding 必须跟它一致。

    对官方目录里 46 个 Windows 发行包的勘察表明声明不可靠：20 个没有
    requirements.txt、4 个无版本约束、**3 个声明与实际发行的库对不上**
    （MAAAE 声明 5.3.0 实际 5.6.0、MaaNTE 声明 v5.10.4 实际 5.10.5、
    MaaADr 声明 5.12.2 实际 5.12.3）。
    """

    def test_probe_is_consulted_before_the_declaration(self) -> None:
        from pathlib import Path as _Path

        source = (
            _Path(__file__).resolve().parents[2]
            / "app/task/MaaFW/tools/core/automas_maafw_runner/environment.py"
        ).read_text(encoding="utf-8")
        bundled = source.index("_bundled_project_maafw_requirement(project)")
        declared = source.index("_declared_project_maafw_requirement(project)")
        unpinned = source.index('selected_requirement = "maafw"')
        self.assertLess(bundled, declared, "探测必须排在声明之前")
        self.assertLess(declared, unpinned, "声明必须排在无约束兜底之前")

    def test_a_stale_declaration_loses_to_the_shipped_library(self) -> None:
        """真实案例形状：声明 5.12.2、实际发行 5.12.3，应当钉 5.12.3。"""

        import tempfile
        from pathlib import Path as _Path

        with tempfile.TemporaryDirectory() as td:
            root = _Path(td) / "proj"
            (root / "maafw").mkdir(parents=True)
            (root / "maafw" / "MaaFramework.dll").write_bytes(b"pad v5.12.3 pad")
            (root / "requirements.txt").write_text(
                chr(10).join(["maafw==5.12.2", "requests==2.34.2", ""]),
                encoding="utf-8",
            )
            self.assertEqual(_declared_project_maafw_requirement(root), "maafw==5.12.2")
            self.assertEqual(_bundled_project_maafw_requirement(root), "maafw==5.12.3")


if __name__ == "__main__":
    unittest.main()
