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

"""模拟器层面的游戏客户端 APK 更新公共原语。

模块只提供与具体游戏无关的能力：通过 adb 读取/安装客户端、版本比较、
流式下载安装包、按 HTTP Range 读取远端安装包的版本号。各专项（MAA / SRC 等）
与 MaaFW 特调（M9A）自行对接各自游戏的版本接口与下载入口后调用本模块完成
"检查版本 → 下载 → 安装"的编排。
"""

from __future__ import annotations

import asyncio
import re
import shutil
import struct
import zlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import aiofiles
import httpx

from app.utils import ProcessRunner, get_logger

logger = get_logger("游戏 APK 更新")

APK_MIN_BYTES = 64 * 1024 * 1024
"""安装包体积下限，低于此值判定为下载到错误内容（如跳转页 HTML）"""

_VERSION_NAME_RE = re.compile(r"versionName=([\w.\-]+)")

_ZIP_EOCD_SIGNATURE = b"PK\x05\x06"
_ZIP64_LOCATOR_SIGNATURE = b"PK\x06\x07"
_ZIP64_EOCD_SIGNATURE = b"PK\x06\x06"
_ZIP_CENTRAL_SIGNATURE = b"PK\x01\x02"
_ZIP_LOCAL_SIGNATURE = b"PK\x03\x04"
_ZIP_EOCD_MAX_TAIL = 22 + 0xFFFF
"""ZIP 目录尾记录（22 字节）加最长注释，目录尾一定落在文件末尾这么多字节里"""
_MANIFEST_ENTRY = "AndroidManifest.xml"
_MANIFEST_MAX_BYTES = 8 * 1024 * 1024
"""清单文件（压缩前后）的体积上限；超过就不是正常的清单，不读"""
_CENTRAL_DIRECTORY_MAX_BYTES = 32 * 1024 * 1024
"""中央目录体积上限；大型游戏安装包实测不到 1 MB"""

# 二进制 AXML 的块类型与 android 属性的资源 ID（framework 固定值）
_AXML_STRING_POOL = 0x0001
_AXML_RESOURCE_MAP = 0x0180
_AXML_START_ELEMENT = 0x0102
_AXML_TYPE_STRING = 0x03
_ANDROID_ATTR_NAMES = {
    0x0101021B: "versionCode",
    0x0101021C: "versionName",
}


@dataclass
class GameUpdateResult:
    """游戏更新检查与接管的结果"""

    status: Literal["Skipped", "UpToDate", "Updated", "NeedManualUpdate"]
    """``Skipped`` 未执行检查；``UpToDate`` 无需更新；``Updated`` 已由 MAS 完成更新；
    ``NeedManualUpdate`` 需要用户手动更新，本次不应继续代理"""
    message: str
    """面向用户的说明文本"""
    resource_version: str = ""
    """可选的服务端资源版本号；仅部分游戏提供（如明日方舟用于识别待下载的资源热更新），
    未提供时为空字符串"""


async def _run_adb(
    adb_path: Path | None,
    adb_address: str,
    *args: str,
    timeout: float = 60,
) -> tuple[int, str]:
    """执行一条 adb 命令，返回 (返回码, 合并后的输出)。"""

    program: Path | str = adb_path if adb_path is not None else "adb"
    result = await ProcessRunner.run_process(
        program,
        "-s",
        adb_address,
        *args,
        timeout=timeout,
        if_merge_std=True,
    )
    return result.returncode, result.stdout.strip()


