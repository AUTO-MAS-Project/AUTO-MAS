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

"""API 层：预设、数据模型、HTTP 客户端、聚合加载。

原神走米哈游 HYP Connect 一条轨道，聚合类是 :class:`LauncherApi`。
"""

from app.services.gi_updater.api.client import (
    HttpClient,
    HttpError,
    HttpResponse,
    load_or_create_device_id,
)
from app.services.gi_updater.api.launcher_api import LauncherApi, LauncherApiError
from app.services.gi_updater.api.models import (
    GamePackageResult,
    HypGameInfoBranchData,
    HypPackageData,
    HypPackageInfo,
    HypResourcesData,
    SophonManifestBuildBranch,
    SophonManifestBuildIdentity,
    SophonManifestPatchBranch,
    parse_build,
    parse_game_branches,
    parse_game_packages,
    parse_patch_build,
)
from app.services.gi_updater.api.profiles import (
    PROFILES,
    GameNameType,
    PresetConfig,
    Region,
    SophonChunkUrls,
    get_profile,
)

__all__ = [
    "HttpClient",
    "HttpResponse",
    "HttpError",
    "load_or_create_device_id",
    "PresetConfig",
    "SophonChunkUrls",
    "GameNameType",
    "Region",
    "PROFILES",
    "get_profile",
    "GamePackageResult",
    "HypPackageData",
    "HypPackageInfo",
    "HypResourcesData",
    "HypGameInfoBranchData",
    "SophonManifestBuildBranch",
    "SophonManifestBuildIdentity",
    "SophonManifestPatchBranch",
    "parse_build",
    "parse_game_branches",
    "parse_game_packages",
    "parse_patch_build",
    "LauncherApi",
    "LauncherApiError",
]
