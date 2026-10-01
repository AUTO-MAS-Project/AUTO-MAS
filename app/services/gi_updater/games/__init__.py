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

"""装配层：按游戏短名把 ``PresetConfig`` + 版本管理 + 安装编排拼成可用的更新器。

对外只有一个入口 :func:`create_updater`。它不认得具体是哪款游戏——每个游戏的类由
:mod:`~app.services.gi_updater.games.spec` 的注册表给出，游戏模块在被导入时自行登记。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from app.services.gi_updater.common import AbortHook, ProgressHook, get_logger

# 导入即登记：每个游戏模块在自己文件末尾调 ``register``；加新游戏就在此追加一行
from app.services.gi_updater.games import genshin as _genshin  # noqa: F401
from app.services.gi_updater.games.spec import GameSpec, get_spec
from app.services.gi_updater.install import (
    InstallManagerBase,
    InstallResult,
    UpdateKind,
    UpdatePlan,
)
from app.services.gi_updater.presets import GameKey, PresetConfig, get_profile
from app.services.gi_updater.versioning import GameVersionBase

__all__ = [
    "GameSpec",
    "GameUpdater",
    "create_updater",
    "get_spec",
]


@dataclass
class GameUpdater:
    """一次更新流程所需的全部对象，按装配关系聚成一个门面对象。"""

    preset: PresetConfig
    version_manager: GameVersionBase
    installer: InstallManagerBase

    @property
    def game_path(self) -> str:
        """游戏安装根目录（代理到版本管理器）。"""
        return self.version_manager.game_path

    async def check(self, client: Any) -> UpdatePlan:
        """联网问出「这次该怎么更新」，不下载、不写盘。
        Returns:
            :class:`UpdatePlan`。问不出结论时不抛异常，给出 ``kind=Unknown`` 并带上原因。

        Note:
            兜住的是协议层：HTTP 失败、响应信封不是对象、``retcode`` 非 0、清单缺项、
            zstd 与 protobuf 解不开。这些都只说明「这次问不出来」，不代表用户的客户端
            坏了，也不该让调度任务失败。区服写错在 :func:`create_updater` 里就报了，
            不会被这里吞掉。
        """
        try:
            return await self.installer.build_plan(client)
        except Exception as error:  # noqa: BLE001 —— 协议层的形状变化不止一种，逐条枚举没有意义
            self.installer.logger.warning(
                "问不出该怎么更新，本轮按无法判定处理: %s: %s",
                type(error).__name__,
                error,
            )
            return UpdatePlan(
                kind=UpdateKind.Unknown,
                source_version=self.version_manager.installed_version,
                message=f"{type(error).__name__}: {error}",
            )

    async def execute(
        self,
        plan: UpdatePlan,
        client: Any,
        *,
        hpatchz: Optional[str] = None,
        on_progress: ProgressHook | None = None,
        should_abort: AbortHook | None = None,
    ) -> InstallResult:
        """按计划下载并落盘。"""
        return await self.installer.execute(
            plan,
            client,
            hpatchz=hpatchz,
            on_progress=on_progress,
            should_abort=should_abort,
        )


def create_updater(
    game: str = GameKey.Genshin,
    region: str = "cn",
    game_path: Optional[str] = None,
    *,
    profile_dir: Optional[str] = None,
    logger: Any = None,
) -> GameUpdater:
    """按游戏与区服装配一整套更新器。

    Args:
        profile_dir: 预设/缓存目录；缺省由版本管理器自行决定。
        logger: 日志对象；缺省时按游戏名取。

    Returns:
        聚合了 ``preset`` / ``version_manager`` / ``installer`` 的门面对象。

    Raises:
        ValueError: 这款游戏在该区服没有内置预设。
    """
    spec = get_spec(game)
    logger = logger or get_logger(f"{spec.display_name}更新")
    preset = get_profile(spec.key, region)

    version_manager = spec.version_cls(preset, game_path)
    version_manager.profile_dir = profile_dir
    installer = spec.installer_cls(preset, version_manager, game_path, logger=logger)
    return GameUpdater(
        preset=preset, version_manager=version_manager, installer=installer
    )