async def get_installed_client_version(
    adb_path: Path | None, adb_address: str, package_name: str
) -> str | None:
    """读取模拟器内已安装的客户端版本号。

    Returns:
        str | None: 版本号；游戏未安装或读取失败时返回 ``None``。
    """

    if ":" in adb_address:
        # host:port 形式的设备需要先建立连接，否则 -s 会找不到设备
        await _run_adb(adb_path, adb_address, "connect", adb_address, timeout=20)

    returncode, output = await _run_adb(
        adb_path,
        adb_address,
        "shell",
        "dumpsys",
        "package",
        package_name,
        timeout=30,
    )
    if returncode != 0:
        logger.warning(f"读取已安装版本失败: returncode={returncode}, output={output}")
        return None

    match = _VERSION_NAME_RE.search(output)
    if match is None:
        logger.info(f"未在模拟器中找到已安装的 {package_name}")
        return None

    version = match.group(1)
    logger.info(f"模拟器内 {package_name} 已安装版本: {version}")
    return version


def _parse_version(version: str) -> tuple[int, ...]:
    """把形如 ``2.7.61`` 的版本号解析为可比较的整数元组，无法解析的段落按 0 处理。

    只比较主版本号：开头的 ``v`` / ``V`` 去掉，第一个 ``-`` / ``+`` 之后的构建后缀
    不参与比较（``3.9.0-112.0.1361`` 按 ``3.9.0`` 算）。否则后缀里的数字会被当成
    更低位的版本段，同一主版本、一边带构建号一边不带时就会误判成落后，触发一次
    白下的安装包。
    """

    core = re.split(r"[-+]", version.strip().lstrip("vV"), maxsplit=1)[0]
    parts: list[int] = []
    for segment in core.split("."):
        digits = re.match(r"\d+", segment.strip())
        parts.append(int(digits.group()) if digits else 0)
    return tuple(parts)


def is_client_outdated(installed: str, remote: str) -> bool:
    """判断已安装客户端是否落后于服务端版本。"""

    installed_parts = _parse_version(installed)
    remote_parts = _parse_version(remote)
    if not any(installed_parts) or not any(remote_parts):
        # 任一侧完全解析不出数字时不敢下判断，按未落后处理，交给上游原有流程
        logger.warning(f"版本号无法比较: 已安装 {installed}, 服务端 {remote}")
        return False
    length = max(len(installed_parts), len(remote_parts))
    installed_parts += (0,) * (length - len(installed_parts))
    remote_parts += (0,) * (length - len(remote_parts))
    return installed_parts < remote_parts


@dataclass
class RemoteApkVersion:
    """从远端安装包清单里读到的身份与版本"""

    package: str
    """包名，调用方可据此确认拿到的是自己要的那个游戏"""
    version_name: str
    """``versionName``，与 ``get_installed_client_version`` 读到的是同一个字段"""
    version_code: int | None = None
    """``versionCode``；清单里没有或不是整数时为 ``None``"""


class _RemoteApkError(RuntimeError):
    """远端安装包读不出版本（服务器不支持 Range、不是 ZIP、清单格式不对等）"""


async def _read_range(
    client: httpx.AsyncClient, url: str, start: int, end: int
) -> bytes:
    """按 Range 读 ``[start, end]`` 闭区间的字节。

    服务器没按 206 返回（忽略了 Range，要整包往下发）时不读响应体，直接失败——
    安装包动辄几个 GB，不能因为一次 Range 失效就把整包拉下来。
    """

    expected = end - start + 1
    chunks: list[bytes] = []
    received = 0
    async with client.stream(
        "GET", url, headers={"Range": f"bytes={start}-{end}"}
    ) as response:
        if response.status_code != 206:
            raise _RemoteApkError(
                f"服务器未按 Range 返回（HTTP {response.status_code}）"
            )
        async for chunk in response.aiter_bytes():
            received += len(chunk)
            if received > expected:
                raise _RemoteApkError("服务器返回的字节数多于请求的范围")
            chunks.append(chunk)
    if received != expected:
        raise _RemoteApkError(f"服务器只返回了 {received}/{expected} 字节")
    return b"".join(chunks)


