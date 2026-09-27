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

"""安装编排：把版本管理给出的「状态 + 清单」翻译成动作序列。

    build_plan(client)   -> UpdatePlan      只算不做（联网问清单，不写盘）
    execute(plan, client) -> InstallResult   逐文件取回落盘，成功才写回版本号

主干::

    state = version.get_state()
    NotInstalled / GameBroken -> SophonInstall   （不自动执行）
    Installed                 -> Noop / 预下载
    NeedsUpdate               -> 问主清单 + 问差分
                                  有本机基线的差分 -> SophonPatch（自动执行）
                                  没有             -> SophonUpdate（不自动执行）

只有 ``SophonPatch`` 会下载：其余三种都要么没有增量、要么整份客户端还没落地，无人
值守时把它们跑完，就是替用户决定一整份客户端的流量去哪。

同一款客户端可能被多个用户的任务同时用到，所以按游戏目录串行：``game_dir_lock`` 内跑完
一轮再交给下一个。
"""

from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from app.services.gi_updater.api import (
    fetch_branches,
    fetch_main_manifest_ref,
    fetch_manifest_bytes,
    fetch_patch_manifest_ref,
)
from app.services.gi_updater.common import (
    AbortHook,
    ProgressHook,
    Throttle,
    get_logger,
    summarize_size,
)
from app.services.gi_updater.patch import (
    AssetSummary,
    BlobUrls,
    PatchAsset,
    apply_asset,
    build_patch_assets,
    remove_unused,
    summarize_assets,
)
from app.services.gi_updater.presets import PresetConfig
from app.services.gi_updater.sophon import (
    parse_sophon_manifest,
    parse_sophon_patch,
)
from app.services.gi_updater.versioning import (
    GameInstallStateEnum,
    GameVersion,
    GameVersionBase,
)

__all__ = ["UpdateKind", "UpdatePlan", "InstallResult", "InstallManagerBase"]

#: 同时处理的文件数；下载与打补丁都在这一个上限内
_WORKERS = 6
#: 中间产物目录（建在游戏目录内，保证与目标同卷，替换才是原子改名）
_TEMP_DIR_NAME = "_mas_update"
#: 进度行推送的最小间隔（秒）；阶段变化不受此限
_PROGRESS_INTERVAL_SEC = 1.0


class UpdateKind(str, Enum):
    """本次更新要走的路径。"""

    #: 全新安装：本机没有客户端，官方没有增量可用
    SophonInstall = "sophon-install"
    #: 增量更新：差分清单里有本机基线对应的分片
    SophonPatch = "sophon-patch"
    #: 全量比较：拿不到增量，只能逐文件比对重下
    SophonUpdate = "sophon-update"
    #: 预下载下一版本
    SophonPreload = "sophon-preload"
    #: 无需动作
    Noop = "noop"
    #: 联网问不出结论，由宿主按「无法判定」放行
    Unknown = "unknown"


@dataclass
class UpdatePlan:
    """一次更新的完整计划（只算不做的产物）。"""

    kind: UpdateKind = UpdateKind.Noop
    state: GameInstallStateEnum = GameInstallStateEnum.Installed
    source_version: Optional[GameVersion] = None
    target_version: Optional[GameVersion] = None
    #: 待处理明细（只有 SophonPatch 才有）
    assets: List[PatchAsset] = field(default_factory=list)
    #: 本轮淘汰的旧文件（只有 SophonPatch 才有）
    removals: List[str] = field(default_factory=list)
    #: 取数据用的两处基址（只有 SophonPatch 才有）
    urls: Optional[BlobUrls] = None
    summary: AssetSummary = field(default_factory=AssetSummary)
    #: 面向用户的一句话结论：``kind == Unknown`` 时是问不出的原因
    message: str = ""

    @property
    def is_preload(self) -> bool:
        """本次计划是否为预下载。"""
        return self.kind == UpdateKind.SophonPreload

    @property
    def needs_action(self) -> bool:
        """是否需要真正下载与写盘。"""
        return self.kind not in (UpdateKind.Noop, UpdateKind.Unknown)

    @property
    def file_count(self) -> int:
        """本轮要处理的文件数。"""
        return self.summary.file_count

    @property
    def total_size(self) -> int:
        """本轮要从网络取的字节数（降级的按整文件计）。"""
        return self.summary.download_size

    @property
    def disk_need(self) -> int:
        """磁盘门禁要的空间：要下的量加单个文件更新后的峰值。

        差分包过手即删，真正长驻磁盘的是更新后的新文件；只按下载量放行会在盘紧的机器上
        下载到一半写满。
        """
        return self.summary.download_size + self.summary.largest_target


