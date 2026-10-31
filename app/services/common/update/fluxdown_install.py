#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.
#
#   Contact: DLmaster_361@163.com

"""FluxDown CLI / Server 发布包的下载与便携安装。

FluxDown 的下载能力由两个发布包共同提供：CLI 包给出 ``fluxdown.exe``，
Server 包给出 ``fluxdown-agent.exe`` 与 ``fluxdownd.exe``，三者必须位于同一
目录才能启用断点续传。这里负责解析官方最新 Release、按镜像下载两个 zip、
校验 sha256、安全解压并原子替换到 MAS 用户数据目录，最后把路径写回
``Update.FluxdownPath``。

安装包本身一律用内置 httpx 下载，**不经过 FluxDown 自身**：否则首次安装或
CLI 损坏时会形成鸡生蛋循环。
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import platform
import re
import shutil
import stat
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterable

import httpx

from app.config import config_manager
from app.core import Config
from app.services.common.update.transport import download_file
from app.utils import fluxdown_cli as _fluxdown_cli
from app.utils import get_logger, update_native

logger = get_logger("FluxDown")

_REPOSITORY = "zerx-lab/FluxDown"
_GITHUB_API_LATEST = f"https://api.github.com/repos/{_REPOSITORY}/releases/latest"
_GITHUB_RELEASES = f"https://github.com/{_REPOSITORY}/releases"
RELEASE_PAGE = f"{_GITHUB_RELEASES}/latest"

_ASSET_CLI = "FluxDown-CLI-{version}-windows-{arch}.zip"
_ASSET_SERVER = "FluxDown-Server-{version}-windows-{arch}.zip"

# 大陆可用的下载源。官方镜像在大陆会 302 到 dl-cn，其余地区回退 GitHub；
# gh-proxy / ghfast 直接前缀拼接 GitHub 地址。清单与 MaaFW 模块、前端
# mirrorService.ts 同源，改动时需要同步。
_OFFICIAL_MIRROR = (
    "https://fluxdown.zerx.dev/api/download/{filename}?tag={tag}&source=auto"
)
_GHPROXY = "https://gh-proxy.com/"
_GHFAST = "https://ghfast.top/"

SUPPORTED_MIRRORS: tuple[str, ...] = (
    "auto",
    "official",
    "ghproxy",
    "ghfast",
    "github",
)

_REQUIRED_BINARIES = ("fluxdown.exe", "fluxdown-agent.exe", "fluxdownd.exe")
_RELEASE_CACHE_TTL = 600.0
_MAX_ARCHIVE_BYTES = 256 * 1024**2
_MAX_MEMBER_BYTES = 512 * 1024**2
_MAX_EXTRACTED_BYTES = 1024**3
_MAX_MEMBERS = 4096


@dataclass(frozen=True)
class FluxdownRelease:
    """一次最新 Release 的解析结果。"""

    version: str
    tag: str
    arch: str
    cli_name: str
    server_name: str
    cli_url: str
    server_url: str
    cli_sha256: str | None
    server_sha256: str | None


_release_cache: tuple[float, FluxdownRelease] | None = None
_install_lock = asyncio.Lock()


def _install_dir() -> Path:
    """安装目录：MAS 用户数据目录，跟随 MAS 本体而不是 repo/ 资源目录。"""
    return Config.data_path / "fluxdown-cli"


def _arch() -> str:
    machine = platform.machine().lower()
    return "arm64" if "arm" in machine or "aarch" in machine else "x64"


def _asset_sha256(asset: dict[str, Any]) -> str | None:
    digest = asset.get("digest")
    if isinstance(digest, str) and digest.lower().startswith("sha256:"):
        value = digest.split(":", 1)[1].strip().lower()
        return value if re.fullmatch(r"[0-9a-f]{64}", value) else None
    return None


async def fetch_latest_release(*, proxy: httpx.Proxy | None = None) -> FluxdownRelease:
    """解析 FluxDown 最新 Release（10 分钟缓存，供设置页展示直链与安装共用）。"""

    global _release_cache
    cached = _release_cache
    if cached and time.monotonic() - cached[0] < _RELEASE_CACHE_TTL:
        return cached[1]

    payload = await _fetch_release_payload(proxy)
    release = _parse_release(payload)
    _release_cache = (time.monotonic(), release)
    return release


async def _fetch_release_payload(proxy: httpx.Proxy | None) -> dict[str, Any]:
    """摘要只信任 GitHub HTTPS API；下载镜像不能为自身软件包背书。"""
    try:
        async with httpx.AsyncClient(
            proxy=proxy, follow_redirects=False, timeout=20
        ) as client:
            response = await client.get(
                _GITHUB_API_LATEST,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "AUTO-MAS",
                },
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise RuntimeError("Release 响应不是对象")
            return payload
    except Exception as error:
        raise RuntimeError(
            f"无法从 GitHub 获取可信 FluxDown 版本信息: {error}"
        ) from error


def _parse_release(payload: dict[str, Any]) -> FluxdownRelease:
    tag = str(payload.get("tag_name") or "").strip()
    version = tag.lstrip("vV")
    if not re.fullmatch(r"[vV]?\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?", tag):
        raise RuntimeError("FluxDown Release 信息缺少版本号")

    arch = _arch()
    cli_name = _ASSET_CLI.format(version=version, arch=arch)
    server_name = _ASSET_SERVER.format(version=version, arch=arch)
    assets = {
        str(asset.get("name") or ""): asset
        for asset in payload.get("assets") or []
        if isinstance(asset, dict)
    }
    cli_asset = assets.get(cli_name)
    server_asset = assets.get(server_name)
    if cli_asset is None or server_asset is None:
        raise RuntimeError(f"最新 Release {tag} 缺少 Windows {arch} 的 CLI/Server 资产")

    def url_of(name: str, asset: dict[str, Any]) -> str:
        browser = asset.get("browser_download_url")
        if isinstance(browser, str) and browser:
            return browser
        return f"{_GITHUB_RELEASES}/download/{tag}/{name}"

    return FluxdownRelease(
        version=version,
        tag=tag,
        arch=arch,
        cli_name=cli_name,
        server_name=server_name,
        cli_url=url_of(cli_name, cli_asset),
        server_url=url_of(server_name, server_asset),
        cli_sha256=_asset_sha256(cli_asset),
        server_sha256=_asset_sha256(server_asset),
    )


def _download_urls(name: str, tag: str, mirror: str) -> list[str]:
    """按镜像生成候选下载地址（顺序即尝试顺序）。"""

    github = f"{_GITHUB_RELEASES}/download/{tag}/{name}"
    official = _OFFICIAL_MIRROR.format(filename=name, tag=tag)
    if mirror == "auto":
        return [official, f"{_GHPROXY}{github}", f"{_GHFAST}{github}", github]
    if mirror == "official":
        return [official]
    if mirror == "ghproxy":
        return [f"{_GHPROXY}{github}"]
    if mirror == "ghfast":
        return [f"{_GHFAST}{github}"]
    return [github]


def _mirror_label(url: str) -> str:
    host = httpx.URL(url).host or url
    return host


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def _download_asset(
    release: FluxdownRelease,
    name: str,
    sha256: str | None,
    mirror: str,
    work: Path,
    proxy: httpx.Proxy | None,
) -> int:
    """按镜像顺序下载单个资产并校验 sha256，全部失败时抛出汇总错误。"""

    if not sha256 or not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise RuntimeError(f"{name} 缺少可信的 SHA-256 摘要，拒绝安装")
    errors: list[str] = []
    destination = work / name
    for url in _download_urls(name, release.tag, mirror):
        try:
            await download_file(
                url, destination, timeout=60, proxy=proxy, max_bytes=_MAX_ARCHIVE_BYTES
            )
            actual = await asyncio.to_thread(_sha256_of, destination)
            if actual != sha256:
                raise RuntimeError("sha256 校验失败")
            logger.info(f"已下载 {name}: {url}")
            return destination.stat().st_size
        except Exception as error:  # noqa: BLE001 - 换下一个镜像
            destination.unlink(missing_ok=True)
            errors.append(f"{_mirror_label(url)}: {error}")
            logger.warning(f"下载 {name} 失败({url}): {error}")
    detail = "；".join(errors)
    raise RuntimeError(f"下载 {name} 失败（{detail}），可更换镜像后重试")


def _safe_parts(name: str) -> tuple[str, ...]:
    """zip 成员路径 → 安全的分段元组；绝对路径与 .. 直接拒绝。"""

    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or PureWindowsPath(name).anchor:
        raise RuntimeError(f"安装包包含非法路径: {name}")
    parts = tuple(part for part in path.parts if part not in ("", "."))
    if any(
        part == ".."
        or ":" in part
        or part.endswith((".", " "))
        or PureWindowsPath(part).is_reserved()
        for part in parts
    ):
        raise RuntimeError(f"安装包包含非法路径: {name}")
    return parts


def _common_root(names: Iterable[tuple[str, ...]]) -> str | None:
    """所有成员都在同一个顶层目录下时返回该目录名（发布包都带一层目录）。"""

    values = list(names)
    firsts = {parts[0] for parts in values if len(parts) > 1}
    if len(firsts) == 1 and all(len(parts) > 1 for parts in values):
        return firsts.pop()
    return None


def _extract_zip(archive: Path, target: Path) -> None:
    """安全解压到 target，剥掉发布包唯一的顶层目录。"""

    with zipfile.ZipFile(archive) as bundle:
        entries: list[tuple[zipfile.ZipInfo, tuple[str, ...]]] = []
        infos = bundle.infolist()
        if (
            len(infos) > _MAX_MEMBERS
            or sum(i.file_size for i in infos) > _MAX_EXTRACTED_BYTES
        ):
            raise RuntimeError("安装包解压大小或文件数量超过上限")
        for info in infos:
            if info.file_size > _MAX_MEMBER_BYTES or stat.S_ISLNK(
                info.external_attr >> 16
            ):
                raise RuntimeError("安装包包含过大文件或符号链接")
            parts = _safe_parts(info.filename)
            if parts:
                entries.append((info, parts))
        strip_root = _common_root(parts for _, parts in entries)
        for info, parts in entries:
            relative = parts[1:] if strip_root and len(parts) > 1 else parts
            if not relative:
                continue
            output = target.joinpath(*relative)
            if not output.resolve().is_relative_to(target.resolve()):
                raise RuntimeError(f"安装包路径越界: {info.filename}")
            if info.is_dir():
                output.mkdir(parents=True, exist_ok=True)
                continue
            output.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(info) as source, open(output, "wb") as sink:
                shutil.copyfileobj(source, sink)


def _install_from(extracted: Path) -> Path:
    """把解压结果整理成可用的安装目录并原子替换旧版本。"""

    target = _install_dir()
    old_dir = target.with_name(target.name + ".old")
    # 上次回滚也失败时，先恢复唯一备份，绝不在重试中删掉它。
    if old_dir.exists() and not target.exists():
        os.replace(old_dir, target)
    new_dir = target.with_name(target.name + ".new")
    shutil.rmtree(new_dir, ignore_errors=True)
    shutil.copytree(extracted, new_dir)

    for name in _REQUIRED_BINARIES:
        if (new_dir / name).is_file():
            continue
        matches = list(new_dir.rglob(name))
        if not matches:
            raise RuntimeError(f"安装包缺少 {name}")
        shutil.copy2(matches[0], new_dir / name)

    # 便携标记：CLI 与 server 都只认 exe 同目录的这个文件，缺了会写进用户本体
    (new_dir / "portable").touch()

    portable_data = target / "portable_data"
    if portable_data.exists():
        shutil.rmtree(new_dir / "portable_data", ignore_errors=True)
        shutil.copytree(portable_data, new_dir / "portable_data")
    shutil.rmtree(old_dir, ignore_errors=True)
    moved_old = False
    try:
        if target.exists():
            os.replace(target, old_dir)
            moved_old = True
        os.replace(new_dir, target)
    except OSError as error:
        if moved_old:
            try:
                os.replace(old_dir, target)
            except OSError as rollback_error:
                raise RuntimeError(
                    f"替换与恢复 FluxDown 均失败，旧版本保留在 {old_dir}: {rollback_error}"
                ) from error
        raise RuntimeError(
            f"替换 FluxDown 安装目录失败: {error}；请先停止正在进行的更新下载"
        ) from error
    shutil.rmtree(old_dir, ignore_errors=True)
    return target


async def install_fluxdown(
    mirror: str = "auto", *, proxy: httpx.Proxy | None = None
) -> dict[str, Any]:
    """下载并安装 FluxDown CLI + Server，返回版本、路径与两个包的大小。"""

    if not update_native.supports_fluxdown_install:
        raise RuntimeError("代为下载 FluxDown 仅支持 Windows")
    selected = (mirror or "auto").strip().lower()
    if selected not in SUPPORTED_MIRRORS:
        raise RuntimeError(f"未知的下载镜像: {mirror}")
    if _install_lock.locked():
        raise RuntimeError("正在安装 FluxDown，请等待当前任务完成")

    async with _install_lock:
        # to_thread 不会随请求取消而退出；等待整个安装收尾后才释放锁。
        task = asyncio.create_task(_install_locked(selected, proxy))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            if not task.cancelled():
                task.exception()
            raise


async def _install_locked(mirror: str, proxy: httpx.Proxy | None) -> dict[str, Any]:
    initial_path = Config.setting.Update.FluxdownPath
    release = await fetch_latest_release(proxy=proxy)
    if not release.cli_sha256 or not release.server_sha256:
        raise RuntimeError("CLI/Server 缺少可信的 SHA-256 摘要，拒绝安装")
    tmp_root = Config.data_path / "fluxdown_install_tmp"
    work = tmp_root / "download"
    extracted = tmp_root / "extract"
    shutil.rmtree(tmp_root, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    extracted.mkdir(parents=True, exist_ok=True)

    try:
        cli_size = await _download_asset(
            release, release.cli_name, release.cli_sha256, mirror, work, proxy
        )
        server_size = await _download_asset(
            release,
            release.server_name,
            release.server_sha256,
            mirror,
            work,
            proxy,
        )
        await asyncio.to_thread(_extract_zip, work / release.cli_name, extracted)
        await asyncio.to_thread(_extract_zip, work / release.server_name, extracted)

        # 与所有 FluxDown 下载共用占用边界；替换期间不能启动新下载。
        def replace_installation() -> Path:
            with _fluxdown_cli.fluxdown_install_guard():
                return _install_from(extracted)

        target = await asyncio.to_thread(replace_installation)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    # 配置失败不能报告全流程成功；比较与提交共用事务，保留下载期间的新选择。
    try:
        async with config_manager.transaction():
            if Config.setting.Update.FluxdownPath != initial_path:
                raise RuntimeError("安装期间路径设置已变化，已保留新选择")
            await Config.setting.update(
                type(Config.setting).model_validate(
                    {"Update": {"FluxdownPath": str(target)}}
                ),
                check_visibility=False,
            )
        await Config.flush()
    except Exception as error:
        raise RuntimeError(f"文件已安装到 {target}，但路径未保存: {error}") from error
    logger.info(f"FluxDown {release.version} 已安装到 {target}")
    return {
        "version": release.version,
        "path": str(target),
        "cli_size": cli_size,
        "server_size": server_size,
    }


__all__ = [
    "FluxdownRelease",
    "RELEASE_PAGE",
    "SUPPORTED_MIRRORS",
    "fetch_latest_release",
    "install_fluxdown",
]