async def _read_total_size(client: httpx.AsyncClient, url: str) -> int:
    """用 ``Range: bytes=0-0`` 的 GET 取文件总长（不用 HEAD：部分 CDN 对 HEAD 拒绝服务）。"""

    async with client.stream("GET", url, headers={"Range": "bytes=0-0"}) as response:
        if response.status_code != 206:
            raise _RemoteApkError(
                f"服务器不支持按范围读取（HTTP {response.status_code}）"
            )
        content_range = response.headers.get("content-range", "")
    total = content_range.rpartition("/")[2].strip()
    if not total.isdigit():
        raise _RemoteApkError(f"无法从 Content-Range 取到文件总长: {content_range!r}")
    return int(total)


def _find_central_directory(tail: bytes) -> tuple[int, int] | None:
    """在文件末尾的字节里找目录尾记录，返回 ``(中央目录偏移, 中央目录长度)``。

    返回 ``None`` 表示这是 ZIP64 包，要再读一次 ZIP64 目录尾。
    """

    position = tail.rfind(_ZIP_EOCD_SIGNATURE)
    if position < 0 or len(tail) - position < 22:
        raise _RemoteApkError("文件末尾找不到 ZIP 目录尾记录，可能不是安装包")
    cd_size, cd_offset = struct.unpack_from("<II", tail, position + 12)
    if cd_size == 0xFFFFFFFF or cd_offset == 0xFFFFFFFF:
        return None
    return cd_offset, cd_size


def _find_zip64_record_offset(tail: bytes) -> int:
    position = tail.rfind(_ZIP_EOCD_SIGNATURE)
    locator = position - 20
    if locator < 0 or tail[locator : locator + 4] != _ZIP64_LOCATOR_SIGNATURE:
        raise _RemoteApkError("ZIP64 目录尾定位记录缺失")
    return struct.unpack_from("<Q", tail, locator + 8)[0]


def _find_manifest_entry(central_directory: bytes) -> tuple[int, int, int, int]:
    """在中央目录里找清单条目，返回 ``(本地头偏移, 压缩方式, 压缩后长度, 原始长度)``。"""

    position = 0
    while position + 46 <= len(central_directory):
        if central_directory[position : position + 4] != _ZIP_CENTRAL_SIGNATURE:
            raise _RemoteApkError("中央目录条目签名不对")
        (
            method,
            compressed_size,
            file_size,
            name_length,
            extra_length,
            comment_length,
            header_offset,
        ) = struct.unpack_from("<10xH8xIIHHH8xI", central_directory, position)
        name_start = position + 46
        name = central_directory[name_start : name_start + name_length]
        if name.decode("utf-8", "replace") == _MANIFEST_ENTRY:
            extra = central_directory[
                name_start + name_length : name_start + name_length + extra_length
            ]
            file_size, compressed_size, header_offset = _apply_zip64_extra(
                extra, file_size, compressed_size, header_offset
            )
            return header_offset, method, compressed_size, file_size
        position = name_start + name_length + extra_length + comment_length
    raise _RemoteApkError(f"安装包里没有 {_MANIFEST_ENTRY}")


def _apply_zip64_extra(
    extra: bytes, file_size: int, compressed_size: int, header_offset: int
) -> tuple[int, int, int]:
    """条目字段是 0xFFFFFFFF 时，真实值按顺序放在 ZIP64 扩展字段（0x0001）里。"""

    position = 0
    while position + 4 <= len(extra):
        tag, size = struct.unpack_from("<HH", extra, position)
        if tag == 0x0001:
            values = extra[position + 4 : position + 4 + size]
            cursor = 0

            def take(current: int) -> int:
                nonlocal cursor
                if current != 0xFFFFFFFF or cursor + 8 > len(values):
                    return current
                value = struct.unpack_from("<Q", values, cursor)[0]
                cursor += 8
                return value

            file_size = take(file_size)
            compressed_size = take(compressed_size)
            header_offset = take(header_offset)
            break
        position += 4 + size
    return file_size, compressed_size, header_offset


