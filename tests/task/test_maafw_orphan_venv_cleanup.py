r"""已无脚本引用的 agent 隔离 venv 要被回收。

这些 venv 每个几十到上百 MB（实测两个共 280MB），而在此之前**没有任何回收**
——只有「同一项目依赖变了就重建」那一条（`_reset_isolated_venv`）。用户删脚本、
改项目路径、或项目升级换了目录，旧 venv 都会永远留着。

实测残留证据：`config/maafw_agent_venvs` 下有一份清单写着
`D:\MASeds\Maa_bbb-win-x86_64-v1.12.10`，而用户早已升级到 v1.12.14。

判定不读目录内的清单：目录名就是项目路径的哈希（`compute_isolated_venv_path`），
把所有仍被脚本引用的路径算成目录名，剩下的即孤儿。这样清单损坏也不会误判，
而**存活项目的 venv 永远不会落进结果里**——这是最重要的性质。
"""

import tempfile
import unittest
from pathlib import Path

import app.core  # noqa: F401  # 初始化宿主配置

from app.task.MaaFW.tools.core.automas_maafw_agent_env.planner import (
    collect_orphan_agent_venvs,
    compute_isolated_venv_path,
)


class OrphanDetectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "maafw_agent_venvs"
        self.root.mkdir(parents=True)

    def _venv_for(self, project: str) -> Path:
        path = compute_isolated_venv_path(project, managed_env_root=self.root)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _names(self, live) -> set[str]:
        return {p.name for p in collect_orphan_agent_venvs(self.root, live)}

    def test_a_live_project_is_never_collected(self) -> None:
        self._venv_for(r"D:\proj\alpha")
        self.assertEqual(self._names([r"D:\proj\alpha"]), set())

    def test_an_unreferenced_project_is_collected(self) -> None:
        stale = self._venv_for(r"D:\proj\old-v1")
        self._venv_for(r"D:\proj\new-v2")
        self.assertEqual(self._names([r"D:\proj\new-v2"]), {stale.name})

    def test_no_live_scripts_collects_everything(self) -> None:
        a = self._venv_for(r"D:\proj\a")
        b = self._venv_for(r"D:\proj\b")
        self.assertEqual(self._names([]), {a.name, b.name})

    def test_path_case_and_separators_do_not_cause_false_positives(self) -> None:
        """Windows 上路径大小写不同指的是同一个项目，不能误判成孤儿。"""

        self._venv_for(r"D:\Proj\Alpha")
        self.assertEqual(self._names([r"d:\proj\alpha"]), set())

    def test_unrelated_directories_are_left_alone(self) -> None:
        """只认 maafw_venv_ 前缀，别人的目录一律不碰。"""

        (self.root / "some-other-tool").mkdir()
        (self.root / "notes.txt").write_text("x", encoding="utf-8")
        self._venv_for(r"D:\proj\alpha")
        self.assertEqual(self._names([r"D:\proj\alpha"]), set())
        self.assertTrue((self.root / "some-other-tool").is_dir())

    def test_a_broken_manifest_does_not_matter(self) -> None:
        """判定只看目录名，清单损坏不影响结论。"""

        live = self._venv_for(r"D:\proj\alpha")
        (live / ".auto_mas_agent_env.json").write_text("{ 坏的", encoding="utf-8")
        self.assertEqual(self._names([r"D:\proj\alpha"]), set())

    def test_missing_root_is_not_an_error(self) -> None:
        self.assertEqual(
            collect_orphan_agent_venvs(self.root / "nope", [r"D:\proj\a"]), []
        )


class SweepWiringTest(unittest.TestCase):
    """清理要真的被调用，且只做一次。"""

    def test_check_triggers_the_sweep(self) -> None:
        source = (
            Path(__file__).resolve().parents[2]
            / "app/task/MaaFW/embedded_manager.py"
        ).read_text(encoding="utf-8")
        self.assertIn("_sweep_orphan_agent_venvs_once()", source)
        # 一次进程只扫一遍
        self.assertIn("_ORPHAN_SWEEP_DONE", source)

    def test_the_sweep_only_considers_maafw_scripts(self) -> None:
        source = (
            Path(__file__).resolve().parents[2]
            / "app/task/MaaFW/embedded_manager.py"
        ).read_text(encoding="utf-8")
        flat = " ".join(source.split())
        self.assertIn("isinstance(config, MaaFWConfig)", flat)

    def test_cleanup_failure_does_not_block_the_run(self) -> None:
        """回收磁盘不该挡住运行。"""

        source = (
            Path(__file__).resolve().parents[2]
            / "app/task/MaaFW/embedded_manager.py"
        ).read_text(encoding="utf-8")
        sweep = source[source.index("def _sweep_orphan_agent_venvs_once"):]
        sweep = sweep[: sweep.index("\nclass ")]
        self.assertIn("except Exception", sweep)
        self.assertIn("except OSError", sweep)
        self.assertNotIn("raise", sweep)


if __name__ == "__main__":
    unittest.main()
