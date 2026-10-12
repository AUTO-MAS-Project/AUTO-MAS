#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
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

"""终末地更新共用的数据结构、协议常量与日志出口。"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.utils import get_logger

logger = get_logger("终末地客户端更新")
ProgressFn = Callable[[str], Awaitable[None]]
_TEMP_SUFFIX = ".mas-part"
_CONFIG_MEMBER = "config.ini"
_VERIFY_MANIFEST_MEMBER = "verify_files.json"
_MANIFEST_MAX_BYTES = 8 * 1024**2
"""差量清单与包内清单正文的体积上限。清单是每个变化文件一行的 JSON，远到不了这个量级；
真到了说明服务端或 CDN 给了异常正文，整块读进内存先撑爆的是 MAS 自己。"""
_APPLY_STEP = 20
"""核对基线与落地覆盖这两段逐条播报的间隔（条）：清单能到上万条，逐条播会把最开始的
几步挤出调度台的日志窗口，太疏又看不出还在推进。"""
_DOWNLOAD_CHUNK = 1024**2
_CONNECT_TIMEOUT = 30.0
_READ_TIMEOUT = 60.0


class EndfieldUpdateError(RuntimeError):
    """确认要更新却做不到，或服务端与包内结构不认识。

    「无法判断」不走这里，一律 `Skipped` 放行 —— 不该让一次探测失败毁掉用户排好的
    任务。
    """


@dataclass(frozen=True)
class InstallIdentity:
    """客户端自己在安装目录 `config.ini` 里登记的版本与服务器标识。

    三元组只用来从 `ENDFIELD_SERVER_PRESETS` 里选出一套参数，不直接进请求体。
    """

    version: str
    """版本号原文；空串表示读不出来，此时 MAS 不动手。"""
    appcode: str = ""
    channel: str = ""
    sub_channel: str = ""


@dataclass(frozen=True)
class PackagePart:
    """差量包的一个分卷。"""

    url: str
    md5: str
    size: int
    ordinal: int
    """`.zip.NNN` 的 NNN，用于在换新清单后对齐同一卷。"""


@dataclass(frozen=True)
class Release:
    """服务端给出的一次差量更新计划。"""

    version: str
    """目标版本原文，绝不经任何版本号格式化。"""
    parts: tuple[PackagePart, ...]
    """差量分卷；服务端没给这条基线的差量时为空。"""
    cd_key: str = ""
    """差量包口令（WinZip AES-256）；服务端随每一轮清单一起给出。"""
    patch_info_url: str = ""
    """差量清单 `patch.json` 的地址。开始下载之前就要拿到它。"""
    patch_info_md5: str = ""
    fetched_at: float = field(default_factory=time.monotonic)
    """取到这份清单的时刻；分卷地址带签名，超过 _MANIFEST_MAX_AGE 就换新清单。"""

    @property
    def download_size(self) -> int:
        return sum(part.size for part in self.parts)


@dataclass(frozen=True)
class PatchJob:
    """一条要在本地基线上打差量的活。"""

    path: str
    """新文件在安装目录里的相对路径。"""
    md5: str
    size: int
    base_path: str
    """基线文件的安装目录相对路径；本地必须是它，否则整轮停住。"""
    base_md5: str
    base_size: int
    member: str
    """差量成员在包内的路径。"""


@dataclass(frozen=True)
class MoveJob:
    """整文件清单条目，读取本地包后确定成员名。"""

    path: str
    md5: str
    size: int
    member: str = ""
    """预取时为空；落地前必须匹配并核对包内成员。"""


@dataclass(frozen=True)
class DeltaPlan:
    """读完差量清单与包内成员表后算出的一次落地计划。"""

    patches: tuple[PatchJob, ...]
    moves: tuple[MoveJob, ...]
    deletes: tuple[str, ...]
    """服务端删除表里要清掉的路径（安装目录相对路径），不含孤儿清理。"""

    @property
    def expanded_bytes(self) -> int:
        return sum(job.size for job in self.patches) + sum(
            job.size for job in self.moves
        )


UNKNOWN_SERVER_MESSAGE = (
    "这台终末地客户端登记的服务器 MAS 还认不出，也不会代为猜测，跳过检查"
)
"""面向用户的说法；`appcode`/`channel` 这类标识只进日志，反馈时按日志行核对。"""