def _axml_strings(data: bytes, chunk: int, header_size: int) -> list[str]:
    """解析 AXML 字符串池（UTF-8 与 UTF-16 两种编码）。"""

    count, _style_count, flags, strings_start = struct.unpack_from(
        "<IIII", data, chunk + 8
    )
    offsets = struct.unpack_from(f"<{count}I", data, chunk + header_size)
    base = chunk + strings_start
    is_utf8 = bool(flags & 0x100)
    strings: list[str] = []
    for offset in offsets:
        position = base + offset
        if is_utf8:
            # 先是字符数、再是字节数，各占 1 或 2 字节（最高位为 1 时占 2 字节）
            position += 2 if data[position] & 0x80 else 1
            length = data[position]
            if length & 0x80:
                length = ((length & 0x7F) << 8) | data[position + 1]
                position += 2
            else:
                position += 1
            strings.append(
                data[position : position + length].decode("utf-8", "replace")
            )
        else:
            length = struct.unpack_from("<H", data, position)[0]
            position += 2
            if length & 0x8000:
                low = struct.unpack_from("<H", data, position)[0]
                length = ((length & 0x7FFF) << 16) | low
                position += 2
            strings.append(
                data[position : position + length * 2].decode("utf-16-le", "replace")
            )
    return strings


def _parse_manifest_version(axml: bytes) -> RemoteApkVersion:
    """从二进制 AndroidManifest.xml 里取 ``<manifest>`` 的包名与版本。

    属性名按资源 ID 认（``android:versionName`` 等是 framework 固定 ID）；加固过的
    安装包会把属性名字符串清空，按名字认会漏。``package`` 不是 android 属性，按名字认。

    Raises:
        _RemoteApkError: 不是 AXML、没有 ``<manifest>`` 元素或没有 ``versionName``。
    """

    if len(axml) < 8 or struct.unpack_from("<H", axml, 0)[0] != 0x0003:
        raise _RemoteApkError("清单不是二进制 XML")
    strings: list[str] = []
    resource_ids: tuple[int, ...] = ()
    position = struct.unpack_from("<H", axml, 2)[0]
    while position + 8 <= len(axml):
        chunk_type, header_size, chunk_size = struct.unpack_from("<HHI", axml, position)
        if chunk_size < 8:
            break
        if chunk_type == _AXML_STRING_POOL:
            strings = _axml_strings(axml, position, header_size)
        elif chunk_type == _AXML_RESOURCE_MAP:
            count = (chunk_size - header_size) // 4
            resource_ids = struct.unpack_from(
                f"<{count}I", axml, position + header_size
            )
        elif chunk_type == _AXML_START_ELEMENT:
            ext = position + header_size
            name_index, attr_start, attr_size, attr_count = struct.unpack_from(
                "<4xIHHH", axml, ext
            )
            if name_index < len(strings) and strings[name_index] == "manifest":
                attributes: dict[str, str | int] = {}
                for i in range(attr_count):
                    attr = ext + attr_start + i * attr_size
                    attr_name, raw_value, data_type, data = struct.unpack_from(
                        "<4xIi3xBI", axml, attr
                    )
                    key = ""
                    if attr_name < len(resource_ids):
                        key = _ANDROID_ATTR_NAMES.get(resource_ids[attr_name], "")
                    if not key and attr_name < len(strings):
                        key = strings[attr_name]
                    if raw_value >= 0 and raw_value < len(strings):
                        attributes[key] = strings[raw_value]
                    elif data_type == _AXML_TYPE_STRING and data < len(strings):
                        attributes[key] = strings[data]
                    else:
                        attributes[key] = data
                version_name = attributes.get("versionName")
                if not isinstance(version_name, str) or not version_name:
                    raise _RemoteApkError("清单里没有 versionName")
                version_code = attributes.get("versionCode")
                if isinstance(version_code, str):
                    version_code = int(version_code) if version_code.isdigit() else None
                return RemoteApkVersion(
                    package=str(attributes.get("package") or ""),
                    version_name=version_name,
                    version_code=version_code,
                )
        position += chunk_size
    raise _RemoteApkError("清单里没有 <manifest> 元素")


