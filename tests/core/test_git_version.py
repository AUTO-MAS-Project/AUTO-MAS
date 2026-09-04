"""AppConfig.get_git_version 在受监督布局下的行为回归。

受 AUTO-MAS-Runtime 监督时源码在 <app-root>/repo/、工作目录是 <app-root>/，
且更新由 Runtime 整体替换 repo/ 完成：后端既不能再按 Path.cwd() 打开仓库，
也不应再比对远端分支判定“需要更新”。
"""

import asyncio
import os
import sys
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.core import Config
from app.utils.paths import SOURCE_ROOT

EXPECTED_COMMIT = "0123456789abcdef0123456789abcdef01234567"
COMMIT_TIME = datetime(2026, 9, 1, 12, 0, 0)


def _fake_repo(hexsha: str, remote_hexsha: str | None) -> MagicMock:
    """最小 GitPython Repo 替身：HEAD 提交，以及可选的 origin/<branch> 提交。"""

    repo = MagicMock()
    repo.head.commit = SimpleNamespace(
        hexsha=hexsha, committed_date=int(COMMIT_TIME.timestamp())
    )
    repo.active_branch.name = "dev"
    if remote_hexsha is None:
        repo.commit.side_effect = ValueError("origin/dev 不存在")
    else:
        repo.commit.return_value = SimpleNamespace(hexsha=remote_hexsha)
    return repo


class GetGitVersionTest(unittest.IsolatedAsyncioTestCase):
    async def _call(self, env: dict[str, str], repo) -> tuple[bool, str, str]:
        with (
            patch.dict(os.environ, env),
            patch.object(Config, "loop", asyncio.get_running_loop(), create=True),
            patch.object(Config, "_get_repo", return_value=repo) as get_repo,
        ):
            result = await Config.get_git_version()
        self.get_repo = get_repo
        return result

    async def test_managed_supervision_echoes_injected_commit_without_git(self):
        result = await self._call(
            {"AUTO_MAS_SUPERVISED": "1", "AUTO_MAS_EXPECTED_COMMIT": EXPECTED_COMMIT},
            _fake_repo("deadbeef", "cafebabe"),
        )

        # Runtime 布局不带 git 命令行：直接回显注入的 HEAD，不碰 GitPython
        self.assertEqual(result, (True, EXPECTED_COMMIT, "unknown"))
        self.get_repo.assert_not_called()

    async def test_supervised_development_keeps_git_info_but_never_needs_update(self):
        result = await self._call(
            {"AUTO_MAS_SUPERVISED": "1", "AUTO_MAS_EXPECTED_COMMIT": ""},
            _fake_repo("deadbeef", None),
        )

        # development 模式无注入身份：仍展示源码目录的提交，但不判定需要更新
        self.assertEqual(result, (True, "deadbeef", "2026-09-01 12:00:00"))

    async def test_supervised_without_repo_does_not_report_update(self):
        result = await self._call(
            {"AUTO_MAS_SUPERVISED": "1", "AUTO_MAS_EXPECTED_COMMIT": ""}, None
        )

        self.assertEqual(result, (True, "unknown", "unknown"))

    async def test_unsupervised_ignores_injected_commit_and_compares_remote(self):
        result = await self._call(
            {"AUTO_MAS_SUPERVISED": "", "AUTO_MAS_EXPECTED_COMMIT": EXPECTED_COMMIT},
            _fake_repo("deadbeef", "cafebabe"),
        )

        # 未受监督：沿用 HEAD 与 origin/<branch> 的比对
        self.assertEqual(result, (False, "deadbeef", "2026-09-01 12:00:00"))


class GetRepoTest(unittest.TestCase):
    def test_repo_opens_source_root_instead_of_cwd(self):
        fake_git = SimpleNamespace(Repo=MagicMock(return_value="repo"))
        saved = (Config._repo, Config._repo_initialized)
        try:
            Config._repo, Config._repo_initialized = None, False
            with patch.dict(sys.modules, {"git": fake_git}):
                self.assertEqual(Config._get_repo(), "repo")
        finally:
            Config._repo, Config._repo_initialized = saved

        fake_git.Repo.assert_called_once_with(SOURCE_ROOT)


if __name__ == "__main__":
    unittest.main()
