#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""装配层：把 ``PresetConfig`` + 版本管理 + 安装编排拼成一套可用的更新器。

对外只有一个入口 :func:`create_updater`。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, List, Optional

from app.services.gi_updater.api.client import HttpClient
from app.services.gi_updater.api.launcher_api import LauncherApi
from app.services.gi_updater.api.profiles import PresetConfig, get_profile
from app.services.gi_updater.common.logging import get_logger
from app.services.gi_updater.common.progress import ProgressBase, SpeedLimiter
from app.services.gi_updater.games.genshin import GenshinInstaller
from app.services.gi_updater.install import InstallManagerBase, UpdatePlan
from app.services.gi_updater.versioning import GameTypeGenshinVersion, GameVersionBase

__all__ = [
    "GameUpdater",
    "GenshinInstaller",
    "create_updater",
]


@dataclass
class GameUpdater:
    """一次更新流程所需的全部对象，按装配关系聚成一个门面对象。"""

    preset: PresetConfig
    version_manager: GameVersionBase
    installer: InstallManagerBase
    launcher_api: Optional[LauncherApi] = None
    client: Optional[HttpClient] = None

    # ---------------------------------------------------------------- 便捷转发

    @property
    def game_path(self) -> str:
        """游戏安装根目录（转发到 ``version_manager.game_path``）。"""
        return self.version_manager.game_path

    @property
    def profile_name(self) -> str:
        """预设名称（转发到 ``preset.profile_name``）。"""
        return self.preset.profile_name

    def refresh(self, *, with_api: bool = True) -> None:
        """刷新本地版本缓存，并按需联网拉远程元数据。

        Args:
            with_api: 是否联网拉取 ``launcher_api``。置 ``False`` 时只重载本地版本，
                供离线自测使用。

        Note:
            installer 也持有 ``launcher_api`` 的引用，必须同步更新，
            否则创建时未联网的实例会一直拿到 ``None``。
        """
        self.version_manager.reload()
        if with_api:
            self.launcher_api = LauncherApi.load(
                self.preset, self.client or HttpClient()
            )
            self.version_manager.launcher_api = self.launcher_api
            self.installer.launcher_api = self.launcher_api

    def check(self) -> UpdatePlan:
        """检查更新：联网拉元数据并算出计划，不下载、不写盘。

        Returns:
            计划的完整结果（含 ``kind`` / 目标版本 / 资产清单等）。
        """
        self.refresh(with_api=True)
        return self.installer.build_plan()


def create_updater(
    region: str = "cn",
    game_path: Optional[str] = None,
    *,
    profile_dir: Optional[str] = None,
    client: Optional[HttpClient] = None,
    progress: Optional[ProgressBase] = None,
    speed_limiter: Optional[SpeedLimiter] = None,
    logger: Any = None,
    thread_count: int = 4,
    chunk_thread_count: int = 8,
    voice_languages: Optional[List[str]] = None,
    dry_run: bool = False,
    should_abort: Optional[Callable[[], bool]] = None,
    hdiff_executable: Optional[str] = None,
) -> GameUpdater:
    """按区服装配一整套原神更新器。

    Args:
        region: 区服，``cn`` / ``global``。
        game_path: 游戏安装目录；``None`` 时由版本管理器自行探测。
        profile_dir: 预设/缓存目录；缺省由版本管理器自行决定。
        client: HTTP 客户端；缺省时新建 ``HttpClient``。
        progress: 进度对象；可为 ``None``。
        speed_limiter: 限速器；可为 ``None``。
        logger: 日志对象；缺省时取模块默认 logger。
        thread_count: 文件级下载线程数（默认 4）。
        chunk_thread_count: 单文件分块下载线程数（默认 8）。
        voice_languages: 要保留的语音 locale code 列表，决定下载哪些语音包。
        dry_run: 演练模式——只决策/估算，不联网拉资产、不写盘。
        should_abort: 协作式中止判定，下载在资产与数据块边界轮询它；
            ``None`` 表示不可中止。
        hdiff_executable: ``hpatchz`` 可执行文件路径；缺省时按 ``PATH`` 查找。

    Returns:
        聚合了 ``preset`` / ``version_manager`` / ``installer`` 的门面对象。
    """
    logger = logger or get_logger()
    preset = get_profile(region)
    client = client or HttpClient(logger=logger)

    version_manager = GameTypeGenshinVersion(preset, None, game_path)
    version_manager.profile_dir = profile_dir

    installer = GenshinInstaller(
        preset,
        version_manager,
        None,
        client,
        game_path,
        progress=progress,
        speed_limiter=speed_limiter,
        logger=logger,
        thread_count=thread_count,
        chunk_thread_count=chunk_thread_count,
        dry_run=dry_run,
    )
    installer.should_abort = should_abort
    installer.hdiff_executable = hdiff_executable
    if voice_languages:
        installer.sophon_voice_languages = list(voice_languages)

    return GameUpdater(
        preset=preset,
        version_manager=version_manager,
        installer=installer,
        client=client,
    )