async def _read_remote_manifest(client: httpx.AsyncClient, url: str) -> bytes:
    """只读目录尾、中央目录与清单这一个条目，把远端安装包里的清单取出来。"""

    total = await _read_total_size(client, url)
    tail_start = max(0, total - _ZIP_EOCD_MAX_TAIL)
    tail = await _read_range(client, url, tail_start, total - 1)
    located = _find_central_directory(tail)
    if located is None:
        record_offset = _find_zip64_record_offset(tail)
        record = await _read_range(client, url, record_offset, record_offset + 55)
        if record[:4] != _ZIP64_EOCD_SIGNATURE:
            raise _RemoteApkError("ZIP64 目录尾记录签名不对")
        cd_size, cd_offset = struct.unpack_from("<QQ", record, 40)
    else:
        cd_offset, cd_size = located
    if cd_size <= 0 or cd_size > _CENTRAL_DIRECTORY_MAX_BYTES:
        raise _RemoteApkError(f"中央目录大小异常（{cd_size} 字节）")
    if cd_offset >= tail_start and cd_offset + cd_size <= total:
        # 中央目录已经在读到的尾巴里，不必再请求一次
        central_directory = tail[
            cd_offset - tail_start : cd_offset - tail_start + cd_size
        ]
    else:
        central_directory = await _read_range(
            client, url, cd_offset, cd_offset + cd_size - 1
        )

    header_offset, method, compressed_size, file_size = _find_manifest_entry(
        central_directory
    )
    if max(compressed_size, file_size) > _MANIFEST_MAX_BYTES:
        raise _RemoteApkError(f"清单体积异常（{file_size} 字节）")
    local_header = await _read_range(client, url, header_offset, header_offset + 29)
    if local_header[:4] != _ZIP_LOCAL_SIGNATURE:
        raise _RemoteApkError("清单本地头签名不对")
    name_length, extra_length = struct.unpack_from("<HH", local_header, 26)
    data_start = header_offset + 30 + name_length + extra_length
    payload = (
        await _read_range(client, url, data_start, data_start + compressed_size - 1)
        if compressed_size
        else b""
    )

    if method == 0:
        manifest = payload
    elif method == 8:
        manifest = zlib.decompressobj(-zlib.MAX_WBITS).decompress(
            payload, _MANIFEST_MAX_BYTES
        )
    else:
        raise _RemoteApkError(f"清单压缩方式不支持（{method}）")
    if len(manifest) != file_size:
        raise _RemoteApkError("清单解压后长度与目录记录不符")
    return manifest


async def fetch_remote_apk_version(
    url: str, *, timeout: float = 60.0
) -> RemoteApkVersion | None:
    """不下载整包，只按 HTTP Range 读远端安装包清单里的版本号。

    安装包是 ZIP：读文件末尾的目录尾、中央目录，再只读 ``AndroidManifest.xml``
    这一个条目（实测 2 GB 的安装包总共请求 6 次、约 0.7 MB）。要求下载地址支持
    Range（按 206 返回）；不支持时直接放弃，不会退回整包下载。

    Args:
        url: 安装包直链。重定向会跟随。
        timeout: 整个读取过程的总时长上限（秒）。

    Returns:
        RemoteApkVersion | None: 读到的包名与版本；任何原因读不出来（网络、服务器
        不支持 Range、格式不对、超时）都返回 ``None``，由调用方按"拿不到版本、跳过
        检查"处理。取消（``CancelledError``）照常向上传。
    """

    try:
        async with asyncio.timeout(timeout):
            async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                manifest = await _read_remote_manifest(client, url)
        version = _parse_manifest_version(manifest)
    except TimeoutError:
        logger.warning(f"读取远端安装包版本超时（{timeout:.0f} 秒）: {url}")
        return None
    except Exception as e:
        logger.warning(f"读取远端安装包版本失败: {e}")
        return None

    logger.info(
        f"远端安装包 {version.package} 版本: {version.version_name}"
        f"（versionCode={version.version_code}）"
    )
    return version


