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
    """清理挂在启动流程上，而不是运行前的校验里。

    起初挂在 `MaaFWEmbeddedManager.check()` 上，结果**跑一次测试就把开发者
    磁盘上的真 venv 删了**：check() 是被测试真实调用的，而测试会把
    `Config.ScriptConfig` 换成只含临时项目的替身，于是真 venv 全被判成孤儿。

    两个教训钉在下面：校验方法不得有破坏性副作用；判定依赖「当前全部脚本
    配置」这种全局状态时，只有真实启动时它才可信。
    """

    def _source(self, relative: str) -> str:
        return (Path(__file__).resolve().parents[2] / relative).read_text(
            encoding="utf-8"
        )

    def test_startup_triggers_the_cleanup(self) -> None:
        self.assertIn("await Config.clean_maafw_agent_venvs()", self._source("main.py"))

    def test_check_has_no_destructive_side_effect(self) -> None:
        """校验方法不得删文件——这正是当初出事的地方。"""

        source = self._source("app/task/MaaFW/embedded_manager.py")
        for destructive in ("rmtree", "unlink", "collect_orphan_agent_venvs"):
            with self.subTest(symbol=destructive):
                self.assertNotIn(destructive, source)

    def test_the_cleanup_only_considers_maafw_scripts(self) -> None:
        flat = " ".join(self._source("app/core/config.py").split())
        self.assertIn("isinstance(config, MaaFWConfig)", flat)

    def test_recently_touched_venvs_are_spared(self) -> None:
        """刚动过的一律不碰，避免与正在准备环境的运行抢。"""

        source = self._source("app/core/config.py")
        body = source[source.index("async def clean_maafw_agent_venvs") :]
        body = body[: body.index(chr(10) + "    async def ", 10)]
        self.assertIn("MAAFW_AGENT_VENV_GRACE_SECONDS", body)
        self.assertIn("st_mtime", body)

    def test_cleanup_failure_does_not_block_startup(self) -> None:
        source = self._source("app/core/config.py")
        body = source[source.index("async def clean_maafw_agent_venvs") :]
        body = body[: body.index(chr(10) + "    async def ", 10)]
        self.assertIn("except Exception", body)
        self.assertIn("except OSError", body)
        self.assertNotIn("raise", body)


class TestsMustNotTouchRealVenvsTest(unittest.TestCase):
    """回归：测试套件本身不得删掉真实的 venv 目录。

    这条是被真事逼出来的——一次 pytest 就清空了开发者的
    `config/maafw_agent_venvs`。
    """

    def test_no_test_reaches_the_real_venv_root(self) -> None:
        real_root = Path.cwd() / "config" / "maafw_agent_venvs"
        sentinel = real_root / "maafw_venv_pytest_sentinel"
        created = False
        if real_root.is_dir() and not sentinel.exists():
            sentinel.mkdir()
            created = True
        try:
            from app.task.MaaFW import embedded_manager

            self.assertNotIn("rmtree", Path(embedded_manager.__file__).read_text(
                encoding="utf-8"
            ))
            if created:
                self.assertTrue(sentinel.is_dir())
        finally:
            if created and sentinel.is_dir():
                sentinel.rmdir()


if __name__ == "__main__":
    unittest.main()
