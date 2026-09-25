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

"""安装编排层：把版本管理给出的「状态 + 清单」翻译成动作序列。

    build_plan() -> UpdatePlan    只算不做（联网枚举清单，不写盘）
    execute()    -> InstallResult 真正下载 + 落盘 + 写回版本
    finalize()   -> None          写 game_version / 渠道 / 语音清单

主干：

    state = get_state()
    NotInstalled / GameBroken  -> SophonInstall
    NeedsUpdate                -> SophonPatch（差分清单可得）或 SophonUpdate（全量比较）
    InstalledHavePreload       -> SophonPreload
    Installed                  -> Noop

注意：MAS 的宿主门禁只放行 ``SophonPatch``——全新安装、全量比较与预下载
在无人值守场景一律停手交给官方启动器（zip 全量链路亦未收录）；
:meth:`execute` 因此只实现差分一条路径。
「决策」与「执行」分开，便于先看计划、再落盘。
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence

from app.services.gi_updater.api.client import HttpClient, mask_url_password
from app.services.gi_updater.api.launcher_api import LauncherApi
from app.services.gi_updater.api.profiles import PresetConfig
from app.services.gi_updater.common.logging import get_logger
from app.services.gi_updater.common.progress import ProgressBase
from app.services.gi_updater.common.version import GameVersion
from app.services.gi_updater.download import (
    ExternalHDiffPatcher,
    SophonAsset,
    SophonChunkManifestInfoPair,
    SophonDownloader,
    SophonManifest,
    SophonPatchAsset,
    SophonPatcher,
    build_patch_assets,
)
from app.services.gi_updater.download.sophon import (
    MAIN_MATCHING_FIELD,
    _resolve_target_path,
)
from app.services.gi_updater.versioning import GameInstallStateEnum, GameVersionBase

__all__ = [
    "UpdateKind",
    "UpdatePlan",
    "InstallResult",
    "InstallManagerBase",
]

#: Sophon 清单里可能出现的全部 ``matching_field``
COMMON_SOPHON_PACKAGE_MATCHING_FIELDS = (
    "game",
    "en-us",
    "zh-tw",
    "zh-cn",
    "ko-kr",
    "ja-jp",
)

#: 官方启动器默认保留的语音
DEFAULT_VOICE_LOCALE = "ja-jp"


class UpdateKind(str, Enum):
    """本次更新要走的路径。"""

    #: 全新安装（Sophon 全量清单）
    SophonInstall = "sophon-install"
    #: 更新：Sophon 差分补丁（patch getBuild 可用）
    SophonPatch = "sophon-patch"
    #: 更新：Sophon 全量比较（清单级 diff，逐文件判断是否需要重下）
    SophonUpdate = "sophon-update"
    #: 预下载下一版本
    SophonPreload = "sophon-preload"
    #: 无需动作
    Noop = "noop"


@dataclass
class PatchSpaceNeed:
    """一次差分更新对磁盘的占用估算（见 :meth:`InstallManagerBase.sophon_patch_space_need`）。"""

    #: 本轮还要从网络取的字节数（本地尺寸已对上的文件不计）
    download_left: int = 0
    #: 更新后新文件相对现状的净落盘增量
    write_growth: int = 0
    #: 单个文件的在飞峰值（temp 与旧文件短暂共存 + 一个未删的切片）
    peak: int = 0
    #: 本地尺寸已对上、本轮只需复核不必下载的文件数
    already_done: int = 0

    @property
    def disk_need(self) -> int:
        """放行判断要用的空间：净落盘增量加在飞峰值。

        Returns:
            ``write_growth + peak``；切片是过手即删的中间物，所以不含
            `download_left`。
        """
        return self.write_growth + self.peak


@dataclass
class UpdatePlan:
    """一次更新的完整计划（dry-run 的产物）。"""

    kind: UpdateKind = UpdateKind.Noop
    state: GameInstallStateEnum = GameInstallStateEnum.Installed

    #: 源版本（已安装）/ 目标版本
    source_version: Optional[GameVersion] = None
    target_version: Optional[GameVersion] = None

    #: Sophon 主清单信息对
    main_pair: Optional[SophonChunkManifestInfoPair] = None
    #: Sophon 语音包清单信息对
    voice_pairs: List[SophonChunkManifestInfoPair] = field(default_factory=list)
    #: 差分补丁清单信息对（kind == SophonPatch 时才有）
    patch_pair: Optional[SophonChunkManifestInfoPair] = None
    #: 参与本次下载的 matching_field
    matching_fields: List[str] = field(default_factory=list)

    #: 需要下载/校验的资源（kind 为 SophonInstall/Update 时有效）
    assets: List[SophonAsset] = field(default_factory=list)
    #: 差分资产（kind == SophonPatch 时有效）
    patch_assets: List[SophonPatchAsset] = field(default_factory=list)
    #: 补丁后要删除的旧文件
    removed_files: List[str] = field(default_factory=list)

    #: 统计
    total_size: int = 0
    file_count: int = 0
    #: 差分链路的磁盘占用与本轮待下量估算（``kind == SophonPatch`` 时才有）
    space_need: Optional[PatchSpaceNeed] = None

    @property
    def is_preload(self) -> bool:
        """本次计划是否为预下载。

        Returns:
            ``kind == SophonPreload`` 时为 True。
        """
        return self.kind == UpdateKind.SophonPreload

    @property
    def needs_action(self) -> bool:
        """是否需要真正执行下载/写盘动作。

        Returns:
            ``kind != Noop`` 时为 True；Noop 表示无需更新。
        """
        return self.kind != UpdateKind.Noop

    def describe(self) -> str:
        """生成给人看的一行摘要。

        Returns:
            Noop 时返回「无需更新」；否则含路径、源→目标版本、文件数与大小。
        """
        if self.kind == UpdateKind.Noop:
            return "无需更新"
        size = (
            f"{self.total_size / (1 << 30):.2f} GiB" if self.total_size else "未知大小"
        )
        return (
            f"{self.kind.value} | {self.source_version} -> {self.target_version} | "
            f"{self.file_count} 个文件 | {size}"
        )


@dataclass
class InstallResult:
    """执行结果。"""

    kind: UpdateKind = UpdateKind.Noop
    success: bool = False
    message: str = ""
    version: Optional[GameVersion] = None
    file_total: int = 0
    file_done: int = 0
    file_failed: int = 0
    bytes_downloaded: int = 0
    #: 每种补丁方式各处理了多少文件（SophonPatch 专用）
    method_counts: Dict[str, int] = field(default_factory=dict)

    def __str__(self) -> str:  # pragma: no cover
        """返回人类可读的执行结果摘要（含是否成功与文件数）。"""
        return (
            f"{self.kind.value}: {'成功' if self.success else '失败'} "
            f"({self.file_done}/{self.file_total} 文件，失败 {self.file_failed})"
        )


class InstallManagerBase:
    """安装管理基类；三款游戏通过子类覆写少量钩子。"""

    def __init__(
        self,
        preset: PresetConfig,
        version_manager: GameVersionBase,
        launcher_api: Optional[LauncherApi] = None,
        client: Optional[HttpClient] = None,
        game_path: Optional[str] = None,
        *,
        progress: Optional[ProgressBase] = None,
        logger: Any = None,
        # 下载线程数（默认 4，给界面留出余量）
        thread_count: int = 4,
        chunk_thread_count: int = 8,
        dry_run: bool = False,
    ) -> None:
        """初始化安装管理器。

        Args:
            preset: 预设配置（决定 Sophon 端点、匹配字段等）。
            version_manager: 版本管理器，提供游戏路径/版本/状态。
            launcher_api: 启动器 API 客户端；缺省时复用 ``version_manager`` 的。
            client: HTTP 客户端；缺省时新建 ``HttpClient``。
            game_path: 可选，显式覆盖游戏安装目录（仅本次会话，不落盘）。
            progress: 进度回调；可为 ``None``。
            logger: 日志对象；缺省时取模块默认 logger。
            thread_count: 文件级下载线程数（默认 4）。
            chunk_thread_count: 单文件分块下载线程数（钳制在 1–32）。
            dry_run: 演练模式——只决策/估算，不联网拉资产、不写盘。

        Note:
            仅在传入 ``game_path`` 时调用 ``version.update_game_path(..., save=False)``，
            即不持久化该覆盖路径。
        """
        self.preset = preset
        self.version = version_manager
        self.launcher_api = launcher_api or version_manager.launcher_api
        self.logger = logger or get_logger()

        self.client = client or HttpClient(logger=self.logger)
        self.progress = progress
        self.thread_count = max(1, thread_count)
        self.chunk_thread_count = max(1, min(32, chunk_thread_count))
        #:；本实现只能由调用方显式置真，无自动降级
        self.dry_run = dry_run

        #: 本次流程里选中的语音语言（locale code 列表）
        self.sophon_voice_languages: List[str] = []
        #: 协作式中止判定，透传给下载器与补丁器
        self.should_abort: Optional[Callable[[], bool]] = None
        #: hpatchz 可执行文件路径；None 时按 PATH 查找
        self.hdiff_executable: Optional[str] = None

        if game_path:
            self.version.update_game_path(game_path, save=False)

    # ================================================================== 路径

    @property
    def game_path(self) -> str:
        """游戏安装根目录（代理到 ``version.game_path``）。"""
        return self.version.game_path

    @property
    def preset_urls(self):
        """预设里的 Sophon 端点组。"""
        return self.preset.launcher_resource_chunks_url

    # ================================================================== 计划

    def get_state(self) -> GameInstallStateEnum:
        """读取游戏当前安装状态（代理到版本管理器）。

        Returns:
            当前安装状态（未装/需更新/已装/有预下载等）。
        """
        return self.version.get_state()

    def build_plan(self, state: Optional[GameInstallStateEnum] = None) -> UpdatePlan:
        """只做决策、不做任何下载/写盘（``dry_run`` 也走这里）。

        Args:
            state: 当前安装状态；为 ``None`` 时内部调用 :meth:`get_state`。

        Returns:
            决策结果。无需更新时 ``kind`` 为 ``Noop``；Sophon 链路的
            差分/资产收集仅在确实需要联网时补资源信息，``dry_run`` 下则跳过资产枚举、
            只用 ``getBuild`` 的统计值估算大小/文件数。

        Note:
            本方法「只决策不落盘」；它不下载、不解压、不写 ``config.ini``。
            非演练的 Sophon 路径会联网 ``getBuild`` 拉清单/资产信息。
        """
        state = state or self.get_state()
        plan = UpdatePlan(state=state)
        plan.source_version = self.version.installed_version

        if state == GameInstallStateEnum.InstalledHavePreload:
            self._plan_sophon(plan, is_preload=True)
        elif state in (
            GameInstallStateEnum.NotInstalled,
            GameInstallStateEnum.GameBroken,
        ):
            self._plan_sophon(plan, is_preload=False, kind=UpdateKind.SophonInstall)
        elif state == GameInstallStateEnum.NeedsUpdate:
            self._plan_sophon(plan, is_preload=False)
        else:
            plan.kind = UpdateKind.Noop
        return plan

    # ------------------------------------------------------------ Sophon

    def _plan_sophon(
        self,
        plan: UpdatePlan,
        *,
        is_preload: bool,
        kind: Optional[UpdateKind] = None,
    ) -> None:
        """填充 Sophon 计划：取清单、语音清单、判定差分/更新/预下载。

        写入 ``plan.main_pair`` / ``voice_pairs`` / ``matching_fields`` / ``target_version`` /
        ``patch_pair``（差分）/ ``kind``，并按需收集资产（非 dry-run 时）。

        Args:
            plan: 待填充的计划对象。
            is_preload: 是否走预下载分支（用 pre_download 分支与目标版本）。
            kind: 显式强制路径；为 ``None`` 时按「差分优先、再 SophonUpdate」自动判定。

        Note:
            差分优先于全量更新；但若
            ``is_preload`` 为真则强制降级为 ``SophonPreload``。dry-run 下不联网收集
            资产，只用 ``getBuild`` 的统计值估算大小/文件数。
        """
        pair = self.get_sophon_pair(is_preload=is_preload)
        if pair is None or not pair.is_found:
            self.logger.warning(
                "拿不到 Sophon 清单（%s），计划中止",
                pair.return_message if pair else "?",
            )
            plan.kind = UpdateKind.Noop
            return

        plan.main_pair = pair
        plan.matching_fields = [self.main_matching_field]
        plan.voice_pairs = self.get_voice_pairs(pair)
        plan.matching_fields.extend(
            voice.matching_field for voice in plan.voice_pairs if voice.matching_field
        )
        plan.target_version = (
            self.version.preload_version if is_preload else self.version.latest_version
        )

        # 差分优先
        if kind is None:
            installed = self.version.installed_version
            if (
                installed is not None
                and self.preset_urls is not None
                and self.preset_urls.patch_url
            ):
                # 差分基线要对上响应 stats 里的键，那些键是 3 段版本串（``7.0.0``）；
                # 用解析后的 4 段（``7.0.0.0``）永远对不上，会被判成没有差分
                patch_pair = self.get_sophon_patch_pair(
                    version_update_from=installed.sophon_tag, is_preload=is_preload
                )
                if patch_pair is not None and patch_pair.is_found:
                    plan.patch_pair = patch_pair
                    kind = UpdateKind.SophonPatch
                else:
                    kind = UpdateKind.SophonUpdate
            else:
                kind = UpdateKind.SophonUpdate
        if is_preload:
            kind = UpdateKind.SophonPreload
        plan.kind = kind

        if self.dry_run:
            # 不联网拉清单资产，只用 getBuild 的统计值估算
            pairs = [pair] + plan.voice_pairs
            plan.total_size = sum(
                (p.chunks_info.total_size if p and p.chunks_info else 0) for p in pairs
            )
            plan.file_count = sum(
                (p.chunks_info.files_count if p and p.chunks_info else 0) for p in pairs
            )
            return

        if kind == UpdateKind.SophonPatch:
            self._collect_patch_assets(plan)
        else:
            self._collect_assets(plan, is_preload=is_preload)

    # ------------------------------------------------------------ 清单获取

    @property
    def main_matching_field(self) -> str:
        """Sophon 主清单的匹配字段（如 ``game``）。

        Returns:
            预设 ``main_branch_matching_field``；缺省或为空时回退到
            ``download.sophon.MAIN_MATCHING_FIELD``。
        """
        if self.preset_urls is None:
            return MAIN_MATCHING_FIELD
        return self.preset_urls.main_branch_matching_field or MAIN_MATCHING_FIELD

    def get_sophon_pair(
        self, is_preload: bool = False, matching_field: Optional[str] = None
    ) -> Optional[SophonChunkManifestInfoPair]:
        """构造 ``getBuild`` URL 并取主清单信息对。

        Args:
            is_preload: 是否走预下载分支（用 ``pre_download`` 分支）。
            matching_field: 主清单匹配字段；为 ``None`` 时用 :meth:`main_matching_field`。

        Returns:
            清单信息对；取不到（无 Sophon 端点 /
            无分支 / 未找到清单）时返回 ``None``。

        Note:
            ``tag`` 必须使用 API 返回的**原始 3 段版本串**（如 ``7.0.0``）；
            若补成 4 段（``7.0.0.0``）会被服务端以 ``-202 not found`` 拒绝。
            主清单走 **GET**。这是唯一定位「主清单」的入口。
        """
        if self.preset_urls is None or self.launcher_api is None:
            return None

        branch = (
            (
                self.launcher_api.sophon_branches.pre_download
                if is_preload
                else self.launcher_api.sophon_branches.main
            )
            if self.launcher_api.sophon_branches
            else None
        )
        if branch is None or not branch.package_id:
            return None

        # 注意：tag 必须用 API 返回的原始字符串（如 "7.0.0"），
        # 用补全成 4 段的 VersionString（"7.0.0.0"）会被服务端判为 -202 not found。
        tag = branch.tag or self._raw_target_tag(is_preload)
        url = self.preset.build_get_build_url(
            package_id=branch.package_id,
            branch=branch.branch or "main",
            password=branch.password,
            tag=tag,
        )
        self.logger.debug(
            "getBuild(%s) -> %s",
            "preload" if is_preload else "main",
            mask_url_password(url),
        )

        return SophonManifest.create_info_pair(
            self.client,
            url,
            matching_field or self.main_matching_field,
            throw_if_not_found=False,
            method="GET",
            logger=self.logger,
        )

    def _raw_target_tag(self, is_preload: bool) -> str:
        """取 API 返回的原始版本 tag（未补全 4 段）。

        Args:
            is_preload: 是否取预下载分支的 tag。

        Returns:
            原始版本串（如 ``7.0.0``）；拿不到时回退到已解析版本的
            ``version_string``，再不行返回空串。

        Note:
            必须返回**原始 3 段**版本串——补成 4 段（``7.0.0.0``）会被服务端以
            ``-202 not found`` 拒绝。
        """
        branch = (
            self.version.sophon_preload_branch
            if is_preload
            else self.version.sophon_branch
        )
        if branch is not None and branch.tag:
            return branch.tag
        version = (
            self.version.preload_version if is_preload else self.version.latest_version
        )
        return version.version_string if version else ""

    def get_sophon_patch_pair(
        self, version_update_from: str, is_preload: bool = False
    ) -> Optional[SophonChunkManifestInfoPair]:
        """取 Sophon 差分补丁清单。

        Args:
            version_update_from: 源版本串（作为差分起点，如 ``6.9.0``）。
            is_preload: 是否走预下载分支（patch 用 ``predownload`` 分支）。

        Returns:
            差分清单信息对；无 patch 端点 /
            无分支 / 未找到清单时返回 ``None``。

        Note:
            差分清单走的是独立端点 :cvar:`SophonChunkUrls.patch_url`
            （``getPatchBuild``，只收 POST），与 :meth:`get_sophon_pair` 用的
            ``getBuild``（只收 GET）不通用——发错端点或发错方法都会被服务端判 405。
            基线版本不在 URL 上：响应里每份清单的 ``stats`` 以基线版本为键，
            由调用方按本机已装版本去挑，挑不到即视为没有可用差分。
        """
        if self.preset_urls is None or not self.preset_urls.patch_url:
            return None
        if self.launcher_api is None or self.launcher_api.sophon_branches is None:
            return None

        branch = (
            self.launcher_api.sophon_branches.pre_download
            if is_preload
            else self.launcher_api.sophon_branches.main
        )
        if branch is None or not branch.package_id:
            return None

        # 差分端点的查询串与主清单同形：branch 用主/预下载分支名，
        # package_id 与 password 取该分支下发的值
        url = self.preset.build_sophon_query_url(
            self.preset_urls.patch_url,
            package_id=branch.package_id,
            branch="predownload" if is_preload else "main",
            password=branch.password,
        )
        self.logger.debug(
            "getPatchBuild -> %s (from=%s)",
            mask_url_password(url),
            version_update_from,
        )

        return SophonManifest.create_patch_info_pair(
            self.client,
            url,
            version_update_from,
            self.main_matching_field,
            logger=self.logger,
        )

    def get_voice_pairs(
        self, pair: SophonChunkManifestInfoPair
    ) -> List[SophonChunkManifestInfoPair]:
        """为每个选中的语音语言取对应清单。

        Args:
            pair: 主清单信息对，作为语音清单的母体。

        Returns:
            找到的语音清单；不可用的语言被跳过。
        """
        results: List[SophonChunkManifestInfoPair] = []
        for locale in self.resolve_voice_languages(pair):
            voice_pair = pair.get_other_manifest_info_pair(locale)
            if not voice_pair.is_found:
                self.logger.debug("语音包 %s 不可用，跳过", locale)
                continue
            results.append(voice_pair)
        return results

    def resolve_voice_languages(
        self, pair: Optional[SophonChunkManifestInfoPair] = None
    ) -> List[str]:
        """确定本次要下载的语音语言（locale code 列表）。

        Args:
            pair: 主清单信息对；本实现未使用其字段，仅保留接口兼容，可为 ``None``。

        Returns:
            本次要更新的语音 locale code（已写回 ``self.sophon_voice_languages``）。

        Note:
            策略（**会读盘** ``audio_lang_list_path()``）：
            1. 清单文件存在 -> 逐行经 :meth:`locale_code_from_language_string` 映射；
            2. 否则用 ``self.sophon_voice_languages``（CLI 传入）；
            3. 都没有 -> 回退 ``DEFAULT_VOICE_LOCALE``（默认 ``ja-jp``）。
            ``locale_code_from_language_string`` 是钩子：基类走 locale code，
            原神覆写为语言全名映射。
        """
        languages: List[str] = []
        path = self.version.audio_lang_list_path()
        if path:
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    languages = [
                        self.locale_code_from_language_string(line)
                        for line in handle.read().splitlines()
                        if line.strip()
                    ]
            except OSError:
                languages = []
        languages = [lang for lang in languages if lang]
        if not languages:
            languages = list(self.sophon_voice_languages)
        if not languages:
            languages = [DEFAULT_VOICE_LOCALE]
        self.sophon_voice_languages = languages
        return languages

    def locale_code_from_language_string(self, text: str) -> str:
        """把语言描述映射成 locale code（钩子，子类可覆写）。

        Args:
            text: 语言描述文本（清单里的一行）。

        Returns:
            对应的 locale code（如 ``en-us``）。基类直接 ``strip().lower()``；
            原神覆写为语言全名（``Chinese`` 等）到 locale code 的映射。

        Note:
            与 :meth:`games.genshin.GenshinInstaller.language_string_from_locale_code`
            互为逆函数，但基类不提供逆映射，仅在 Genshin 子类配对实现。
        """
        return text.strip().lower()

    # ------------------------------------------------------------ 资产收集

    def _collect_assets(self, plan: UpdatePlan, *, is_preload: bool) -> None:
        """枚举并过滤 Sophon 主/语音清单的资产，写入 ``plan.assets``。

        Args:
            plan: 计划对象，其 ``main_pair`` / ``voice_pairs`` 必须已就绪。
            is_preload: 是否预下载——决定用 ``exclude_matching_field_preload``
                还是 ``exclude_matching_field_main`` 做排除。

        Note:
            先按 ``exclude`` 列表用 fnmatch 跳过匹配的 ``matching_field``，再交给
            :meth:`filter_assets` 二次过滤；最终用资产数/总大小覆盖 ``plan`` 统计。
        """
        exclude = list(
            (
                self.preset_urls.exclude_matching_field_preload
                if is_preload
                else self.preset_urls.exclude_matching_field_main
            )
            if self.preset_urls
            else []
        )
        pairs = [plan.main_pair] + plan.voice_pairs
        assets: List[SophonAsset] = []
        for pair in pairs:
            if pair is None or not pair.is_found:
                continue
            if pair.matching_field and self._is_excluded(pair.matching_field, exclude):
                continue
            assets.extend(
                SophonManifest.enumerate_assets(self.client, pair, logger=self.logger)
            )

        assets = self.filter_assets(assets)
        plan.assets = assets
        plan.file_count = len(assets)
        plan.total_size = sum(asset.asset_size for asset in assets)

    def _collect_patch_assets(self, plan: UpdatePlan) -> None:
        """构建并过滤 Sophon 差分资产，写入 ``plan.patch_assets`` / ``removed_files``。

        Args:
            plan: 计划对象，其 ``patch_pair`` / ``main_pair`` 必须已就绪。

        Note:
            经 :func:`download.build_patch_assets` 计算「源→目标」差异，按
            `UpdatePlan.source_version` 的 3 段 tag 挑本机基线那份分片；再交给
            :meth:`filter_patch_assets` 二次过滤。体量按 ``patch_chunk_length``
            累加——那才是要从网络取的字节数，与官方差分统计同口径；
            ``patch_size`` 不是下载量，拿它累加会把约 10 GB 的增量报成上百 GB。
            触发前已 ``assert`` 两个清单非空。
        """
        assert plan.patch_pair is not None and plan.main_pair is not None
        assets, removed = build_patch_assets(
            self.client,
            plan.patch_pair,
            plan.main_pair,
            plan.source_version.sophon_tag if plan.source_version else "",
            logger=self.logger,
        )
        assets = self.filter_patch_assets(assets)
        plan.patch_assets = assets
        plan.removed_files = removed
        plan.file_count = len(assets)
        plan.total_size = sum(asset.patch_chunk_length for asset in assets)
        # 顺手把磁盘与本轮待下量算好：门禁与进度分母都用它，stat 只走这一遍
        plan.space_need = self.sophon_patch_space_need(plan)

    def sophon_patch_space_need(self, plan: UpdatePlan) -> PatchSpaceNeed:
        """估算这次差分更新要占多少磁盘。

        Args:
            plan: 已收集好 ``patch_assets`` 的计划（``kind`` 应为 SophonPatch）。

        Returns:
            :class:`PatchSpaceNeed`：本轮还要下的字节、新文件净落盘增量、在飞峰值，
            以及本地尺寸已对上、不必再下的文件数。

        Note:
            「还要不要下」用文件大小做廉价判定（不比对 MD5）：整轮上千个文件逐个
            算哈希会把估算本身拖成几分钟的读盘。判断偏保守一侧——尺寸相同但内容
            不对的文件会被少算一次分片，宿主给的固定余量覆盖这种误差。在飞峰值按
            单个文件的新大小加它自己的分片取最大，对应「temp 与旧文件短暂共存、
            切片用完才删」的实际占用。
        """
        need = PatchSpaceNeed()
        for asset in plan.patch_assets:
            target = _resolve_target_path(self.game_path, asset.target_file_path)
            current = os.path.getsize(target) if os.path.isfile(target) else -1
            if current == asset.target_file_size:
                need.already_done += 1
                continue
            need.download_left += asset.patch_chunk_length
            need.write_growth += max(0, asset.target_file_size - max(current, 0))
            need.peak = max(
                need.peak, asset.target_file_size + asset.patch_chunk_length
            )
        return need

    @staticmethod
    def _is_excluded(matching_field: str, patterns: Sequence[str]) -> bool:
        """判断 matching_field 是否命中任一 fnmatch 排除模式。

        Args:
            matching_field: 待判定的匹配字段（如 ``game`` / ``en-us``）。
            patterns: fnmatch 通配模式序列（如 ``zh-*``）。

        Returns:
            命中任一模式时为 True。
        """
        import fnmatch

        return any(fnmatch.fnmatch(matching_field, pattern) for pattern in patterns)

    # ================================================================== 钩子

    def filter_assets(self, assets: List[SophonAsset]) -> List[SophonAsset]:
        """钩子：过滤主/语音清单资产。

        Args:
            assets: 待过滤的资产列表。

        Returns:
            过滤后的资产（基类原样返回）。

        Note:
            子类可覆写以剔除特定资源——绝区零据此排除 ``KDelResource`` 相关字段。
        """
        return assets

    def filter_patch_assets(
        self, assets: List[SophonPatchAsset]
    ) -> List[SophonPatchAsset]:
        """钩子：过滤差分资产（差分版的 :meth:`filter_assets`）。

        Args:
            assets: 待过滤的差分资产列表。

        Returns:
            过滤后的差分资产（基类原样返回）。
        """
        return assets

    def before_install(self, plan: UpdatePlan) -> None:
        """安装前扩展点（钩子，子类可覆写）。

        Args:
            plan: 当前执行计划。

        Note:
            基类默认什么都不做。子类用途各异：原神做 3.6 语音目录迁移的前置检查，
            崩铁在要走自研 DeltaPatch 时把 ``pkg_version`` 挪走；执行
            ``execute`` 时于落盘前调用。
        """
        return None

    def write_audio_lang_list(self, languages: Sequence[str]) -> None:
        """写回 ``audio_lang_*`` 清单（钩子，三游戏各不相同，子类覆写）。

        Args:
            languages: 要写入的语音 locale code 列表。

        Note:
            基类按行写文本；``dry_run`` 或拿不到路径时直接跳过（不写盘）。
            原神把 locale code 映射成语言全名写 ``audio_lang_14``；绝区零额外双写
            备用短码清单。子类覆写时应保留此跳过语义。
        """
        path = self.version.audio_lang_list_path_static()
        if not path or self.dry_run:
            return
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            for language in languages:
                handle.write(f"{language}\n")

    # ================================================================== 执行

    def execute(self, plan: Optional[UpdatePlan] = None) -> InstallResult:
        """按计划真正执行下载、落盘与写回版本。

        Args:
            plan: 待执行计划；为 ``None`` 时内部先 :meth:`build_plan`。

        Returns:
            含成功/失败信息；``plan`` 为 Noop 时直接返回成功、
            消息「无需更新」。

        Raises:
            RuntimeError: 计划不是 ``SophonPatch``——MAS 的无人值守更新只实现
                差分一条路径，宿主门禁应在调用前拦下其余 kind。

        Note:
            只实现差分执行；全新安装（``SophonInstall``）、全量比较
            （``SophonUpdate``）与预下载（``SophonPreload``）由宿主门禁停手，
            交给官方启动器。
        """
        plan = plan or self.build_plan()
        result = InstallResult(kind=plan.kind, version=plan.target_version)

        if not plan.needs_action:
            result.success = True
            result.message = "无需更新"
            return result

        if not self.game_path:
            result.message = "未设置游戏目录"
            return result

        if plan.kind != UpdateKind.SophonPatch:
            raise RuntimeError(
                f"MAS 无人值守更新只支持差分（{plan.kind.value} 不支持执行），"
                "请改用官方启动器"
            )

        os.makedirs(self.game_path, exist_ok=True)
        self.before_install(plan)
        self._reset_progress(plan)
        return self._execute_sophon_patch(plan, result)

    def _reset_progress(self, plan: UpdatePlan) -> None:
        """重置进度条的总量/活动名（无进度回调时为空操作）。

        Args:
            plan: 计划对象，提供总字节数与文件数。

        Note:
            差分链路的字节分母用「本轮还要下的量」而不是计划全量：续传时大部分
            文件本地已经更新好，按全量算分母会一直显示零头、跑完也到不了 100%。
        """
        if self.progress is None:
            return
        pending = plan.space_need.download_left if plan.space_need else 0
        self.progress.set_activity(f"更新 {self.preset.profile_name}")
        self.progress.set_total(pending or plan.total_size, plan.file_count)

    def _new_downloader(self) -> SophonDownloader:
        """新建一个 Sophon 下载器实例（按当前会话参数装配）。

        Returns:
            每次调用都新建，不缓存复用。
        """
        return SophonDownloader(
            client=self.client,
            chunk_threads=self.chunk_thread_count,
            progress=self.progress,
            logger=self.logger,
            dry_run=self.dry_run,
            should_abort=self.should_abort,
        )

    # ------------------------------------------------------------ Sophon

    def _execute_sophon_patch(
        self, plan: UpdatePlan, result: InstallResult
    ) -> InstallResult:
        """执行 Sophon 差分补丁（走 :class:`SophonPatcher`）。

        Args:
            plan: 计划对象（含 ``patch_assets`` / ``removed_files``）。
            result: 复用并填充的执行结果。

        Returns:
            含各补丁方式的 ``method_counts``、已完成数（未落盘文件数
            记为失败）；成功后落盘写版本。

        Note:
            失败定义为「仍有文件未落盘」（含 HDiff 不可用、降级后仍失败与
            单文件异常的项）；字节数只计入被标记 ``needs_download``
            的资产，且按 ``patch_chunk_length``（真正要从网络取的字节）累加。
        """
        patcher = SophonPatcher(
            client=self.client,
            game_path=self.game_path,
            downloader=self._new_downloader(),
            progress=self.progress,
            logger=self.logger,
            dry_run=self.dry_run,
            should_abort=self.should_abort,
            hdiff=ExternalHDiffPatcher(self.hdiff_executable or "hpatchz"),
        )
        result.file_total = len(plan.patch_assets)
        counts = patcher.apply(plan.patch_assets, plan.removed_files)
        result.method_counts = counts
        result.file_done = sum(counts.values())
        result.file_failed = len(patcher.failed)
        result.bytes_downloaded = sum(
            asset.patch_chunk_length
            for asset in plan.patch_assets
            if asset.needs_download
        )
        result.success = result.file_failed == 0
        result.message = (
            "" if result.success else f"{result.file_failed} 个文件未能落盘"
        )

        if result.success:
            self.finalize(plan)
        return result

    # ================================================================== 收尾

    def finalize(self, plan: UpdatePlan) -> None:
        """把「已更新」落盘。

        Args:
            plan: 当前执行计划（提供目标版本与语音清单口径）。

        Note:
            这是**唯一**把更新结果写盘的地方：写 ``config.ini`` 的
            ``game_version`` / channel / sub_channel / cps，并按需写回语音清单，
            最后 ``version.reload()``。``dry_run`` 时直接跳过（不落盘）。
        """
        if self.dry_run:
            return

        self.version.update_game_version_to_latest(save=True)
        if self.sophon_voice_languages:
            self.write_audio_lang_list(self.sophon_voice_languages)
        self.version.reload()

    # ================================================================== 清理

    def cleanup_temp(self, *, keep_patch_cache: bool = False) -> List[str]:
        """处理 Sophon / zip 链路产生的临时产物，返回保留下来的目录。

        Args:
            keep_patch_cache: 为真时**保留**下载缓存（差分切片与差分档案目录），
                供下一次从断点接着用；失败与中止路径要传真，成功收尾传假。

        Returns:
            本次保留下来的缓存目录绝对路径（已全部清掉时为空列表）。

        Note:
            散落在游戏各目录下的 ``*.temp`` 半成品只在写单个文件时短暂存在，
            正常与异常路径都会就地删除；这里不做全目录递归清扫——为一路上万个
            文件做一次遍历只为找几个残留，代价不值。进程被强杀留下的个别
            ``.temp`` 可以手工删，不影响游戏。
        """
        if not self.game_path or self.dry_run:
            return []
        kept: List[str] = []
        for name in ("chunk_auto_mas", "ldiff"):
            path = os.path.join(self.game_path, name)
            if not os.path.isdir(path):
                continue
            if keep_patch_cache:
                kept.append(path)
                continue
            shutil.rmtree(path, ignore_errors=True)
        return kept
