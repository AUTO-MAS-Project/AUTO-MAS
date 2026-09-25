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

"""下载层：protobuf/zstd 解码、Sophon 清单与差分补丁。"""

from app.services.gi_updater.download.protobuf import (
    ProtoMessage,
    SophonAssetChunk,
    SophonAssetProperty,
    SophonManifestProto,
    SophonPatchAssetInfo,
    SophonPatchAssetProperty,
    SophonPatchChunk,
    SophonPatchProto,
    parse_sophon_manifest,
    parse_sophon_patch,
    read_message,
)
from app.services.gi_updater.download.sophon import (
    SophonAsset,
    SophonChunk,
    SophonChunkManifestInfoPair,
    SophonChunksInfo,
    SophonDownloader,
    SophonError,
    SophonManifest,
    SophonManifestInfo,
)
from app.services.gi_updater.download.sophon_patch import (
    BLANK_FILE_MD5,
    ExternalHDiffPatcher,
    HDiffPatcher,
    HDiffUnavailableError,
    SophonPatchAsset,
    SophonPatcher,
    SophonPatchMethod,
    build_patch_assets,
)
from app.services.gi_updater.download.zstd import (
    ZstdBackend,
    ZstdError,
    backend_name,
    decompress,
    is_available,
    iter_decompress,
)

__all__ = [
    "ProtoMessage",
    "SophonAssetChunk",
    "SophonAssetProperty",
    "SophonManifestProto",
    "SophonPatchAssetInfo",
    "SophonPatchAssetProperty",
    "SophonPatchChunk",
    "SophonPatchProto",
    "parse_sophon_manifest",
    "parse_sophon_patch",
    "read_message",
    "ZstdError",
    "ZstdBackend",
    "backend_name",
    "decompress",
    "is_available",
    "iter_decompress",
    "SophonAsset",
    "SophonChunk",
    "SophonChunkManifestInfoPair",
    "SophonChunksInfo",
    "SophonDownloader",
    "SophonError",
    "SophonManifest",
    "SophonManifestInfo",
    "BLANK_FILE_MD5",
    "ExternalHDiffPatcher",
    "HDiffPatcher",
    "HDiffUnavailableError",
    "SophonPatchAsset",
    "SophonPatchMethod",
    "SophonPatcher",
    "build_patch_assets",
]
