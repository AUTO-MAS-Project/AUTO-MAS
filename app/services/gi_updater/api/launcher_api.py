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

"""
启动器 API 聚合：一次并发拉齐更新要用的全部元数据。

 并发拉 5 类接口：
    1. Sophon 分支（getGameBranches）      <- 必须最先，因为版本以它为准
    2. 资源包（getGamePackages） + 插件 + SDK
    3. 新闻（与更新无关，Python 侧省略）
    4. 游戏信息
    5. WPF 包（与更新无关，Python 侧省略）

用线程池并发拉取，并在拿到结果后补一次伪造：当 zip 资源不可用、或版本
低于 Sophon 分支时，用 Sophon 的 tag 伪造 ``major`` 与 ``patches``。
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.services.gi_updater.api.client import HttpClient
from app.services.gi_updater.api.models import (
    HypLauncherSophonBranchesKind,
    HypResourcesData,
    parse_game_branches,
    parse_game_packages,
)
from app.services.gi_updater.api.profiles import PresetConfig
from app.services.gi_updater.common.logging import get_logger

__all__ = ["LauncherApi", "LauncherApiError"]


class LauncherApiError(RuntimeError):
    pass


@dataclass
class LauncherApi:
    """一次「拉取远程元数据」的结果快照。

     暴露的那几个属性：`LauncherGameResourcePackage`、
    `LauncherGameSophonBranches`、`LauncherGameResourcePlugin`、`LauncherGameResourceSdk`。
    """

    preset: PresetConfig
    client: HttpClient

    #: game_packages[] 里匹配到本游戏的条目
    resource_package: Optional[HypResourcesData] = None
    #: game_branches[] 里匹配到本游戏的条目
    sophon_branches: Optional[HypLauncherSophonBranchesKind] = None
    plugin_packages: List[Any] = field(default_factory=list)
    sdk_packages: List[Any] = field(default_factory=list)

    #:：zip 缺失时必须走 Sophon
    is_force_redirect_to_sophon: bool = False
    logger: Any = None

    def __post_init__(self) -> None:
        """惰性初始化 logger（未传入时取默认）。"""
        if self.logger is None:
            self.logger = get_logger()

    # ------------------------------------------------------------------ 加载

    @classmethod
    def load(
        cls,
        preset: PresetConfig,
        client: Optional[HttpClient] = None,
        *,
        fetch_plugin: bool = False,
        fetch_sdk: bool = False,
        logger: Any = None,
    ) -> "LauncherApi":
        """并发拉取所需接口并做归一化。

        用线程池并发请求 ``getGamePackages``/``getGameBranches``（及可选的插件、SDK），
        任一失败仅记日志不中断；最后执行 Sophon 版本伪造。

        Args:
            preset: 目标游戏区服预设。
            client: 复用的 ``HttpClient``；``None`` 时新建一个（非离线）。
            fetch_plugin: 是否拉取插件资源。
            fetch_sdk: 是否拉取渠道 SDK。
            logger: 覆盖默认 logger。

        Returns:
            填充好 ``resource_package``/``sophon_branches`` 的 ``LauncherApi`` 快照。

        Raises:
            LauncherApiError: 当 ``packages`` 与 ``branches`` **两者都**拉取失败时。
        """
        client = client or HttpClient()
        api = cls(preset=preset, client=client, logger=logger or get_logger())

        tasks: Dict[str, str] = {
            "packages": preset.game_packages_url,
            "branches": preset.game_branches_url,
        }
        if fetch_plugin and preset.launcher_plugin_url:
            tasks["plugin"] = preset.launcher_plugin_url
        if fetch_sdk and preset.launcher_game_channel_sdk_url:
            tasks["sdk"] = preset.launcher_game_channel_sdk_url

        results: Dict[str, Any] = {}
        failures: Dict[str, str] = {}
        # I/O 密集，用线程池并发拉取
        with ThreadPoolExecutor(max_workers=max(1, len(tasks))) as pool:
            futures = {
                pool.submit(client.get_json, url): name for name, url in tasks.items()
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    results[name] = future.result()
                except Exception as error:  # noqa: BLE001
                    failures[name] = str(error)
                    api.logger.warning("拉取 %s 失败：%s", name, error)

        if "packages" not in results and "branches" not in results:
            raise LauncherApiError(
                "资源包与 Sophon 分支接口均拉取失败：" + "; ".join(failures.values())
            )

        if "packages" in results:
            api.resource_package = api._find_resource(results["packages"])
        if "branches" in results:
            api.sophon_branches = api._find_branch(results["branches"])

        api._initialize_fake_version_info()
        return api

    @classmethod
    def from_fixtures(
        cls,
        preset: PresetConfig,
        packages_payload: Optional[Dict[str, Any]] = None,
        branches_payload: Optional[Dict[str, Any]] = None,
        *,
        logger: Any = None,
    ) -> "LauncherApi":
        """离线构造（测试用）：直接吃本地 JSON，不联网。

        Args:
            preset: 目标游戏区服预设（内部用 ``HttpClient(offline=True)`` 保证不联网）。
            packages_payload: 本地 ``getGamePackages`` 响应；``None`` 则 ``resource_package`` 留空。
            branches_payload: 本地 ``getGameBranches`` 响应；``None`` 则 ``sophon_branches`` 留空。
            logger: 覆盖默认 logger。

        Returns:
            离线填充好的 ``LauncherApi`` 快照。
        """
        api = cls(
            preset=preset,
            client=HttpClient(offline=True),
            logger=logger or get_logger(),
        )
        if packages_payload is not None:
            api.resource_package = api._find_resource(packages_payload)
        if branches_payload is not None:
            api.sophon_branches = api._find_branch(branches_payload)
        api._initialize_fake_version_info()
        return api

    # ------------------------------------------------------------------ 查找

    def _find_resource(self, payload: Dict[str, Any]) -> Optional[HypResourcesData]:
        """在 ``game_packages[]`` 里按 biz / game_id 定位本游戏。

        Args:
            payload: 原始 ``getGamePackages`` 响应。

        Returns:
            匹配到的 ``HypResourcesData``；未命中返回 ``None``。
        """
        for item in parse_game_packages(payload):
            if self._match(item.game_info.game_biz, item.game_info.game_id):
                return item
        return None

    def _find_branch(
        self, payload: Dict[str, Any]
    ) -> Optional[HypLauncherSophonBranchesKind]:
        """在 ``game_branches[]`` 里按 biz / game_id 定位本游戏。

        Args:
            payload: 原始 ``getGameBranches`` 响应。

        Returns:
            匹配到的 ``HypLauncherSophonBranchesKind``；未命中返回 ``None``。
        """
        for item in parse_game_branches(payload):
            if self._match(item.game_info.game_biz, item.game_info.game_id):
                return item
        return None

    def _match(self, biz: str, game_id: str) -> bool:
        """判断某条目的 biz / game_id 是否命中本预设。

        Args:
            biz: 待比对业务名（对应 ``launcher_biz_name``）。
            game_id: 待比对游戏 ID（对应 ``game_id``）。

        Returns:
            ``True`` 当 biz 或 game_id 任一相等（且双方均非空）。
        """
        want_biz = self.preset.launcher_biz_name
        want_id = self.preset.game_id
        if want_biz and biz and biz == want_biz:
            return True
        if want_id and game_id and game_id == want_id:
            return True
        return False

    # --------------------------------------------------- InitializeFakeVersionInfo

    def _initialize_fake_version_info(self) -> None:
        """的等价实现（有副作用）。

        直接改写 ``self.resource_package`` 并在需要时置 ``is_force_redirect_to_sophon``。

        触发逻辑：
          * 无 Sophon 分支（``self.sophon_branches`` 为 ``None``）时直接返回，不改动。
          * 完全没有 zip 资源（``resource`` 为 ``None``，如原神 5.6+）时，置强制 Sophon 并返回。
          * Sophon 的 ``tag`` 与 zip 的 ``major.version`` **不相等**时，用 Sophon tag 伪造
            ``main``/``pre_download`` 的 ``current_version`` 并把 ``diff_tags`` 补成 ``patches``，
            同时置 ``is_force_redirect_to_sophon = True``。

        Note:
            本方法会就地修改 ``self.resource_package``，调用方不应假设其不可变。
        """
        resource = self.resource_package
        branch = self.sophon_branches
        if branch is None:
            return

        main_branch = branch.main
        preload_branch = branch.pre_download

        if resource is None:
            # 完全没有 zip 资源（原神 5.6 之后就是这样）-> 全靠 Sophon
            self.is_force_redirect_to_sophon = True
            self.logger.debug("无 zip 资源包，强制走 Sophon")
            return

        from app.services.gi_updater.common.version import GameVersion

        zip_version = (
            GameVersion.parse(resource.main_package.current_version.version)
            if resource.main_package and resource.main_package.current_version
            else None
        )
        sophon_version = GameVersion.parse(main_branch.tag) if main_branch else None

        if (
            sophon_version is not None
            and zip_version is not None
            and sophon_version == zip_version
        ):
            return

        # 伪造 pre_download
        if preload_branch is not None and resource.pre_download is None:
            resource.pre_download = _make_resource_package(
                preload_branch.tag, preload_branch.diff_tags
            )
        elif preload_branch is not None and resource.pre_download is not None:
            _add_fake_version(
                resource.pre_download, preload_branch.tag, preload_branch.diff_tags
            )

        if main_branch is None:
            return

        if resource.main_package is None:
            resource.main_package = _make_resource_package(
                main_branch.tag, main_branch.diff_tags
            )
        else:
            _add_fake_version(
                resource.main_package, main_branch.tag, main_branch.diff_tags
            )
        self.is_force_redirect_to_sophon = True

    # ------------------------------------------------------------------ 便捷

    @property
    def has_sophon(self) -> bool:
        """是否存在可用的 Sophon 主分支（``sophon_branches.main`` 非空）。"""
        return (
            self.sophon_branches is not None and self.sophon_branches.main is not None
        )

    def get_package_versions(self) -> List[str]:
        """zip 资源里可用的版本列表（major + patches）。

        Returns:
            版本串列表（``current_version.version`` + 各 ``patch.version``）；
            无 zip 资源时返回空列表。
        """
        if not self.resource_package or not self.resource_package.main_package:
            return []
        main = self.resource_package.main_package
        versions: List[str] = []
        if main.current_version:
            versions.append(main.current_version.version)
        versions.extend(patch.version for patch in main.patches)
        return versions


def _make_resource_package(tag: str, diff_tags: Optional[List[str]]):
    """构造一个「伪造」的 ``HypResourcePackageData``（仅含 Sophon 提供的版本信息）。

    Args:
        tag: Sophon 分支的版本 tag，用作 ``current_version``。
        diff_tags: 差分 tag 列表，逐一补成 ``patches``。

    Returns:
        ``HypResourcePackageData``：``current_version`` 取 ``tag``，``patches`` 由 ``diff_tags`` 补成。
    """
    from app.services.gi_updater.api.models import HypResourcePackageData

    package = HypResourcePackageData()
    _add_fake_version(package, tag, diff_tags)
    return package


def _add_fake_version(package, tag: str, diff_tags: Optional[List[str]]) -> None:
    """的等价实现（就地修改 ``package``）。

    Args:
        package: 目标 ``HypResourcePackageData``（被就地修改，无返回值）。
        tag: Sophon 版本 tag，缺失 ``current_version`` 时用来填充。
        diff_tags: 差分 tag 列表，去重后追加为 ``patches``。

    Note:
        本函数就地修改 ``package``（填充 ``current_version``、追加 ``patches``），不返回新对象。
    """
    from app.services.gi_updater.api.models import HypPackageInfo

    if package.current_version is None or not package.current_version.version:
        package.current_version = HypPackageInfo(version=tag or "")

    existing = {patch.version for patch in package.patches}
    for diff_tag in diff_tags or []:
        if diff_tag not in existing:
            package.patches.append(HypPackageInfo(version=diff_tag))


def load_fixture(name: str) -> Dict[str, Any]:
    """从 ``tests/fixtures`` 读一个 JSON 样例（离线自测用）。

    Args:
        name: 文件名（含扩展名），相对 ``tests/fixtures`` 目录。

    Returns:
        解析后的 JSON 对象。

    Raises:
        FileNotFoundError: 文件不存在时。
        json.JSONDecodeError: 文件内容不是合法 JSON 时。
    """
    path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "tests", "fixtures", name
    )
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)
