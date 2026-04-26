#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from app.utils import get_logger

logger = get_logger("Git服务")


class GitService:
    """Provides async access to Git repository version information."""

    def __init__(self, repo: Any, loop: asyncio.AbstractEventLoop) -> None:
        """
        Args:
            repo: A ``git.Repo`` instance (or ``None`` if Git is unavailable).
            loop: The running asyncio event loop used for executor calls.
        """
        self._repo = repo
        self._loop = loop

    async def get_git_version(self) -> tuple[bool, str, str]:
        """获取Git版本信息，如果Git不可用则返回默认值"""

        def _get_git_info() -> tuple[bool, str, str]:
            if self._repo is None:
                logger.warning("Git仓库不可用，返回默认版本信息")
                return False, "unknown", "unknown"

            # 获取当前 commit
            current_commit = self._repo.head.commit
            # 获取 commit 哈希
            commit_hash = current_commit.hexsha
            # 获取 commit 时间
            commit_time = datetime.fromtimestamp(current_commit.committed_date)

            # 检查是否为最新 commit
            try:
                # 获取远程分支的最新 commit
                origin = self._repo.remotes.origin
                origin.fetch()  # 拉取最新信息
                remote_commit = self._repo.commit(
                    f"origin/{self._repo.active_branch.name}"
                )
                is_latest = bool(current_commit.hexsha == remote_commit.hexsha)
            except (ValueError, OSError) as e:
                logger.warning(f"无法获取远程分支信息: {e}")
                is_latest = False

            return is_latest, commit_hash, commit_time.strftime("%Y-%m-%d %H:%M:%S")

        # 在线程池中执行 Git 操作
        is_latest, commit_hash, commit_time = await self._loop.run_in_executor(
            None, _get_git_info
        )
        return is_latest, commit_hash, commit_time
