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

"""终末地客户端身份、官方更新响应与差量清单解析。"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import httpx
from Crypto.Cipher import AES

from app.utils.constants import ENDFIELD_SERVER_PRESETS

from .common import (
    _CONFIG_MEMBER,
    _CONNECT_TIMEOUT,
    _MANIFEST_MAX_BYTES,
    _READ_TIMEOUT,
    UNKNOWN_SERVER_MESSAGE,
    EndfieldUpdateError,
    InstallIdentity,
    MoveJob,
    PackagePart,
    PatchJob,
    Release,
    logger,
)

_DIFF_MEMBER_PREFIX = "vfs_files/vfs_patch/"
_MAX_PARTS = 512
_MAX_ENTRIES = 20_000
"""分卷数与清单条目数上限：超出时停止解析。"""
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


def _file_name_from_url(url: str) -> str:
    """从下载地址取落盘文件名。并检查文件名是否可用。"""

    path = url.split("?", 1)[0].split("#", 1)[0]
    name = unquote(path.rsplit("/", 1)[-1]).strip()
    if (
        not name
        or name in {".", ".."}
        or any(sep in name for sep in ("/", "\\", ":", "\x00"))
    ):
        raise EndfieldUpdateError(f"下载地址里的文件名不可用: {path!r}")
    return name


def _safe_file_name(url: str) -> str:
    """取分卷落盘名；名字不可用时返回空串，交给需要报错的那一处去报。

    认盘上已有文件时不值得为「名字不可用」当场判废：那一卷没有可复用的候选，重下就好。
    真正要拦下的地方是 `_download_release`——那里名字缺失就意味着拼流会缺卷，必须响亮报错。
    """

    try:
        return _file_name_from_url(url)
    except EndfieldUpdateError:
        return ""


def _parse_int(raw: object) -> int:
    """服务端把体积给成字符串；解析失败时返回 0，由调用方检查是否有效。"""

    if raw is None:
        return 0
    match = _DIGITS_RE.match(str(raw).strip())
    return int(match.group(1)) if match else 0


def _parse_release(payload: object) -> Release:
    if not isinstance(payload, dict):
        raise EndfieldUpdateError("启动器响应不是 JSON 对象")
    rsps = payload.get("proxy_rsps") or []
    if not isinstance(rsps, list):
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
            return _parse_latest_game(body)
    logger.warning(
        f"启动器响应里没有 get_latest_game 条目，响应片段: {str(payload)[:200]}"
    )
    raise EndfieldUpdateError("启动器响应里缺终末地的版本信息条目")


def _parse_latest_game(body: dict) -> Release:
    # 目标版本只取 `version`：`pre_patch` 是预下载那条独立安装路径的版本，跟着它写会把
    # 没发布出去的版本号盖进客户端。
    version = str(body.get("version") or "").strip()
    if not version:
        raise EndfieldUpdateError("启动器响应里没有版本号")

    patch = body.get("patch")
    if not isinstance(patch, dict):
        # 没有差量时，由入口根据版本号决定是否需要手动更新。
        return Release(version=version, parts=())

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
            raise EndfieldUpdateError(f"服务端未给出第 {index + 1} 卷的差量卷体积")
        url = str(pack["url"])
        if not _SCHEME_RE.match(url):
            # 下载地址必须完整，详细地址只记入日志。
            logger.warning(f"第 {index + 1} 卷的差量卷地址不是绝对地址: {url!r}")
            raise EndfieldUpdateError(f"服务端给的第 {index + 1} 卷下载地址不完整")
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
    )


def _match_preset(identity: InstallIdentity) -> dict[str, str] | None:
    """按客户端三元组匹配服务器；未知组合不得猜测或混用其他服务器参数。"""

    return ENDFIELD_SERVER_PRESETS.get(
        (identity.appcode, identity.channel, identity.sub_channel)
    )


def _log_unknown_server(identity: InstallIdentity) -> None:
    logger.warning(
        "终末地客户端登记的服务器不在已知四类之内: "
        f"appcode={identity.appcode or '空'} channel={identity.channel or '空'}"
        f" sub_channel={identity.sub_channel or '空'}"
    )


async def _fetch_release(
    identity: InstallIdentity, *, preset: dict[str, str] | None = None
) -> Release:
    """上报本地版本原文，换回差量计划。

    请求参数使用调用方已匹配的预设；未传入时按客户端身份匹配。版本号使用本地原文。

    Raises:
        EndfieldUpdateError: 三元组匹配不到已知服务器参数。
    """

    if preset is None:
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
    return _parse_release(response.json())


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

    # 这份配置只有加密一种形态：解不开就按读不到处理，不猜内容，也不试明文
    try:
        cipher = AES.new(_CONFIG_KEY, AES.MODE_CBC, _CONFIG_IV)
        text = _strip_padding(cipher.decrypt(raw)).decode("utf-8", "replace")
    except (ValueError, KeyError) as error:
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


def _canonical_relative(name: str) -> str:
    """规范化清单路径，拒绝上级目录与非法字符。

    规范化结果同时用于匹配包内成员与落盘；不能只靠会折叠 .. 的 _resolve_within。"""

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


async def _fetch_patch_manifest(
    client: httpx.AsyncClient, url: str, digest: str
) -> tuple[PatchJob, ...]:
    """取差量清单 `patch.json`：明文 JSON，限制读取大小并核对服务端提供的 MD5。

    Returns:
        要打差量的条目，路径已并上清单给的 VFS 根。整文件不在这里——它们连同落地核对表
        一起由包内 `verify_files.json` 给出。

    Raises:
        EndfieldUpdateError: 清单读不懂、MD5 不符、或给出 MAS 不认的多跳差量。
    """

    raw = bytearray()
    async with client.stream("GET", url) as response:
        response.raise_for_status()
        async for chunk in response.aiter_bytes(64 * 1024):
            if len(raw) + len(chunk) > _MANIFEST_MAX_BYTES:
                raise EndfieldUpdateError(
                    f"差量清单超过 {_MANIFEST_MAX_BYTES} 字节上限"
                )
            raw.extend(chunk)
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

    specs: list[PatchJob] = []
    for item in entries:
        if not isinstance(item, dict):
            raise EndfieldUpdateError(f"差量清单条目不是对象: {item!r}")
        nodes = item.get("patch")
        if not nodes:
            continue
        if not isinstance(nodes, list) or len(nodes) != 1:
            # 当前只支持从本地基线直接更新到目标版本。
            count = len(nodes) if isinstance(nodes, list) else 0
            raise EndfieldUpdateError(f"清单给出 {count} 跳差量，MAS 只认单跳")
        node = nodes[0]
        if not isinstance(node, dict):
            raise EndfieldUpdateError(f"差量条目不是对象: {node!r}")
        specs.append(
            PatchJob(
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


def _move_entries(doc: dict[str, Any]) -> tuple[MoveJob, ...]:
    """把包内落地核对表的 `move` 段读成整文件清单。"""

    entries: list[MoveJob] = []
    for item in doc.get("move") or []:
        if not isinstance(item, dict):
            raise EndfieldUpdateError(f"落地核对表条目不是对象: {item!r}")
        entries.append(
            MoveJob(
                path=_canonical_relative(str(item.get("path") or "")),
                md5=str(item.get("md5") or "").strip().lower(),
                size=_parse_int(item.get("size")),
            )
        )
    return tuple(entries)
