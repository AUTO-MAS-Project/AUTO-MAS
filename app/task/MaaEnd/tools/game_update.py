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

"""终末地 PC 客户端增量更新。

只服务 `Game.ControllerType` 协议为 Win32 的终末地脚本，其他专项与 MaaFW 的 PC 线都不
复用本模块。更新对象是游戏本体（`Game.Path` 所在目录）。

流程：从客户端自己的 `config.ini` 读出版本号与服务器三元组 → 用这份原文向 `batch_proxy`
接口换回差量包与差量清单 → 先按清单核对本地基线文件，核对不过就一个字都不写 → 逐卷下载
差量分卷并按 MD5 校验 → 把分卷拼成连续流交给 `pyzipper`（差量包是 WinZip AES-256，口令
来自服务端给的 `cd_key`）→ 逐条用 `hpatchz` 把差量打在基线文件上（整文件成员直接取包内
字节）→ 每条落盘前比 MD5，全部就位后才提交 `config.ini`，最后按服务端的删除表清理。

只做差量，**不做整包**：整包与差量同时挂在服务端时也只走差量那一支。判不出本地版本、
服务端没给这条基线的差量、或本地基线文件与清单不符，一律走 `NeedManualUpdate` 停下并提示
手动更新——停下来不比刷错客户端更糟。

四条不可动摇的约束：

- **版本号原文上报**：本地版本必须原样发给服务端。服务端按它做精确匹配，补段（在末尾多
  写一个 `.0`）或加后缀都不会报错，只会当成没有差量；终末地发布出去的第三段本来就是跳号
  的，造出来的版本号问不到东西。
- **服务器参数整套取自同一套登记值**：先用 `config.ini` 登记的 `appcode`/`channel`/
  `sub_channel` 匹配 `app.utils.constants.ENDFIELD_SERVER_PRESETS` 里的一套，请求体的每
  一项（含 `seq` 与 `launcher_appcode`）都取自这一套；四套之间这些值并不相同，混用参数
  会让国际服客户端拿到错的清单。匹配不到就不碰客户端。
- **绝不自写 `config.ini`**：它是游戏自有的加密配置，MAS 只读；新版本号只用包内自带
  的那份覆盖进来。
- **`config.ini` 最后提交**：顺序不能动，判据与后果见 `_apply_delta`；差量落地不做
  回滚（旧版留底等于再放一整份客户端）。
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import threading
import time
import zipfile
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import aiofiles
import httpx
import psutil
import pyzipper
from Crypto.Cipher import AES

from app.services import System
from app.utils import get_logger
from app.utils.constants import ENDFIELD_SERVER_PRESETS
from app.utils.game_apk import GameUpdateResult, is_client_outdated
from app.utils.hpatchz import ensure_hpatchz
from app.utils.io import force_rmtree

from . import package_index

logger = get_logger("终末地客户端更新")

ProgressFn = Callable[[str], Awaitable[None]]

_STAGING_DIR_NAME = "_mas_endfield_update"
"""差量分卷暂存目录，放在安装目录内：几 GB 的差量往常年在 C 盘的 MAS 数据目录里塞会
撞上系统盘余量，且同卷才能让落盘的最后一步是原子改名。"""

_PENDING_CONFIG_NAME = "config.ini.pending"
_TEMP_SUFFIX = ".mas-part"

_CONFIG_MEMBER = "config.ini"
_DELETE_LIST_MEMBER = "delete_files.txt"
_VERIFY_MANIFEST_MEMBER = "verify_files.json"
_DIFF_MEMBER_PREFIX = "vfs_files/vfs_patch/"
_WHOLE_MEMBER_PREFIX = "vfs_files/files/"
"""差量包内的成员摆法：差量成员是 `vfs_files/vfs_patch/` 加上清单里给出的名字；
VFS 整文件挂在 `vfs_files/files/<安装目录相对路径>`；非 VFS 的整文件直接用安装目录
相对路径躺在根上。"""

_MAX_PARTS = 512
_MAX_ENTRIES = 20_000
"""分卷数与清单条目数上限：超出就当包不认识，绝不动手。"""

_MANIFEST_MAX_BYTES = 8 * 1024**2
"""差量清单与包内清单正文的体积上限。清单是每个变化文件一行的 JSON，远到不了这个量级；
真到了说明服务端或 CDN 给了异常正文，整块读进内存先撑爆的是 MAS 自己。"""

_APPLY_STEP = 20
"""逐条落地时的播报间隔（条）：太密会刷满调度台日志，太疏看不出还在推进。"""

_RESERVE_BYTES = 256 * 1024**2
"""除下载与落地体积外额外要求的余量：盘刚好占满会把问题转移到下一次运行。"""

_PROGRESS_STEP = 512 * 1024**2
_PROGRESS_INTERVAL = 10.0
"""进度按「每 `_PROGRESS_STEP` 或每 `_PROGRESS_INTERVAL`」两者先到者播报一次：一轮下载
只出十几行，也给调度台日志留足余量，不让它撞上前端的截断线。"""

_DOWNLOAD_CHUNK = 1024**2
_MD5_CHUNK = 16 * 1024**2
_CONNECT_TIMEOUT = 30.0
_READ_TIMEOUT = 60.0
_PART_ATTEMPTS = 3
"""单卷尝试次数：CDN 抖动与签名地址失效都在这里消化。"""

_MANIFEST_MAX_AGE = 60.0
"""清单最长复用时长（秒）。分卷地址带 `auth_key` 签名，按地址里的时间戳观测有效窗口约
2 分钟；这里取一半留余量，跨分钟的下载一定在新地址上做，不去赌边界。"""

_KILL_WAIT_SECONDS = 30.0

_UNPACK_DRAIN_SECONDS = 5.0
"""中止后等设备线程自己停下的上限：只等它松手（下一块就停），不等它把成员拷完。"""

_CONFIG_KEY = bytes.fromhex(
    "c0f30e1ce763bbc21cc355a34303ac50399444bff68c4a22af398c0a166ee143"
)
_CONFIG_IV = bytes.fromhex("33467861192750649501937264608400")
"""`config.ini` 的固定解密密钥与 IV。