async def download_apk(
    url: str,
    target_path: Path,
    progress: Callable[[str], Awaitable[None]] | None = None,
    *,
    timeout: float = 3600.0,
) -> Path:
    """下载安装包。

    Args:
        url: 安装包下载入口（允许重定向到真实下载地址）。
        target_path: 安装包落盘路径。
        progress: 进度回调，用于向前端播报下载进度。
        timeout: 下载总时长上限（秒）。安装包体积不小，不能信任用户的网络；
            ``httpx`` 自身的单次读写超时仅在网络停滞时兜底，不限制总时长。

    Returns:
        Path: 下载完成的安装包路径。

    Raises:
        RuntimeError: 下载失败、下载超时，或下载内容体积明显小于安装包
            （通常是拿到了跳转页）。
    """

    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_name(f"{target_path.name}.downloading")
    temp_path.unlink(missing_ok=True)

    try:
        async with asyncio.timeout(timeout):
            async with httpx.AsyncClient(follow_redirects=True) as client:
                async with client.stream("GET", url, timeout=60.0) as response:
                    response.raise_for_status()
                    total = int(response.headers.get("content-length", 0) or 0)

                    if (
                        total
                        and shutil.disk_usage(target_path.parent).free < total * 1.2
                    ):
                        raise RuntimeError(
                            f"磁盘剩余空间不足以下载安装包（需要约 {total / 1024**3:.1f} GB）"
                        )

                    downloaded = 0
                    next_report = 0
                    async with aiofiles.open(temp_path, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):
                            if not chunk:
                                continue
                            await f.write(chunk)
                            downloaded += len(chunk)

                            if progress is not None and downloaded >= next_report:
                                next_report = downloaded + 50 * 1024 * 1024
                                if total:
                                    await progress(
                                        f"正在下载游戏安装包 "
                                        f"{downloaded / 1024**3:.2f}/"
                                        f"{total / 1024**3:.2f} GB"
                                    )
                                else:
                                    await progress(
                                        f"正在下载游戏安装包 {downloaded / 1024**3:.2f} GB"
                                    )

            if temp_path.stat().st_size < APK_MIN_BYTES:
                raise RuntimeError(
                    f"下载内容体积异常（{temp_path.stat().st_size} 字节），可能未取到真实安装包"
                )

            target_path.unlink(missing_ok=True)
            temp_path.replace(target_path)
            logger.success(f"游戏安装包下载完成: {target_path}")
            return target_path

    except TimeoutError:
        # asyncio.timeout 在总时长耗尽时抛出内置 TimeoutError；
        # httpx 自身的单次操作超时是 httpx.TimeoutException，不会被这里误捕
        temp_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"下载安装包超时（超过 {timeout / 60:.0f} 分钟），请检查网络后重试"
        ) from None
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


async def install_apk(
    adb_path: Path | None,
    adb_address: str,
    apk_path: Path,
    timeout: float,
) -> None:
    """通过 adb 安装安装包，保留应用数据。

    Raises:
        RuntimeError: 安装未成功。
    """

    logger.info(f"开始安装游戏安装包: {apk_path}")
    returncode, output = await _run_adb(
        adb_path,
        adb_address,
        "install",
        "-r",
        str(apk_path),
        timeout=timeout,
    )
    if returncode != 0 or "Success" not in output:
        raise RuntimeError(f"安装失败: returncode={returncode}, output={output}")

    logger.success("游戏安装包安装成功")