@dataclass
class InstallResult:
    """一轮执行的结果。"""

    kind: UpdateKind = UpdateKind.Noop
    success: bool = False
    message: str = ""
    version: str = ""
    file_total: int = 0
    file_done: int = 0
    file_failed: int = 0
    #: 走整文件降级的文件数
    downgraded: int = 0
    #: 从网络取回的字节数
    bytes_downloaded: int = 0
    removed: int = 0
    aborted: bool = False

    def __str__(self) -> str:  # pragma: no cover
        """人类可读的一行结果。"""
        return (
            f"{self.kind.value}: {'成功' if self.success else '失败'} "
            f"({self.file_done}/{self.file_total} 文件，失败 {self.file_failed})"
        )


_game_dir_locks: Dict[str, asyncio.Lock] = {}


def game_dir_lock(game_path: str) -> asyncio.Lock:
    """取该游戏目录的串行锁（同一目录的多个任务不并发写盘）。"""
    key = os.path.normcase(os.path.abspath(game_path))
    lock = _game_dir_locks.get(key)
    if lock is None:
        lock = _game_dir_locks[key] = asyncio.Lock()
    return lock


class InstallManagerBase:
    """安装管理基类；每款游戏通过子类覆写少量钩子。"""

    def __init__(
        self,
        preset: PresetConfig,
        version_manager: GameVersionBase,
        game_path: Optional[str] = None,
        *,
        logger: Any = None,
    ) -> None:
        """初始化安装管理器。

        Args:
            logger: 日志对象；缺省时取模块默认 logger。
        """
        self.preset = preset
        self.version = version_manager
        self.logger = logger or get_logger()
        if game_path:
            self.version.update_game_path(game_path, save=False)

    @property
    def game_path(self) -> str:
        """游戏安装根目录（代理到 ``version.game_path``）。"""
        return self.version.game_path

    # ================================================================== 只算不做

    async def build_plan(self, client: Any) -> UpdatePlan:
        """问出「这次该怎么更新」，不写任何文件。
        Returns:
            :class:`UpdatePlan`。只有增量路径会带上待处理明细，其余三种给出结论即返回。

        Raises:
            UpdaterError: 接口失败、清单缺项或清单解不开——由调用方按「无法判定」处理。
        """
        main, preload = await fetch_branches(client, self.preset)
        self.version.apply_branches(main.tag, preload.tag if preload else "")
        state = self.version.get_state()
        plan = UpdatePlan(state=state, source_version=self.version.installed_version)
        plan.target_version = self.version.latest_version

        if state in (
            GameInstallStateEnum.NotInstalled,
            GameInstallStateEnum.GameBroken,
        ):
            # 全新安装与「有可执行文件却没版本号」都交给官方启动器：让调度任务往一个
            # 没装过游戏的目录里灌一整份客户端，是不可挽回的浪费
            plan.kind = UpdateKind.SophonInstall
            return plan

        if state == GameInstallStateEnum.InstalledHavePreload:
            plan.kind = UpdateKind.SophonPreload
            plan.target_version = self.version.preload_version
            return plan

        if state == GameInstallStateEnum.Installed:
            plan.kind = UpdateKind.Noop
            return plan

        baseline = self.version.installed_version
        if baseline is None:
            # 读不出本机版本就无从谈起增量：交给官方启动器，别按全新安装硬来
            plan.kind = UpdateKind.SophonUpdate
            plan.message = "读不出本机游戏版本，无法定位差分基线"
            return plan

        target_ref = await fetch_main_manifest_ref(client, self.preset, main)
        patch_ref = await fetch_patch_manifest_ref(
            client, self.preset, main, baseline.sophon_tag
        )
        if patch_ref is None:
            plan.kind = UpdateKind.SophonUpdate
            plan.message = (
                f"官方没有下发 {baseline.sophon_tag} -> "
                f"{main.tag} 的差分包，只能逐文件全量比对"
            )
            return plan

        target_assets = parse_sophon_manifest(
            await fetch_manifest_bytes(client, target_ref)
        ).assets
        patch_manifest = parse_sophon_patch(
            await fetch_manifest_bytes(client, patch_ref)
        )
        assets, removals = build_patch_assets(
            patch_manifest, target_assets, baseline.sophon_tag, self.protected_names()
        )
        plan.assets = self.filter_assets(assets)
        plan.removals = removals
        plan.urls = BlobUrls(
            diff_prefix=patch_ref.chunk_url_prefix,
            diff_compressed=patch_ref.chunk_compressed,
            main_prefix=target_ref.chunk_url_prefix,
            main_compressed=target_ref.chunk_compressed,
        )
        plan.summary = await summarize_assets(plan.assets, self.game_path)
        plan.kind = UpdateKind.SophonPatch
        return plan

    # ================================================================== 执行

    async def execute(
        self,
        plan: UpdatePlan,
        client: Any,
        *,
        hpatchz: Optional[str] = None,
        on_progress: ProgressHook | None = None,
        should_abort: AbortHook | None = None,
    ) -> InstallResult:
        """按计划逐文件取回落盘，全部成功才写回版本号。
        Returns:
            :class:`InstallResult`。单个文件失败不会中断整轮：失败的文件记数，
            其余继续——一次更新上千个文件，因为一个坏文件停手会让用户反复从头开始。
        """
        result = InstallResult(kind=plan.kind, file_total=plan.file_count)
        if plan.kind is not UpdateKind.SophonPatch or plan.urls is None:
            result.success = True
            result.message = "本轮没有需要自动执行的增量"
            return result

        game_path = self.game_path
        temp_dir = os.path.join(game_path, _TEMP_DIR_NAME)
        await asyncio.to_thread(os.makedirs, temp_dir, exist_ok=True)
        throttle = Throttle(_PROGRESS_INTERVAL_SEC)
        pending = list(plan.assets)

        async with game_dir_lock(game_path):
            while pending:
                if should_abort is not None and should_abort():
                    result.aborted = True
                    result.message = (
                        f"更新已中止（已完成 {result.file_done}/{plan.file_count} 个）；"
                        "已落盘的文件保留，重新运行会接着更新"
                    )
                    return result
                batch, pending = pending[:_WORKERS], pending[_WORKERS:]
                outcomes = await asyncio.gather(
                    *(
                        apply_asset(
                            client,
                            game_path,
                            temp_dir,
                            asset,
                            plan.urls,
                            hpatchz=hpatchz,
                            logger=self.logger,
                        )
                        for asset in batch
                    ),
                    return_exceptions=True,
                )
                for asset, outcome in zip(batch, outcomes):
                    if isinstance(outcome, BaseException):
                        result.file_failed += 1
                        self.logger.warning("%s 处理失败: %s", asset.name, outcome)
                        continue
                    fetched, downgraded = outcome
                    result.bytes_downloaded += fetched
                    result.downgraded += int(downgraded)
                    result.file_done += 1
                if on_progress is not None and throttle.ready():
                    await on_progress(
                        f"已处理 {result.file_done}/{plan.file_count} 个文件"
                        f" · 已取回 {summarize_size(result.bytes_downloaded)}"
                        + (
                            f" · 整文件重下 {result.downgraded} 个"
                            if result.downgraded
                            else ""
                        )
                    )

            result.success = result.file_failed == 0
            if result.success:
                result.removed = await remove_unused(
                    game_path, plan.removals, self.logger
                )
                self.finalize()
            else:
                result.message = f"{result.file_failed} 个文件未能落盘"
            return result

    # ================================================================== 钩子

    def filter_assets(self, assets: List[PatchAsset]) -> List[PatchAsset]:
        """钩子：剔除这款游戏不该下的文件；基类原样返回。"""
        return assets

    def protected_names(self) -> List[str]:
        """钩子：清单要求删除也必须留下的文件名（可执行文件与客户端配置）。"""
        return [name for name in (self.preset.executable_name, "config.ini") if name]

    def validate_exec_data_dir(self) -> bool:
        """钩子：可执行目录本身是否有效（防不同区服混装）；基类认为总是有效。"""
        return True

    # ================================================================== 收尾

    def finalize(self) -> None:
        """把「已更新」落盘：写 ``config.ini`` 的版本号与频道信息，再重载本地版本。

        这是唯一把更新结果写盘的地方，只在整轮零失败时调用。
        """
        self.version.update_game_version_to_latest(save=True)
        self.version.reload()

    def cleanup_temp(self) -> List[str]:
        """删掉本轮的中间产物目录，返回处理过的路径。

        切片与差分文件都落在游戏目录内的 ``_mas_update``，成功失败都可以直接删——落盘是
        原子替换，没落盘的本轮就不认。
        """
        temp_dir = os.path.join(self.game_path, _TEMP_DIR_NAME)
        if not os.path.isdir(temp_dir):
            return []
        try:
            shutil.rmtree(temp_dir)
        except OSError as error:
            self.logger.warning("清理中间产物目录失败 %s: %s", temp_dir, error)
            return [temp_dir]
        return [temp_dir]