只读：用它解出 `config.ini` 里的版本号与服务器三元组，绝不写回。差量包自身的口令不在
这里——服务端在 `patch.cd_key` 里随每次清单一起给出。
"""

_VOLUME_SUFFIX_RE = re.compile(r"\.(\d+)$")
_DIGITS_RE = re.compile(r"^\s*(\d+)$")
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*://")
_LONG_PATH_THRESHOLD = 259


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
    request_version: str = ""
    """换回这份清单时上报的本地版本原文。

    服务端按这个值决定给不给差量：报目标版本会被当成「已是最新」而回空差量，所以中途
    刷新清单必须重发它，不能拿 `version` 顶替。
    """
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
    """一条直接从包里搬整文件的活。"""

    path: str
    md5: str
    size: int
    member: str


@dataclass(frozen=True)
class MoveEntry:
    """包内落地核对表 `move` 段的一条：新文件在安装目录里的相对路径与它的 MD5、体积。"""

    path: str
    md5: str
    size: int


@dataclass(frozen=True)
class DeltaPlan:
    """读完差量清单与包内成员表后算出的一次落地计划。"""

    patches: tuple[PatchJob, ...]
    moves: tuple[MoveJob, ...]
    deletes: tuple[str, ...]
    """服务端删除表里要清掉的路径（安装目录相对路径），不含孤儿清理。"""
    config_member: str
    """包内 `config.ini` 的成员名；版本号载体，必须最后一个提交。"""

    @property
    def expanded_bytes(self) -> int:
        return sum(job.size for job in self.patches) + sum(
            job.size for job in self.moves
        )


def _file_name_from_url(url: str) -> str:
    """从下载地址取落盘文件名。名字来自远端，清洗过才准用。"""

    path = url.split("?", 1)[0].split("#", 1)[0]
    name = unquote(path.rsplit("/", 1)[-1]).strip()
    if (
        not name
        or name in {".", ".."}
        or any(sep in name for sep in ("/", "\\", ":", "\x00"))
    ):
        raise EndfieldUpdateError(f"下载地址里的文件名不可用: {path!r}")
    return name


def _parse_int(raw: object) -> int:
    """服务端把体积给成字符串；解析不出来就当作不可信，绝不盲下。"""

    if raw is None:
        return 0
    match = _DIGITS_RE.match(str(raw).strip())
    return int(match.group(1)) if match else 0


def _parse_release(payload: object, request_version: str) -> Release:
    if not isinstance(payload, dict):
        raise EndfieldUpdateError("启动器响应不是 JSON 对象")
    rsps = payload.get("proxy_rsps") or []
    if not isinstance(rsps, list):
        # 服务端口径变了就停下来问：往下 iterate 会抛 TypeError，那是打死任务的错法
        raise EndfieldUpdateError(
            f"启动器响应的 proxy_rsps 不是列表: {type(rsps).__name__}"
        )
    for item in rsps:
        if not isinstance(item, dict) or item.get("kind") not in (
            None,
            "get_latest_game",
        ):
            continue
        body = item.get("get_latest_game_rsp")
        if isinstance(body, dict):
            return _parse_latest_game(body, request_version)
    raise EndfieldUpdateError(
        f"启动器响应里找不到 get_latest_game: {str(payload)[:200]}"
    )


def _parse_latest_game(body: dict, request_version: str) -> Release:
    # 目标版本只取 `version`：`pre_patch` 是预下载那条独立安装路径的版本，跟着它写会把
    # 没发布出去的版本号盖进客户端。
    version = str(body.get("version") or "").strip()
    if not version:
        raise EndfieldUpdateError("启动器响应里没有版本号")

    patch = body.get("patch")
    if not isinstance(patch, dict):
        # 空差量段有两种意思：已是最新，或这条基线没有差量。谁也不许拿整包兜底，
        # 交给上层用版本号原文判。
        return Release(version=version, parts=(), request_version=request_version)

    parts: list[PackagePart] = []
    patches = patch.get("patches") or []
    if not isinstance(patches, list):
        raise EndfieldUpdateError(
            f"差量段的 patches 不是列表: {type(patches).__name__}"
        )
    for index, pack in enumerate(patches):
        if not isinstance(pack, dict) or not pack.get("url"):
            continue
        size = _parse_int(pack.get("package_size"))
        if size <= 0:
            raise EndfieldUpdateError(f"服务端未给出差量卷体积: {pack!r}")
        url = str(pack["url"])
        if not _SCHEME_RE.match(url):
            # 差量卷地址是带 auth_key 签名的绝对地址；给成相对地址说明服务端改了口径，
            # 宁可报错也不拿别的基准去拼一个错地址。
            raise EndfieldUpdateError(f"差量卷地址不是绝对地址: {url!r}")
        match = _VOLUME_SUFFIX_RE.search(url.split("?", 1)[0])
        parts.append(
            PackagePart(
                url=url,
                md5=str(pack.get("md5") or "").strip().lower(),
                size=size,
                ordinal=int(match.group(1)) if match else index + 1,
            )
        )
    if len(parts) > _MAX_PARTS:
        raise EndfieldUpdateError(f"差量卷数 {len(parts)} 超过上限 {_MAX_PARTS}")
    if parts and not str(patch.get("v2_patch_info_url") or "").strip():
        raise EndfieldUpdateError("服务端给了差量卷却没给差量清单地址")
    parts.sort(key=lambda part: part.ordinal)
    return Release(
        version=version,
        parts=tuple(parts),
        cd_key=str(patch.get("cd_key") or "").strip(),
        patch_info_url=str(patch.get("v2_patch_info_url") or "").strip(),
        patch_info_md5=str(patch.get("v2_patch_info_md5") or "").strip().lower(),
        request_version=request_version,
    )


def _match_preset(identity: InstallIdentity) -> dict[str, str] | None:
    """按客户端登记的三元组选出对应的一套服务器参数；选不出就交给调用方中止。

    MAS 没有替用户选服务器的入口，所以只认 `config.ini` 里登记的值。匹配不到时不能拿
    别的一套兜底：那样问回来的清单压根不是这个客户端的。
    """

    return ENDFIELD_SERVER_PRESETS.get(
        (identity.appcode, identity.channel, identity.sub_channel)
    )


UNKNOWN_SERVER_MESSAGE = (
    "这台终末地客户端登记的服务器 MAS 还认不出，也不会代为猜测，跳过检查"
)
"""面向用户的说法；`appcode`/`channel` 这类标识只进日志，反馈时按日志行核对。"""


def _log_unknown_server(identity: InstallIdentity) -> None:
    logger.warning(
        "终末地客户端登记的服务器不在已知四类之内: "
        f"appcode={identity.appcode or '空'} channel={identity.channel or '空'}"
        f" sub_channel={identity.sub_channel or '空'}"
    )


async def _fetch_release(identity: InstallIdentity) -> Release:
    """上报本地版本原文，换回差量计划。

    请求体的每一项都取自 `_match_preset` 选中的那一套参数，`version` 才是本地读到的原文。

    Raises:
        EndfieldUpdateError: 三元组匹配不到已知服务器参数。
    """

    preset = _match_preset(identity)
    if preset is None:
        _log_unknown_server(identity)
        raise EndfieldUpdateError(UNKNOWN_SERVER_MESSAGE)
    body = {
        "seq": preset["seq"],
        "proxy_reqs": [
            {
                "kind": "get_latest_game",
                "get_latest_game_req": {
                    "appcode": preset["appcode"],
                    "launcher_appcode": preset["launcher_appcode"],
                    "channel": preset["channel"],
                    "sub_channel": preset["sub_channel"],
                    "version": identity.version,
                },
            }
        ],
    }
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(_READ_TIMEOUT, connect=_CONNECT_TIMEOUT),
        headers={"Content-Type": "application/json"},
    ) as client:
        response = await client.post(preset["api_url"], json=body)
    response.raise_for_status()
    return _parse_release(response.json(), identity.version)


def _strip_padding(plain: bytes) -> bytes:
    if not plain:
        return plain
    pad = plain[-1]
    if 1 <= pad <= 16 and plain.endswith(bytes([pad]) * pad):
        return plain[:-pad]
    return plain


_IDENTITY_FIELDS = ("version", "appcode", "channel", "sub_channel")
"""询问差量所必需的四个键：版本号原文，外加选服务器用的三元组。"""


def read_install_identity(install_dir: Path) -> InstallIdentity:
    """读取安装目录 `config.ini` 里的版本号与服务器三元组**原文**。

    文件缺失、解不开或键不全时对应字段留空串，调用方据此走 `Skipped`，不做猜测。
    """

    config_path = install_dir / _CONFIG_MEMBER
    try:
        raw = config_path.read_bytes()
    except OSError as error:
        logger.info(f"读取终末地 config.ini 失败，按版本未知处理: {error}")
        return InstallIdentity(version="")

    if len(raw) % 16:
        # 未加密的 config.ini 是真实存在的磁盘状态，不能因为解不开就报错
        logger.warning(f"终末地 config.ini 长度不是分组倍数，按明文处理: {config_path}")
        text = raw.decode("utf-8", "replace")
    else:
        try:
            cipher = AES.new(_CONFIG_KEY, AES.MODE_CBC, _CONFIG_IV)
            text = _strip_padding(cipher.decrypt(raw)).decode("utf-8", "replace")
        except (ValueError, KeyError, UnicodeDecodeError) as error:
            logger.warning(f"终末地 config.ini 解密失败，按版本未知处理: {error}")
            return InstallIdentity(version="")

    found: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        name = key.strip().casefold()
        if name in _IDENTITY_FIELDS and name not in found:
            found[name] = value.strip()
    missing = [name for name in _IDENTITY_FIELDS if not found.get(name)]
    if missing:
        logger.warning(f"终末地 config.ini 缺少询问差量所需的键: {', '.join(missing)}")
    return InstallIdentity(
        version=found.get("version", ""),
        appcode=found.get("appcode", ""),
        channel=found.get("channel", ""),
        sub_channel=found.get("sub_channel", ""),
    )


def read_installed_version(install_dir: Path) -> str:
    """只取版本号原文，用于收尾回读与「已是最新」的比对。"""

    return read_install_identity(install_dir).version


def _native_path(path: Path) -> str:
    """Windows 长路径开关。

    包内路径不深，但安装目录由用户放在任意深层位置，拼起来就可能超过 Win32 的长度
    上限；Python 只在路径带 `\\\\?\\` 前缀时才绕过自身对长度的额外处理。
    """

    text = str(path)
    if os.name != "nt" or len(text) < _LONG_PATH_THRESHOLD:
        return text
    absolute = os.path.abspath(text)
    if absolute.startswith("\\\\"):
        # UNC 必须走 `\\?\UNC\server\share`；直接拼 `\\?\` 会被当成本机相对路径解析
        return "\\\\?\\UNC\\" + absolute.lstrip("\\\\")
    return "\\\\?\\" + absolute


def _size_of(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return -1


def _replace(source: Path, target: Path) -> None:
    if target.exists():
        try:
            # 游戏资源里满是只读文件，带着只读位改名会 PermissionError
            os.chmod(_native_path(target), stat.S_IWRITE)
        except OSError:
            pass
    try:
        os.replace(_native_path(source), _native_path(target))
    except FileNotFoundError:
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(_native_path(source), _native_path(target))


def _resolve_within(root: Path, name: str) -> Path:
    """把包内路径解析到安装目录之内。

    成员名来自下载的包，属于不可信输入：目录穿越会把文件写到安装目录外面去。
    """

    parts = tuple(part for part in re.split(r"[\\/]+", name) if part not in ("", "."))
    if not parts:
        # 空路径会归一成安装目录本身，放过就等于把整棵目录树冲掉
        raise EndfieldUpdateError(f"包内路径为空: {name!r}")
    if any(":" in part for part in parts):
        # 盘符与交替数据流都靠冒号表达，NTFS 也不允许文件名带它
        raise EndfieldUpdateError(f"包内路径含非法冒号: {name!r}")
    target = root.joinpath(*parts)
    anchor = os.path.normcase(os.path.abspath(root))
    absolute = os.path.normcase(os.path.abspath(target))
    if absolute != anchor and not absolute.startswith(anchor + os.sep):
        raise EndfieldUpdateError(f"包内路径越出安装目录: {name!r}")
    # 返回规范化后的绝对路径：`\\\\?\\` 前缀是把字符串直接交给 Win32，内核不做
    # `..` 折叠，留着 `..` 段会让写入莫名失败
    return Path(os.path.normpath(os.path.abspath(target)))


def _processes_under(root: Path) -> list[str]:
    """列出镜像路径落在安装目录里的进程。

    按镜像路径而不是进程名判断：终末地是 UE 客户端，会带一串同名子进程，同时别家
    同名的 `Endfield.exe` 不该被误伤。
    """

    try:
        anchor = root.resolve()
    except OSError:
        return []
    found: list[str] = []
    for process in psutil.process_iter(["pid", "name", "exe"]):
        try:
            executable = process.info.get("exe")
            if not executable:
                continue
            image = Path(executable)
            if anchor != image.parent and anchor not in image.parents:
                continue
            found.append(
                f"{process.info.get('name') or image.name}（PID {process.info.get('pid')}）"
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            continue
    return found


async def _release_install_dir(game_exe: Path) -> str | None:
    """让安装目录脱离进程占用；仍被占用时返回给用户看的说明。"""

    install_dir = game_exe.parent
    busy = await _busy_processes(install_dir)
    if not busy:
        return None
    logger.info(f"终末地客户端正在运行，先请求退出: {', '.join(busy)}")
    await System.kill_process(game_exe)
    deadline = time.monotonic() + _KILL_WAIT_SECONDS
    while time.monotonic() < deadline:
        if not await _busy_processes(install_dir):
            return None
        await asyncio.sleep(2.0)
    busy = await _busy_processes(install_dir)
    # 占用者按镜像路径认，未必只有游戏本身：游戏目录里放着的别的工具同样会挡路
    return f"{', '.join(busy)} 仍在使用游戏目录，请退出上面列出的程序后重试"


async def _busy_processes(root: Path) -> list[str]:
    """在工作线程里问一遍进程占用：Windows 上取每个进程的镜像路径是百毫秒级的活。"""

    return await asyncio.to_thread(_processes_under, root)


def _landing_need(
    patches: Sequence[PatchJob | _PatchSpec],
    moves: Sequence[MoveJob | MoveEntry],
    install_dir: Path,
) -> int:
    """落地期间最多要腾出多少字节：整轮累计净增，再加单条改名时的瞬时量。

    改名之前旧文件不释放，所以最大那一条按新旧两份同时在盘算；其余是一条接一条累上去的
    净增，只增不减——整搬的目标本来不存在时整条体积都是新增。只按单条峰值估会放过一个根本
    装不下的盘，等到客户端被写了一半才失败。

    下载前的预估与下载后的判定共用这一套算法，两道门不会各算各的账。
    """

    net_growth = 0
    widest = 0
    for job in patches:
        net_growth += job.size - job.base_size
        widest = max(widest, job.size + job.base_size)
    for job in moves:
        old = max(_size_of(_resolve_within(install_dir, job.path)), 0)
        net_growth += job.size - old
        widest = max(widest, job.size + old)
    return max(net_growth, 0) + widest


def _disk_shortfall(directory: Path, need: int, label: str) -> str | None:
    """问一次磁盘余量：放行时把那一刻的数留在日志里，拦住时只给调用方那一句。

    放行也要留痕——收尾会把暂存卷整个清掉，日志报的 free 与用户事后去看的 free 天生差
    一卷；记下核对当时的需要量与可用量，事后才对得上账。
    """

    probe = directory
    while not probe.exists() and probe.parent != probe:
        # 目录还没建出来时向上找到挂载点，否则 disk_usage 直接抛错
        probe = probe.parent
    try:
        free = shutil.disk_usage(probe).free
    except OSError as error:
        return f"无法确认{label}所在磁盘的余量：{error}"
    if free >= need:
        logger.info(
            f"{label}所在磁盘余量核对：需要约 {need / 1024**3:.1f} GB，"
            f"当前可用 {free / 1024**3:.1f} GB，足够"
        )
        return None
    return (
        f"{label}所在磁盘余量不足：需要约 {need / 1024**3:.1f} GB，"
        f"当前可用 {free / 1024**3:.1f} GB"
    )


def _write_probe(directory: Path) -> str | None:
    """探针文件试探可写。

    不按路径猜「Program Files」、也不提权：无人值守时 UAC 弹窗会把调度卡死，而正式
    包本身已以管理员运行，探针失败就是真失败。
    """

    probe = directory / f".mas_write_probe.{os.getpid()}"
    try:
        probe.write_bytes(b"")
    except OSError as error:
        return f"游戏目录不可写入（{error}），请给当前用户授予该目录写权限后重试"
    finally:
        try:
            probe.unlink()
        except OSError:
            pass
    return None


class _SplicedStream(io.RawIOBase):
    """把已下载的分卷拼成一条可 seek 的连续流，直接交给 `zipfile` 读。

    整包就是单条 zip 的纯字节切片，所以不需要物理合并 —— 合并会再多占一份包体积。任意
    时刻只保持一个卷句柄；分卷一律留到收尾统一清，磁盘余量预估也按「整包全程留在盘上」
    算。
    """

    def __init__(self, files: Sequence[Path], sizes: Sequence[int]) -> None:
        self._files = list(files)
        self.sizes = list(sizes)
        self._starts: list[int] = []
        cursor = 0
        for size in self.sizes:
            self._starts.append(cursor)
            cursor += size
        self.size = cursor
        self.pos = 0
        self._handle: io.BufferedReader | None = None
        self._handle_index = -1

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        base = {os.SEEK_SET: 0, os.SEEK_CUR: self.pos, os.SEEK_END: self.size}[whence]
        self.pos = max(0, base + offset)
        return self.pos

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = self.size - self.pos
        size = min(size, self.size - self.pos)
        if size <= 0:
            return b""
        data = self._span(self.pos, size)
        self.pos += len(data)
        return data

    def readinto(self, buffer):  # type: ignore[no-untyped-def]
        data = self.read(len(buffer))
        buffer[: len(data)] = data
        return len(data)

    def close(self) -> None:
        self._close_handle()
        super().close()

    def _locate(self, offset: int) -> int:
        for index in range(len(self._starts) - 1, -1, -1):
            if offset >= self._starts[index]:
                return index
        return 0

    def _span(self, offset: int, length: int) -> bytes:
        out = bytearray()
        cursor = offset
        remaining = length
        while remaining > 0:
            index = self._locate(cursor)
            local = cursor - self._starts[index]
            take = min(remaining, self.sizes[index] - local)
            out += self._read_volume(index, local, take)
            cursor += take
            remaining -= take
        return bytes(out)

    def _read_volume(self, index: int, local: int, length: int) -> bytes:
        if self._handle is None or self._handle_index != index:
            self._close_handle()
            self._handle = open(_native_path(self._files[index]), "rb")
            self._handle_index = index
        self._handle.seek(local)
        data = self._handle.read(length)
        if len(data) != length:
            raise EndfieldUpdateError(
                f"分卷 {self._files[index].name} 比服务端声明的短：读到 "
                f"{len(data)}，期望 {length}"
            )
        return data

    def _close_handle(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None
            self._handle_index = -1


def _canonical_relative(name: str) -> str:
    """把清单与包内的相对路径规范化成 `a/b/c`。

    同一个规范化值既用来比对成员名，也用来落盘，所以判废必须在这里做完。
    `_resolve_within` 单独用不够：它丢掉空段与 `.`，于是 `/etc/passwd` 会被解析进安装
    目录之内、`Endfield_Data/../config.ini` 会静默折叠成一个合法路径。
    """

    parts: list[str] = []
    for part in re.split(r"[\\/]+", name):
        if part in ("", "."):
            continue
        if part == ".." or ":" in part or any(ch in part for ch in '<>|"?*\x00'):
            raise EndfieldUpdateError(f"清单路径不可用: {name!r}")
        parts.append(part)
    if not parts:
        raise EndfieldUpdateError(f"清单路径为空: {name!r}")
    return "/".join(parts)


@dataclass(frozen=True)
class _PatchSpec:
    """差量清单里的一条「在哪个基线上打哪个成员」。"""

    path: str
    """新文件在安装目录里的相对路径。"""
    md5: str
    size: int
    base_path: str
    base_md5: str
    base_size: int
    member: str


async def _fetch_patch_manifest(
    client: httpx.AsyncClient, url: str, digest: str
) -> tuple[_PatchSpec, ...]:
    """取差量清单 `patch.json`：明文 JSON，按服务端给的 MD5 钉死。

    Returns:
        要打差量的条目，路径已并上清单给的 VFS 根。整文件不在这里——它们连同落地核对表
        一起由包内 `verify_files.json` 给出。

    Raises:
        EndfieldUpdateError: 清单读不懂、MD5 不符、或给出 MAS 不认的多跳差量。
    """

    response = await client.get(url)
    response.raise_for_status()
    raw = response.content
    if len(raw) > _MANIFEST_MAX_BYTES:
        raise EndfieldUpdateError(
            f"差量清单正文 {len(raw)} 字节超过上限 {_MANIFEST_MAX_BYTES}，判为异常"
        )
    if digest and hashlib.md5(raw).hexdigest() != digest:
        raise EndfieldUpdateError("差量清单的 MD5 与服务端声明不符")
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EndfieldUpdateError(f"差量清单不是可读的 JSON: {error}") from error
    if not isinstance(doc, dict):
        raise EndfieldUpdateError("差量清单顶层不是 JSON 对象")

    vfs = _canonical_relative(str(doc.get("vfs_base_path") or ""))
    entries = doc.get("files")
    if not isinstance(entries, list) or not entries:
        raise EndfieldUpdateError("差量清单里没有 files 段")
    if len(entries) > _MAX_ENTRIES:
        raise EndfieldUpdateError(
            f"差量清单条目 {len(entries)} 超过上限 {_MAX_ENTRIES}"
        )

    specs: list[_PatchSpec] = []
    for item in entries:
        if not isinstance(item, dict):
            raise EndfieldUpdateError(f"差量清单条目不是对象: {item!r}")
        nodes = item.get("patch")
        if not nodes:
            continue
        if not isinstance(nodes, list) or len(nodes) != 1:
            # 多跳意味着还要留下中间版本逐轮打，这里不做——宁可判不接管，
            # 也不猜该按哪一跳落地。
            count = len(nodes) if isinstance(nodes, list) else 0
            raise EndfieldUpdateError(f"清单给出 {count} 跳差量，MAS 只认单跳")
        node = nodes[0]
        if not isinstance(node, dict):
            raise EndfieldUpdateError(f"差量条目不是对象: {node!r}")
        specs.append(
            _PatchSpec(
                path=f"{vfs}/{_canonical_relative(str(item.get('name') or ''))}",
                md5=str(item.get("md5") or "").strip().lower(),
                size=_parse_int(item.get("size")),
                base_path=f"{vfs}/{_canonical_relative(str(node.get('base_file') or ''))}",
                base_md5=str(node.get("base_md5") or "").strip().lower(),
                base_size=_parse_int(node.get("base_size")),
                member=_DIFF_MEMBER_PREFIX
                + _canonical_relative(str(node.get("patch") or "")),
            )
        )
    if not specs:
        raise EndfieldUpdateError("差量清单里没有要打差量的条目")
    return tuple(specs)


async def _check_baselines(
    specs: Sequence[_PatchSpec],
    install_dir: Path,
    progress: ProgressFn | None,
    abort: threading.Event,
) -> list[str]:
    """按清单核对本地基线文件，返回核对不过的那些路径。

    先比体积再算 MD5：体积就不对的文件打不了差量，没必要读内容。这一步跑完之前一个字
    都不写进游戏目录——差量打在错基线上产出的是「长度对得上、内容坏了」的文件，只有
    落盘前那次 MD5 能发现，而那时游戏目录已经被写了一半。
    """

    bad: list[str] = []
    total = len(specs)
    for index, spec in enumerate(specs, start=1):
        if abort.is_set():
            break
        base = _resolve_within(install_dir, spec.base_path)
        if _size_of(base) != spec.base_size:
            bad.append(spec.base_path)
            continue
        try:
            digest = await asyncio.to_thread(_md5_of, base)
        except OSError:
            digest = ""
        if digest != spec.base_md5:
            bad.append(spec.base_path)
        if progress is not None and (index % _APPLY_STEP == 0 or index == total):
            await progress(f"正在核对本地基线文件 {index}/{total}")
    return bad


def _move_entries(doc: dict[str, Any]) -> tuple[MoveEntry, ...]:
    """把包内落地核对表的 `move` 段读成整文件清单。"""

    entries: list[MoveEntry] = []
    for item in doc.get("move") or []:
        if not isinstance(item, dict):
            raise EndfieldUpdateError(f"落地核对表条目不是对象: {item!r}")
        entries.append(
            MoveEntry(
                path=_canonical_relative(str(item.get("path") or "")),
                md5=str(item.get("md5") or "").strip().lower(),
                size=_parse_int(item.get("size")),
            )
        )
    return tuple(entries)


def _read_package_manifests(
    archive: pyzipper.AESZipFile, members: set[str]
) -> tuple[tuple[MoveJob, ...], tuple[str, ...]]:
    """读包内的落地核对表与删除表。

    `verify_files.json` 是明文 JSON，`move` 段给的就是要搬进安装目录的整文件清单，每条
    带安装目录相对路径 + 新文件的 MD5 与体积；VFS 的挂在 `vfs_files/files/` 下，非 VFS
    的按相对路径直接躺在包根上。成员名按这两种摆法在包内找，找不到就判废——宁可不更新，
    也不能少搬一个文件还把版本号写成新版。
    """

    # 整块读进内存之前先卡一次体积，与 CDN 上那份差量清单同一条上限
    for name in (_VERIFY_MANIFEST_MEMBER, _DELETE_LIST_MEMBER):
        info = archive.getinfo(name)
        if info.file_size > _MANIFEST_MAX_BYTES:
            raise EndfieldUpdateError(
                f"包内清单 {name} 体积 {info.file_size} 字节"
                f"超过上限 {_MANIFEST_MAX_BYTES}，判为异常"
            )
    with archive.open(_VERIFY_MANIFEST_MEMBER) as handle:
        doc = json.loads(handle.read().decode("utf-8"))
    if not isinstance(doc, dict):
        raise EndfieldUpdateError("包内落地核对表顶层不是 JSON 对象")
    moves: list[MoveJob] = []
    for entry in _move_entries(doc):
        member = (
            entry.path if entry.path in members else _WHOLE_MEMBER_PREFIX + entry.path
        )
        if member not in members:
            raise EndfieldUpdateError(f"清单要的整文件在包里找不到: {entry.path}")
        moves.append(
            MoveJob(
                path=entry.path,
                md5=entry.md5,
                size=entry.size,
                member=member,
            )
        )
    with archive.open(_DELETE_LIST_MEMBER) as handle:
        text = handle.read().decode("utf-8", "replace")
    deletes = tuple(
        _canonical_relative(line.strip()) for line in text.splitlines() if line.strip()
    )
    return tuple(moves), deletes


def _build_delta_plan(
    specs: Sequence[_PatchSpec],
    members: set[str],
    moves: Sequence[MoveJob],
    deletes: Sequence[str],
) -> DeltaPlan:
    """把两份清单并成一次落地计划；成员对不上就判废。"""

    patches: list[PatchJob] = []
    for spec in specs:
        if spec.member not in members:
            raise EndfieldUpdateError(f"清单要的差量成员在包里找不到: {spec.member}")
        patches.append(
            PatchJob(
                path=spec.path,
                md5=spec.md5,
                size=spec.size,
                base_path=spec.base_path,
                base_md5=spec.base_md5,
                base_size=spec.base_size,
                member=spec.member,
            )
        )
    if _CONFIG_MEMBER not in members:
        # 缺了它 MAS 无法确认更新是否生效，只会每轮静默重下差量，宁可拒绝接管
        raise EndfieldUpdateError(
            "差量包里没有 config.ini，MAS 无法确认更新结果，已停止自动更新，请手动更新一次"
        )
    # 先写后删：与本轮要写的文件同名的删除项跳过，否则刚写好就自我删除；
    # 大小写按文件系统口径忽略。
    written = {os.path.normcase(job.path) for job in (*patches, *moves)}
    kept = [path for path in deletes if os.path.normcase(path) not in written]
    if len(kept) != len(deletes):
        logger.info(
            f"删除表有 {len(deletes) - len(kept)} 项与本轮要写的文件同名，跳过这些删除"
        )
    return DeltaPlan(
        patches=tuple(patches),
        moves=tuple(moves),
        deletes=tuple(kept),
        config_member=_CONFIG_MEMBER,
    )


def _write_member(
    archive: pyzipper.AESZipFile,
    info: zipfile.ZipInfo,
    temp: Path,
    abort: threading.Event,
) -> None:
    """把单个成员读到临时文件。

    成员是 WinZip AES-256 加密的，`pyzipper` 在读满时自己校验包内 HMAC，坏数据到不了
    改名那一步；这里只核对长度。中止标志逐块检查：整文件的成员比差量卷本身还大，只在
    成员之间检查会让中止后的线程继续写很久。调用方负责把它放工作线程里跑。
    """

    written = 0
    try:
        # 包里的目录条目不进成员表，父目录得自己建出来
        temp.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as source, open(_native_path(temp), "wb") as sink:
            while chunk := source.read(4 * _DOWNLOAD_CHUNK):
                if abort.is_set():
                    raise EndfieldUpdateError(
                        f"本轮更新已中止（正在读 {info.filename}），游戏目录处于未完成状态"
                    )
                sink.write(chunk)
                written += len(chunk)
    except OSError as error:
        raise EndfieldUpdateError(_describe_os_error(error, info.filename)) from error
    if written != info.file_size:
        raise EndfieldUpdateError(
            f"{info.filename} 读出 {written} 字节，与包内声明的 {info.file_size} 不符"
        )


def _describe_os_error(error: OSError, name: str) -> str:
    if getattr(error, "winerror", None) == 5:
        return f"{name} 被占用或无权限写入，请确认终末地已完全退出后重试（{error}）"
    if getattr(error, "winerror", None) == 206:
        return (
            f"{name} 的路径超过 Windows 长度限制，"
            "请缩短安装目录或开启系统长路径支持后重试"
        )
    return f"写入 {name} 失败: {error}"


def _run_hpatchz(exe: Path, base: Path, diff: Path, out: Path, new_size: int) -> None:
    """单文件模式打差量：`hpatchz <基线> <差量> <输出>`，非 0 退出即失败。

    `new_size` 是这一条声明的新文件体积，用来把「盘写不下」从其它失败里分出来。
    """

    process = subprocess.run(
        [str(exe), str(base), str(diff), str(out)], capture_output=True
    )
    if process.returncode == 0:
        return
    free = shutil.disk_usage(out.parent).free
    if free < new_size:
        raise EndfieldUpdateError(
            f"磁盘余量不足：写 {out.name} 还差约 "
            f"{(new_size - free) / 1024**3:.1f} GB，当前只剩 "
            f"{free / 1024**3:.1f} GB，请清理磁盘后重试"
        )
    detail = (process.stdout or b"") + (process.stderr or b"")
    lines = detail.decode("utf-8", "replace").strip().splitlines()
    raise EndfieldUpdateError(
        f"差量应用失败（{base.name} → {out.name}）："
        f"hpatchz 退出码 {process.returncode}，"
        f"{lines[-1] if lines else '没有输出'}"
    )


async def _commit(temp: Path, target: Path, md5: str, size: int) -> None:
    """比过体积与 MD5 才把临时文件改名就位。

    先校验再移动：宁可这次更新停住，也不能把坏文件写进游戏目录。同卷下 `os.replace`
    是原子改名，不存在写一半的中间态。
    """

    actual = _size_of(temp)
    if actual != size:
        temp.unlink(missing_ok=True)
        raise EndfieldUpdateError(
            f"{target.name} 落地体积不符：期望 {size} 实际 {actual}"
        )
    digest = await asyncio.to_thread(_md5_of, temp)
    if digest != md5:
        temp.unlink(missing_ok=True)
        raise EndfieldUpdateError(
            f"{target.name} 落地校验未通过：期望 {md5} 实际 {digest}"
        )
    # 改名是单次系统调用，不走线程池：进了线程池，被判定「已中止」之后仍可能在后台
    # 把游戏文件换掉，回报的状态就和磁盘上的实情不一致
    _replace(temp, target)


def _collect_temp_files(root: Path) -> list[Path]:
    """在工作线程里收一遍残留的临时文件：遍历十万级目录是秒级的活，别压在事件循环上。"""

    return list(root.rglob("*" + _TEMP_SUFFIX))


async def _apply_delta(
    archive: pyzipper.AESZipFile,
    plan: DeltaPlan,
    install_dir: Path,
    staging: Path,
    hpatchz: Path,
    progress: ProgressFn | None,
    abort: threading.Event,
) -> int:
    """按差量计划落地：打差量 → 搬整文件 → 清理删除表 → 最后提交 `config.ini`。

    每条都先写进目标旁边的临时文件，比过 MD5 才改名；`config.ini` 单独暂存到收尾才
    提交，于是「安装目录里的版本号已是新版」等价于「本次其余文件都已落盘」，中途崩溃
    只留下旧版本号，下一轮按同一份清单重新判定。清单里没有而本地多出来的文件不删——
    删错了不可逆，而留着只是占地方。
    """

    total = len(plan.patches) + len(plan.moves)
    done = 0
    # 回收上一轮被中断时留下的临时文件：同名目标会被本轮截断覆盖，但文件名一旦变了，
    # 旧孤儿就永久留在游戏目录里。只认我们自己独占的那个后缀。
    for stray in await asyncio.to_thread(_collect_temp_files, install_dir):
        try:
            stray.unlink(missing_ok=True)
        except OSError as error:
            logger.warning(f"未能清理残留的临时文件 {stray.name}: {error}")

    async def _report(line: str) -> None:
        if progress is not None:
            await progress(line)

    async def _unpack(info: zipfile.ZipInfo, temp: Path) -> None:
        """在工作线程里解出一个成员，别把拷贝压在事件循环上。

        整文件的成员比差量卷本身还大，同步拷贝会卡住整个 MAS（其它专项、界面、接口都
        停），而 `asyncio.timeout` 只在 await 点生效，这段时间的超时上限形同虚设。挪进
        线程之后，`abort` 的逐块检查第一次真正起作用：中止后线程最多再写一块就自停。
        """

        task = asyncio.create_task(
            asyncio.to_thread(_write_member, archive, info, temp, abort)
        )
        # 线程里的异常在这里取回，不留「exception was never retrieved」
        task.add_done_callback(lambda done: done.cancelled() or done.exception())
        try:
            await asyncio.shield(task)
        except (TimeoutError, asyncio.CancelledError):
            abort.set()
            # 等它真的松手：这条线程还攥着暂存卷的读句柄，收尾删暂存就会删不动。
            # 线程最多再写一块就会自停，所以这个等待有上限，不等它把成员拷完。
            with suppress(BaseException):
                await asyncio.wait({task}, timeout=_UNPACK_DRAIN_SECONDS)
            raise

    for index, job in enumerate(plan.patches, start=1):
        target = _resolve_within(install_dir, job.path)
        temp = target.with_name(target.name + _TEMP_SUFFIX)
        try:
            temp.parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise EndfieldUpdateError(
                f"无法创建游戏目录 {temp.parent}：{error}"
            ) from error
        diff_file = staging / f"diff-{index:04d}{_TEMP_SUFFIX}"
        await _unpack(archive.getinfo(job.member), diff_file)
        try:
            await asyncio.to_thread(
                _run_hpatchz,
                hpatchz,
                _resolve_within(install_dir, job.base_path),
                diff_file,
                temp,
                job.size,
            )
        finally:
            diff_file.unlink(missing_ok=True)
        await _commit(temp, target, job.md5, job.size)
        done += 1
        await _report(f"正在打补丁并覆盖游戏文件 {done}/{total}")

    for job in plan.moves:
        target = _resolve_within(install_dir, job.path)
        temp = target.with_name(target.name + _TEMP_SUFFIX)
        await _unpack(archive.getinfo(job.member), temp)
        await _commit(temp, target, job.md5, job.size)
        done += 1
        await _report(f"正在打补丁并覆盖游戏文件 {done}/{total}")

    for path in plan.deletes:
        try:
            _resolve_within(install_dir, path).unlink(missing_ok=True)
        except OSError as error:
            # 删除失败只是留个没用的文件，不该让整轮更新停在这里
            logger.warning(f"未能按删除表清理 {path}: {error}")

    pending = staging / _PENDING_CONFIG_NAME
    await _unpack(archive.getinfo(plan.config_member), pending)
    # 携带新版本号的这份配置是本轮最后一次写入：单次原子改名，不进线程池
    _replace(pending, install_dir / _CONFIG_MEMBER)
    return done


def _md5_of(path: Path) -> str:
    digest = hashlib.md5()
    with open(_native_path(path), "rb") as handle:
        for block in iter(lambda: handle.read(_MD5_CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _hash_prefix(digest: Any, path: Path, limit: int) -> None:
    """续传前把已落盘的字节补进摘要。"""

    with open(_native_path(path), "rb") as handle:
        read = 0
        while read < limit:
            block = handle.read(min(_MD5_CHUNK, limit - read))
            if not block:
                break
            digest.update(block)
            read += len(block)


class _Reporter:
    """累计跨卷进度并按 `_PROGRESS_STEP` / `_PROGRESS_INTERVAL` 节流播报。"""

    def __init__(self, progress: ProgressFn | None, total: int, count: int) -> None:
        self._progress = progress
        self._total = total
        self._count = count
        self._downloaded = 0
        self._part = 0
        self._next_bytes = 0
        self._next_at = 0.0
        self._sent_bytes = 0
        self._sent_at = time.monotonic()

    def rewind(self, size: int) -> None:
        """把已计入但即将被覆盖重写的字节退回总量。

        「Range 被忽略 → 从头重写」这条路上，之前那次尝试计过的部分马上会被重新写
        一遍，不回收就会播报出超过总量的进度。
        """

        self._downloaded = max(self._downloaded - size, 0)
        self._next_bytes = self._downloaded
        self._next_at = 0.0
        # 速度窗口跟着重新起算：不退这一步，续传后第一行会把退回的字节当成没下的量
        self._sent_bytes = self._downloaded
        self._sent_at = time.monotonic()

    async def add(self, size: int, part: int) -> None:
        self._downloaded += size
        self._part = part
        now = time.monotonic()
        if self._progress is None:
            return
        # 两条门槛任一到了就播一行。要两条都过才出声，慢链路上能十几分钟一行不出，
        # 前端那套「多久没新日志就算连接断了」的看门狗会把正常推进的更新判死并中止
        if self._downloaded < self._next_bytes and now < self._next_at:
            return
        self._next_bytes = self._downloaded + _PROGRESS_STEP
        self._next_at = now + _PROGRESS_INTERVAL
        # 速度取相邻两行之间的平均，不是相邻两个分块之间的抖动；窗口不足一秒就不报，
        # 那种样本只会给出一个几百 MB/s 的假数
        elapsed = now - self._sent_at
        speed = (
            f"，{(self._downloaded - self._sent_bytes) / elapsed / 1024**2:.1f} MB/s"
            if elapsed >= 1.0
            else ""
        )
        self._sent_bytes, self._sent_at = self._downloaded, now
        # 百分比按真实字节封顶显示：MD5 不符删掉重下那截确实流过网络，速度照全量算
        shown = min(self._downloaded, self._total)
        percent = shown / self._total * 100 if self._total else 0.0
        await self._progress(
            f"正在下载游戏更新包 {shown / 1024**3:.2f}/"
            f"{self._total / 1024**3:.2f} GB"
            f"（{percent:.1f}%，第 {self._part}/{self._count} 卷{speed}）"
        )


async def _download_part(
    client: httpx.AsyncClient,
    url: str,
    size: int,
    temp: Path,
    reporter: _Reporter,
    part: int,
) -> str:
    """下载单卷，返回落盘内容的 MD5。

    单会话顺序读，绝不分片并发：CDN 若忽略 `Range` 会给回整份正文，多会话各自写回
    自己那一段，结果文件长度对得上、内容却是若干份重复正文 —— 静默损坏，只有末尾那
    次 MD5 能发现。
    """

    resume_from = max(_size_of(temp), 0)
    if resume_from > size:
        temp.unlink(missing_ok=True)
        resume_from = 0
    digest = hashlib.md5()
    mode = "ab" if resume_from else "wb"
    headers = {"Range": f"bytes={resume_from}-"} if resume_from else {}
    # 服务端忽略 Range 时给回 200 与整份正文，这时必须从头覆盖写：追加会把新内容
    # 接在旧字节后面，静默写出坏文件
    async with client.stream("GET", url, headers=headers) as response:
        if response.status_code == 200 and resume_from:
            logger.warning("CDN 忽略了 Range，本卷从头重写")
            reporter.rewind(resume_from)
            resume_from = 0
            mode = "wb"
        response.raise_for_status()
        if mode == "ab":
            await asyncio.to_thread(_hash_prefix, digest, temp, resume_from)
        async with aiofiles.open(_native_path(temp), mode) as sink:
            async for chunk in response.aiter_bytes(_DOWNLOAD_CHUNK):
                if not chunk:
                    continue
                await sink.write(chunk)
                digest.update(chunk)
                await reporter.add(len(chunk), part)
    return digest.hexdigest()


async def _download_release(
    release: Release,
    staging: Path,
    progress: ProgressFn | None,
    identity: InstallIdentity,
) -> list[Path]:
    """下载全部差量分卷，逐卷校验后改名就位。

    体积相符的既有分卷先比 MD5 决定复用：每轮开头会清暂存目录，但被句柄扣住的那卷删不
    动、会留到下一轮，认出指纹就接着用，不重下。中途换新签名地址或某一卷重下时同样兜住。

    Raises:
        EndfieldUpdateError: 某一卷反复下载或校验不过，或换新清单后发现版本与指纹
            都变了（混用两个构建的分卷会静默毁掉游戏目录）。
    """

    files: list[Path] = []
    count = len(release.parts)
    # 落盘名取自 URL 末段：两卷同名就是互相覆盖，拼流会把一卷当两卷读。开局就判废，
    # 别等到落地阶段报「比服务端声明的短」——那时谁也说不清是哪一卷
    names = [_file_name_from_url(part.url) for part in release.parts]
    if len(set(names)) != count:
        raise EndfieldUpdateError("服务端给出的差量分卷有重名，无法区分两卷内容")
    reporter = _Reporter(progress, release.download_size, count)
    current = release
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(_READ_TIMEOUT, connect=_CONNECT_TIMEOUT),
        follow_redirects=True,
    ) as client:
        for index, planned in enumerate(release.parts, start=1):
            target = staging / names[index - 1]
            if _size_of(target) == planned.size and (
                not planned.md5
                or await asyncio.to_thread(_md5_of, target) == planned.md5
            ):
                logger.info(f"复用已下载的分卷: {target.name}")
                await reporter.add(planned.size, index)
                files.append(target)
                continue
            temp = target.with_name(target.name + _TEMP_SUFFIX)
            part = planned
            for attempt in range(1, _PART_ATTEMPTS + 1):
                if time.monotonic() - current.fetched_at > _MANIFEST_MAX_AGE:
                    current = await _refresh_plan(identity, current)
                    part = current.parts[index - 1]
                try:
                    digest = await _download_part(
                        client, part.url, planned.size, temp, reporter, index
                    )
                except httpx.HTTPStatusError as error:
                    if error.response.status_code not in (401, 403, 404, 410):
                        raise
                    # 签名地址过期是常态，换新地址再来一轮，不占用一次判失败
                    logger.warning(
                        f"{target.name} 返回 {error.response.status_code}，换签名地址重试"
                    )
                    current = await _refresh_plan(identity, current)
                    part = current.parts[index - 1]
                    continue
                except httpx.TransportError as error:
                    # 中途断流、连接重置与读超时都到不了状态码，只会以传输层异常收场。
                    # 已落盘的字节留着，换一把地址从断点接着下；试满才判废。
                    logger.warning(
                        f"{target.name} 传输中断（{type(error).__name__}），换签名地址续传"
                    )
                    current = await _refresh_plan(identity, current)
                    part = current.parts[index - 1]
                    continue
                if _size_of(temp) != planned.size:
                    logger.warning(
                        f"{target.name} 体积不符（{_size_of(temp)} != {planned.size}），重下"
                    )
                elif planned.md5 and digest != planned.md5:
                    logger.warning(
                        f"{target.name} 校验未通过（期望 {planned.md5} 实际 {digest}），重下"
                    )
                    # 坏文件必须删掉：留着它下一轮会从错的位置续传，越修越坏
                    temp.unlink(missing_ok=True)
                else:
                    _replace(temp, target)
                    files.append(target)
                    break
            else:
                # 含「每次都是签名无效/过期」这条路：`continue` 也会走到这里，绝不放过
                # 少一卷的静默结果——拼流少一卷会写成半新半旧的包，比不更新更坏
                raise EndfieldUpdateError(
                    f"{target.name} 试满 {_PART_ATTEMPTS} 次仍未拿到完好的一卷，"
                    "请检查网络后重试"
                )
    if len(files) != len(release.parts):
        raise EndfieldUpdateError(
            f"差量卷应有 {len(release.parts)} 卷，实际只拿到 {len(files)} 卷"
        )
    return files


async def _refresh_plan(identity: InstallIdentity, current: Release) -> Release:
    """取一份新清单换回签名地址，并确认它描述的还是同一轮差量。

    必须用同一份身份重问：报目标版本会被服务端当成「已是最新」而回空差量，那样每次
    刷新都会误判成清单变了，整轮下载必然中止。
    """

    fresh = await _fetch_release(identity)
    if fresh.version != current.version:
        raise EndfieldUpdateError(
            f"下载期间服务端把最新版本换成了 {fresh.version}"
            f"（本轮目标 {current.version}）；混用两个构建的分卷会毁掉游戏目录，"
            "本轮更新中止，请重新发起"
        )
    if [part.md5 for part in fresh.parts] != [part.md5 for part in current.parts]:
        raise EndfieldUpdateError(
            f"下载期间服务端差量指纹发生变化（{len(current.parts)} 卷 → "
            f"{len(fresh.parts)} 卷），本轮更新中止，请重新发起"
        )
    return fresh


async def _prefetch_moves(
    client: httpx.AsyncClient,
    release: Release,
    report: ProgressFn,
) -> tuple[MoveEntry, ...] | None:
    """在下载之前从远端读出包内的整文件清单，好把下载与落地的体积合成一次判定。

    只发几次小请求，不落下任何正文；读不到就返回 `None`，落地前那道门仍是权威判据。
    分卷地址带签名、有效窗口两分钟上下，这一步要在读盘核对基线之前做完。
    """

    await report("正在预取包内清单，先核对磁盘余量")
    doc = await package_index.fetch_member_json(
        client=client,
        volumes=[
            package_index.RemoteVolume(part.url, part.size) for part in release.parts
        ],
        cd_key=release.cd_key,
        member=_VERIFY_MANIFEST_MEMBER,
        max_plain_bytes=_MANIFEST_MAX_BYTES,
    )
    if doc is None:
        await report("未能预取到包内清单，本轮改为下载后再核对磁盘余量")
        return None
    entries = _move_entries(doc)
    await report(
        f"预取到包内整文件清单 {len(entries)} 条，按下载与落地的总量核对磁盘余量"
    )
    return entries


async def ensure_game_updated(
    game_exe: Path,
    *,
    time_limit_minutes: int,
    progress: ProgressFn | None = None,
    entry: str = "自动",
) -> GameUpdateResult:
    """对外入口：跑一轮判定，并把开始、过程与结论都写进 `debug/app.log`。

    时限包住「核对基线 + 下载差量 + 落地」三段；进度行只往调度台推，同一行由本函数写进
    `debug/app.log`；`entry` 只进日志，用来区分自动门与脚本页手动按钮。
    """

    logger.info(
        f"{entry}发起终末地客户端更新检查: 安装目录 {game_exe.parent}"
        f"（限时 {time_limit_minutes} 分钟）"
    )
    outcome = ("已取消", "本轮更新被取消（用户点了停止，或看门狗下发了中止）")
    try:
        result = await _ensure_game_updated(
            game_exe, time_limit_minutes=time_limit_minutes, progress=progress
        )
    except Exception as error:
        outcome = ("异常", f"未得出结论文案：{type(error).__name__}: {error}")
        raise
    else:
        outcome = (result.status, result.message)
    finally:
        logger.info(f"终末地客户端更新结论（{entry}）: {outcome[0]} - {outcome[1]}")
    return result


async def _ensure_game_updated(
    game_exe: Path,
    *,
    time_limit_minutes: int,
    progress: ProgressFn | None,
) -> GameUpdateResult:
    """检查并在需要时由 MAS 接管终末地 PC 客户端的差量更新。

    对外承诺不抛异常：判不了的走 `Skipped`（读不到本地版本、问不动服务端），确认要更新
    却做不到的走 `NeedManualUpdate`（这条基线没有差量、本地基线与清单不符、下载或落地
    失败），意外异常也归到后者——调用方据此决定放行还是阻断，不需要再猜目录有没有被动
    过。不做整包兜底：判不了就不动，动不了就停下提示手动更新。
    """

    if not game_exe.is_file():
        return GameUpdateResult("Skipped", f"未找到终末地客户端: {game_exe}")

    install_dir = game_exe.parent
    identity = read_install_identity(install_dir)
    if not identity.version:
        return GameUpdateResult(
            "Skipped",
            f"读不到终末地客户端的版本号（{install_dir / _CONFIG_MEMBER}），跳过检查",
        )
    preset = _match_preset(identity)
    if preset is None:
        _log_unknown_server(identity)
        return GameUpdateResult("Skipped", UNKNOWN_SERVER_MESSAGE)

    try:
        release = await _fetch_release(identity)
    except (httpx.HTTPError, EndfieldUpdateError, ValueError) as error:
        logger.warning(f"检查终末地客户端更新失败，跳过检查: {error}")
        return GameUpdateResult(
            "Skipped", f"未能获取终末地客户端版本信息（{error}），跳过检查"
        )

    logger.info(
        f"本地版本 {identity.version}，客户端登记 "
        f"appcode={identity.appcode} channel={identity.channel}"
        f" sub_channel={identity.sub_channel}，匹配到 {preset['label']}，"
        f"服务端给出 {release.version}"
    )

    latest = f"终末地客户端已是最新版本 {identity.version}"
    if identity.version == release.version:
        # 服务端给的差量卷可能是按别的基线算的：本地已是目标版就什么都不做，否则基线
        # 核对注定失败，把没动过的客户端说成「被改过」是冤枉
        return GameUpdateResult("UpToDate", latest)
    if not release.parts:
        # 空差量段：要么已是最新，要么这条基线没有差量
        if not is_client_outdated(identity.version, release.version):
            return GameUpdateResult("UpToDate", latest)
        return GameUpdateResult(
            "NeedManualUpdate",
            f"终末地客户端版本落后（已安装 {identity.version}，最新 {release.version}），"
            f"但官方没有 {identity.version} 这一路的增量包，请用启动器手动更新一次",
        )
    if not is_client_outdated(identity.version, release.version):
        logger.warning(
            f"服务端给出差量但本地版本不比它旧（本地 {identity.version}，"
            f"目标 {release.version}）"
        )
        return GameUpdateResult(
            "UpToDate",
            f"终末地客户端不比目标旧（本地 {identity.version}，目标 {release.version}），"
            "未做任何改动",
        )

    outdated = (
        f"终末地客户端版本落后（已安装 {identity.version}，最新 {release.version}）"
    )
    blocked = await _release_install_dir(game_exe)
    if blocked:
        return GameUpdateResult("NeedManualUpdate", f"{outdated}，{blocked}")
    unwritable = _write_probe(install_dir)
    if unwritable:
        return GameUpdateResult("NeedManualUpdate", f"{outdated}，{unwritable}")
    short = _disk_shortfall(
        install_dir, release.download_size + _RESERVE_BYTES, "游戏目录（下载差量包）"
    )
    if short:
        return GameUpdateResult("NeedManualUpdate", f"{outdated}，{short}")

    staging = install_dir / _STAGING_DIR_NAME
    abort = threading.Event()
    landed = 0

    async def report(line: str) -> None:
        """每条播报同时进 `debug/app.log` 与调度台：前者才是用户反馈时会带来的那份。"""

        logger.info(line)
        if progress is not None:
            await progress(line)

    try:
        # 清暂存与建目录都在 try 内：本函数对外承诺不抛，暂存名被占成文件、盘只读这类
        # 情况也要落成一条看得懂的结论，而不是让任务直接异常
        force_rmtree(staging)
        staging.mkdir(parents=True, exist_ok=True)
        async with asyncio.timeout(time_limit_minutes * 60):
            await report(
                f"{outdated}\n按 {preset['label']} 的服务器参数核对官方差量清单"
                f"（差量 {len(release.parts)} 卷 / "
                f"{release.download_size / 1024**3:.1f} GB）"
            )
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(_READ_TIMEOUT, connect=_CONNECT_TIMEOUT),
                follow_redirects=True,
            ) as client:
                specs = await _fetch_patch_manifest(
                    client, release.patch_info_url, release.patch_info_md5
                )
                prefetched = await _prefetch_moves(client, release, report)
            if prefetched is not None:
                # 下载与落地共用一个盘，两笔体积必须在这一刻一起算：卷要读到最后一刻
                # 才清，落地那一刻暂存卷还压在同一个目录里
                landing_need = _landing_need(specs, prefetched, install_dir)
                short = _disk_shortfall(
                    install_dir,
                    release.download_size + landing_need + _RESERVE_BYTES,
                    "游戏目录（下载与落地）",
                )
                if short:
                    return GameUpdateResult(
                        "NeedManualUpdate",
                        f"{outdated}，本轮尚未开始下载，暂存卷还没占盘："
                        f"下载差量包约 {release.download_size / 1024**3:.1f} GB，"
                        f"落地还要在游戏目录净腾出约 {landing_need / 1024**3:.1f} GB，"
                        f"再加一份固定余量。{short}",
                    )
            bad = await _check_baselines(specs, install_dir, report, abort)
            if bad:
                shown = "、".join(Path(path).name for path in bad[:5])
                return GameUpdateResult(
                    "NeedManualUpdate",
                    f"{outdated}，本地 {len(bad)} 个文件与官方基线不符（{shown}"
                    f"{' 等' if len(bad) > 5 else ''}），MAS 不覆盖改动过的客户端，"
                    "请用启动器手动更新一次",
                )

            hpatchz = await ensure_hpatchz(on_progress=report)
            files = await _download_release(release, staging, report, identity)
            # 下载要花几分钟，期间用户完全可能自己把游戏开回去；UE 客户端锁着
            # .ucas/.pak，这时候开写就是 PermissionError。只检测不强杀：那是用户在
            # MAS 不知情下自己开的窗口，没被授权关掉它
            busy = await _busy_processes(install_dir)
            if busy:
                raise EndfieldUpdateError(
                    f"下载期间游戏被重新启动（{', '.join(busy)}），本轮不覆盖，"
                    "请退出游戏后重试"
                )

            stream = _SplicedStream(files, [part.size for part in release.parts])
            try:
                archive = pyzipper.AESZipFile(
                    io.BufferedReader(stream, buffer_size=4 * _DOWNLOAD_CHUNK)
                )
                # 差量包是 WinZip AES-256；口令就是服务端的 patch.cd_key
                archive.setpassword(release.cd_key.encode())
                members = {
                    info.filename for info in archive.infolist() if not info.is_dir()
                }
                moves, deletes = _read_package_manifests(archive, members)
                plan = _build_delta_plan(specs, members, moves, deletes)
                landing = _disk_shortfall(
                    install_dir,
                    _landing_need(plan.patches, plan.moves, install_dir)
                    + _RESERVE_BYTES,
                    "游戏目录（差量落地）",
                )
                if landing:
                    raise EndfieldUpdateError(landing)
                await report(
                    f"差量包就位，开始覆盖安装目录：{len(plan.patches)} 个打补丁 + "
                    f"{len(plan.moves)} 个整文件，共 "
                    f"{plan.expanded_bytes / 1024**3:.1f} GB"
                )
                landed = await _apply_delta(
                    archive, plan, install_dir, staging, hpatchz, report, abort
                )
                archive.close()
            finally:
                stream.close()
    except TimeoutError:
        abort.set()
        return GameUpdateResult(
            "NeedManualUpdate",
            f"{outdated}，MAS 更新超过 {time_limit_minutes} 分钟已中止，"
            "请放宽游戏更新超时限制或手动更新一次",
        )
    except asyncio.CancelledError:
        # 用户点了停止：CancelledError 不是 Exception，不进下面的兜底，必须自己把中止
        # 标志递下去，让正在拷贝成员的工作线程停下。版本号还没提交，游戏目录停在旧版，
        # 下一轮按同一份清单重新判定；没改名的临时文件会被下一轮回收。
        abort.set()
        raise
    except (EndfieldUpdateError, httpx.HTTPError, OSError) as error:
        detail = (
            _describe_os_error(error, "游戏目录")
            if isinstance(error, OSError)
            else str(error)
        )
        logger.warning(f"终末地差量更新失败: {error}")
        return GameUpdateResult(
            "NeedManualUpdate",
            f"{outdated}，MAS 自动更新失败（{detail}），请手动更新游戏后重试",
        )
    except Exception as error:
        # 兜底：本函数对外承诺不抛，调用方才能拿 status 决定放行还是阻断。走到这里
        # 说明有没预料到的异常类型（包内解析、线程池等），一律按「需要手动更新」处理
        logger.opt(exception=True).warning(f"终末地差量更新出现未预料的异常: {error}")
        return GameUpdateResult(
            "NeedManualUpdate",
            f"{outdated}，MAS 自动更新失败（{type(error).__name__}: {error}），"
            "请手动更新游戏后重试",
        )
    finally:
        # 无论成败都不把差量卷留在用户盘上。中止那条路上可能仍有工作线程攥着卷句柄，
        # 那种文件在 Windows 上删不动，会被跳过并留到下一轮开头清掉，所以这里不断言清干净了
        force_rmtree(staging)
        if abort.is_set():
            logger.info("本轮差量更新已中止")

    committed = read_installed_version(install_dir)
    if committed != release.version:
        return GameUpdateResult(
            "NeedManualUpdate",
            f"MAS 已完成差量落地，但游戏版本号仍是 {committed or '未知'}"
            f"（目标 {release.version}），请手动更新一次后重试；若反复出现请反馈",
        )
    note = f"（{landed} 个文件，下载 {release.download_size / 1024**3:.1f} GB）"
    return GameUpdateResult("Updated", f"MAS 已将终末地客户端更新至 {committed}{note}")
