"""worker 加载哪份 MaaFramework.dll。

同一个版本号下二进制未必相同。实测五个真实发行包自带的 MaaFramework.dll：

    M9A-MXU    5448a2d5… 2,532,864   与 PyPI maafw==5.12.3 相同
    Maa_bbb    5448a2d5… 2,532,864   相同
    MaaYYs     4048ba4e… 2,534,912   **不同**
    MaaEnd     661e5138… 2,534,912   **不同**（且与 MaaYYs 也不同）

所以必须优先加载项目自己的那份，项目的自定义构建才对得上。

`runtimes/win-x64/native` 是 MFAAvalonia 这类 .NET 外壳的固定布局
（.NET 把原生库放在 `runtimes/<rid>/native/` 下）。此前候选路径只到
`runtimes/win-x64` 这一层，对 MFAAvalonia 包永远落空、静默回落到 runner
venv 里那份——M9A-MFAA 没出事只是因为它那份恰好与 PyPI 相同。

已知布局不写死具体 rid（`runtimes/*` 用枚举），且全部落空时再走有界的逐层
搜索，免得下次外壳换个位置又静默回落。深度上限 4：真实布局最深 3 层，
再深就会扫到 `python/Lib/site-packages/maa/bin` 那种项目自带解释器的副本，
那是 agent 的而非外壳的。
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


def load():
    """解析实现放在 environment —— 它只依赖 stdlib + packaging，不碰 maa。

    早先这段逻辑在 runner 里，而 runner 顶层 import maa（导入即打开原生库），
    测试因此得先 mock 一整套 maa 模块。搬到 environment 后连 mock 都不需要了。
    """

    import importlib

    return (
        importlib.import_module(
            "app.task.MaaFW.tools.core.automas_maafw_runner.environment"
        ),
        mock.patch.dict(sys.modules, {}),
    )


class ProjectRuntimePathTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module, patcher = load()
        patcher.start()
        self.addCleanup(patcher.stop)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)

    def _project(self, relative: str | None) -> Path:
        root = self.base / str(abs(hash(relative)))
        root.mkdir(parents=True, exist_ok=True)
        if relative is not None:
            target = root / relative
            target.mkdir(parents=True, exist_ok=True)
            (target / "MaaFramework.dll").write_bytes(b"")
        return root

    def test_bundled_maafw_directory_wins(self) -> None:
        root = self._project("maafw")
        self.assertEqual(self.module.project_maafw_runtime_path(root), root / "maafw")

    def test_dotnet_native_layout_is_found(self) -> None:
        """MFAAvalonia 的布局，此前落空。"""

        root = self._project("runtimes/win-x64/native")
        self.assertEqual(
            self.module.project_maafw_runtime_path(root),
            root / "runtimes" / "win-x64" / "native",
        )

    def test_flat_win_x64_layout_still_works(self) -> None:
        root = self._project("runtimes/win-x64")
        self.assertEqual(
            self.module.project_maafw_runtime_path(root),
            root / "runtimes" / "win-x64",
        )

    def test_maafw_wins_over_runtimes(self) -> None:
        root = self._project("maafw")
        (root / "runtimes" / "win-x64" / "native").mkdir(parents=True)
        (root / "runtimes" / "win-x64" / "native" / "MaaFramework.dll").write_bytes(b"")
        self.assertEqual(self.module.project_maafw_runtime_path(root), root / "maafw")

    def test_project_without_a_bundled_runtime_falls_back(self) -> None:
        """没有自带 DLL 时回落 venv —— 返回 None，由调用方走默认路径。"""

        self.assertIsNone(self.module.project_maafw_runtime_path(self._project(None)))

    def test_none_project_is_tolerated(self) -> None:
        self.assertIsNone(self.module.project_maafw_runtime_path(None))

    def test_directory_without_the_dll_is_not_accepted(self) -> None:
        root = self.base / "empty-maafw"
        (root / "maafw").mkdir(parents=True)
        self.assertIsNone(self.module.project_maafw_runtime_path(root))


class RelocatedLayoutFallbackTest(unittest.TestCase):
    """布局挪了位置也要找得到，而不是静默回落 venv。"""

    def setUp(self) -> None:
        self.module, patcher = load()
        patcher.start()
        self.addCleanup(patcher.stop)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)

    def _with_dll_at(self, relative: str) -> Path:
        root = self.base / relative.replace("/", "_")
        target = root / relative
        target.mkdir(parents=True, exist_ok=True)
        (target / "MaaFramework.dll").write_bytes(b"")
        return root

    def test_unknown_but_shallow_layout_is_found(self) -> None:
        for relative in ("bin/native/win64", "lib/framework", "native"):
            with self.subTest(layout=relative):
                root = self._with_dll_at(relative)
                self.assertEqual(
                    self.module.project_maafw_runtime_path(root),
                    root / Path(relative),
                )

    def test_other_runtime_identifiers_are_not_hardcoded_away(self) -> None:
        """win-x64 是写死的会漏掉 arm64 / linux。"""

        for rid in ("win-arm64", "linux-x64", "osx-arm64"):
            with self.subTest(rid=rid):
                root = self._with_dll_at(f"runtimes/{rid}/native")
                self.assertEqual(
                    self.module.project_maafw_runtime_path(root),
                    root / "runtimes" / rid / "native",
                )

    def test_too_deep_is_not_picked_up(self) -> None:
        """深处那份多半是项目自带解释器里的副本，属于 agent 而非外壳。"""

        root = self._with_dll_at("a/b/c/d/e")
        self.assertIsNone(self.module.project_maafw_runtime_path(root))

    def test_shallowest_wins(self) -> None:
        root = self._with_dll_at("bin")
        deep = root / "bin" / "x" / "y"
        deep.mkdir(parents=True)
        (deep / "MaaFramework.dll").write_bytes(b"")
        self.assertEqual(self.module.project_maafw_runtime_path(root), root / "bin")

    def test_known_layout_still_wins_over_the_search(self) -> None:
        root = self._with_dll_at("maafw")
        other = root / "bin"
        other.mkdir(parents=True)
        (other / "MaaFramework.dll").write_bytes(b"")
        self.assertEqual(self.module.project_maafw_runtime_path(root), root / "maafw")


class RealTargetLayoutsTest(unittest.TestCase):
    """真靶子布局回归（靶子不在本机时跳过）。"""

    TARGETS = Path("D:/MAS/tmp/maafw-embedded-target")
    CASES = {
        "M9A-win-x86_64-v4.7.1-MFAA": "runtimes/win-x64/native",
        "M9A-win-x86_64-v4.7.1-MXU": "maafw",
        "MaaYYs-win-x86_64-v3.14.8-MXU": "maafw",
        "MaaEnd-win-x86_64-v2.26.0": "maafw",
        "Maa_bbb-win-x86_64-v1.12.14": "maafw",
    }

    def setUp(self) -> None:
        self.module, patcher = load()
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_every_target_resolves_to_its_own_runtime(self) -> None:
        for name, expected in self.CASES.items():
            root = self.TARGETS / name
            if not root.is_dir():
                self.skipTest(f"靶子不在本机: {name}")
            with self.subTest(target=name):
                resolved = self.module.project_maafw_runtime_path(root)
                self.assertIsNotNone(resolved, f"{name} 回落到了 venv")
                self.assertEqual(resolved, root / Path(expected))


if __name__ == "__main__":
    unittest.main()
