#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""BetterGI 本体更新：MAS 下载校验，官方 Kachina 安装器负责安装及保留 User。

上游没有关闭启动版本查询的开关；运行期仅临时使用其「忽略版本提示」设置，
不修改脚本仓库更新。官方安装器失败/取消后保留安装标记，禁止把半安装当旧版运行。
"""

import asyncio
import hashlib
import re
import tempfile
import zipfile
from contextlib import suppress
from copy import deepcopy
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx
import psutil
from packaging.version import Version

from app.core import Config
from app.core.script_update import download_script_package
from app.models.config import BetterGIConfig
from app.services import script_install
from app.services.common.update.transport import (
    DownloadProgress,
    request_mirror_resource,
)
from app.utils import io as _utils_io

REPOSITORY = "babalae/better-genshin-impact"
NOTICE_KEY = "notShowNewVersionNoticeEndVersion"
# BetterGI 使用严格 SemVer 比较，不能填通配符或空的版本号。
IGNORED_VERSION = "2147483647.0.0"


def assert_idle(root: Path) -> None:
    for process in psutil.process_iter(["exe", "name"]):
        try:
            executable = process.info["exe"]
            name = str(process.info.get("name", "")).casefold()
            if not executable and (
                name in {"bettergi.exe", "bettergi.update.exe"}
                or name.startswith("bettergi.install.")
            ):
                raise script_install.InstallUnsafeError(
                    "无法确认 BetterGI 更新器已退出，请以管理员身份重试"
                )
            if executable and any(
                Path(executable).resolve().is_relative_to(path.resolve())
                for path in (root, script_install.workspace(root))
            ):
                raise script_install.InstallUnsafeError(
                    "BetterGI 或其更新器仍在运行，请退出后重试"
                )
        except psutil.NoSuchProcess:
            continue
        except psutil.AccessDenied as error:
            raise script_install.InstallUnsafeError(
                "无法确认 BetterGI 进程已退出，请以管理员身份重试"
            ) from error


def read_version(root: Path) -> Version:
    """读取官方程序版本资源，不以 MAS 的上次版本记录代替实际安装版本。"""
    import win32api

    path = str(root / "BetterGI.exe")
    translations = win32api.GetFileVersionInfo(path, r"\VarFileInfo\Translation")
    language, codepage = translations[0]
    value = win32api.GetFileVersionInfo(
        path, f"\\StringFileInfo\\{language:04x}{codepage:04x}\\ProductVersion"
    )
    return Version(value.split("+", 1)[0])


async def confirm_current_install(root: Path) -> None:
    await asyncio.to_thread(assert_idle, root)
    if (script_install.workspace(root) / "bgi-install.json").exists():
        raise script_install.InstallUnsafeError(
            "BetterGI 上次安装尚未确认，请开启更新托管重试或使用官方安装器修复"
        )
    try:
        await asyncio.to_thread(read_version, root)
        arch = await asyncio.to_thread(
            script_install.read_pe_architecture, root / "BetterGI.exe"
        )
        if arch != "x86_64":
            raise ValueError("不支持的安装架构")
    except Exception as error:
        raise script_install.InstallUnsafeError(
            "BetterGI 当前安装不可识别，请使用官方安装器修复"
        ) from error


async def request_release(channel: str) -> dict:
    path = "releases/latest" if channel == "stable" else "releases?per_page=100"
    async with httpx.AsyncClient(
        proxy=Config.proxy, timeout=15, follow_redirects=True
    ) as client:
        response = await client.get(f"https://api.github.com/repos/{REPOSITORY}/{path}")
        response.raise_for_status()
        payload = response.json()
    releases = []
    for release in payload if isinstance(payload, list) else [payload]:
        if not isinstance(release, dict) or release.get("draft"):
            continue
        try:
            version = Version(release["tag_name"])
        except (KeyError, ValueError, TypeError):
            continue
        if channel == "stable" and (release.get("prerelease") or version.is_prerelease):
            continue
        releases.append((version, release))
    if not releases:
        raise ValueError("未找到可识别的 BetterGI 官方发行版")
    return max(releases, key=lambda item: item[0])[1]


def select_installer(release: dict) -> tuple[Version, str, str, int, str]:
    tag = release["tag_name"]
    version = Version(tag)
    name = f"BetterGI.Install.{tag.removeprefix('v')}.exe"
    for asset in release.get("assets", []):
        if asset.get("name") != name:
            continue
        digest = str(asset.get("digest", ""))
        size = asset.get("size")
        if not digest.startswith("sha256:") or len(digest[7:]) != 64:
            raise ValueError("BetterGI 官方安装包缺少可信 SHA256")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise ValueError("BetterGI 官方安装包大小无效")
        url = f"https://github.com/{REPOSITORY}/releases/download/{quote(tag, safe='')}/{quote(name, safe='')}"
        return version, name, url, size, digest[7:]
    raise ValueError("BetterGI 官方发行版没有完整安装器")


def verify_installer(
    path: Path, size: int, digest: str, *, executable: bool = True
) -> None:
    if path.stat().st_size != size:
        raise ValueError("BetterGI 安装包大小不符")
    with path.open("rb") as handle:
        if hashlib.file_digest(handle, "sha256").hexdigest() != digest.lower():
            raise ValueError("BetterGI 安装包 SHA256 不符")
    if executable and script_install.read_pe_architecture(path) != "x86_64":
        raise ValueError("BetterGI 安装器架构不符")


def unpack_mirror_installer(
    archive: Path, destination: Path, name: str, size: int
) -> None:
    # BGI 不带 os/arch 的 Mirror 资源是安装器 ZIP；不执行其中的其他文件，
    # 上游会给 Mirror 包内安装器追加 VC 运行库，因此不能用 GitHub 的哈希校验它。
    with zipfile.ZipFile(archive) as package:
        if package.namelist() != [name]:
            raise ValueError("Mirror 酱包不是预期的 BetterGI 完整安装器")
        info = package.getinfo(name)
        if not size <= info.file_size <= size + 256 * 1024**2 or info.flag_bits & 1:
            raise ValueError("Mirror 酱安装器大小无效或已加密")
        with package.open(info) as source, destination.open("xb") as output:
            remaining = info.file_size
            while chunk := source.read(min(1024 * 1024, remaining + 1)):
                remaining -= len(chunk)
                if remaining < 0:
                    raise ValueError("Mirror 酱安装器展开大小异常")
                output.write(chunk)


async def run_installer(installer: Path, root: Path) -> None:
    # Kachina -S 静默安装，-D 显式指定现有安装目录；不用 -O，避免离线包再联网取包。
    process = await asyncio.create_subprocess_exec(
        str(installer), "-S", "-D", str(root.resolve()), cwd=str(installer.parent)
    )
    waiter = asyncio.create_task(process.wait())
    try:
        code = await asyncio.wait_for(asyncio.shield(waiter), timeout=30 * 60)
    except asyncio.CancelledError:
        # 不强杀正在写盘的官方安装器，等待退出后才释放目录锁；取消仍阻断启动。
        while not waiter.done():
            with suppress(asyncio.CancelledError):
                await asyncio.shield(waiter)
        raise
    except TimeoutError as error:
        raise script_install.InstallUnsafeError(
            "BetterGI 官方安装器尚未退出，已保留安装现场，请手动确认"
        ) from error
    if code != 0:
        raise script_install.InstallUnsafeError(
            "BetterGI 官方安装器失败，已保留安装标记，请重试更新或手动修复"
        )


async def update_before_run(
    root: Path, config: BetterGIConfig, *, progress: DownloadProgress | None = None
) -> str:
    await asyncio.to_thread(assert_idle, root)
    current = await asyncio.to_thread(read_version, root)
    if script_install.read_pe_architecture(root / "BetterGI.exe") != "x86_64":
        raise script_install.InstallUnsafeError("BetterGI 当前安装架构不支持自动更新")
    target, name, url, size, digest = select_installer(
        await request_release(config.Update.Channel)
    )
    directory = script_install.workspace(root)
    marker = directory / "bgi-install.json"
    if target <= current and not marker.exists():
        return f"BetterGI 当前版本 {current} 无需更新"
    if target < current:
        raise script_install.InstallUnsafeError(
            "BetterGI 上次安装未完成且高于所选通道，请切换通道或手动修复，不会自动降级"
        )
    directory.mkdir(parents=True, exist_ok=True)
    cache = Path(tempfile.mkdtemp(dir=directory, prefix="download-"))
    installer = cache / name
    cdk = (
        config.Update.MirrorChyanCDK.strip()
        or Config.setting.Update.MirrorChyanCDK.strip()
    )
    source = "GitHub"
    destination = installer
    if cdk:
        payload = await request_mirror_resource(
            "BGI",
            params={
                "cdk": cdk,
                "channel": "stable" if config.Update.Channel == "stable" else "alpha",
            },
            proxy=Config.proxy,
        )
        data = payload.get("data", {})
        if (
            data.get("update_type") != "full"
            or Version(str(data.get("version_name", ""))) != target
        ):
            raise ValueError("Mirror 酱安装包版本与官方发行版不一致")
        url = str(data.get("url", ""))
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError("Mirror 酱下载地址无效")
        source = "MirrorChyan"
        destination = cache / "installer.zip"
        # Mirror 发行流程追加运行库，包体与 GitHub 不同。只接受 API 的可信摘要，
        # 不把下载后自算的哈希冒充来源校验。
        mirror_digest = str(data.get("sha256", ""))
        if not re.fullmatch(r"[0-9a-fA-F]{64}", mirror_digest):
            raise ValueError("Mirror 酱 BetterGI 安装包缺少可信 SHA256")
        mirror_size = data.get("filesize")
        if (
            not isinstance(mirror_size, int)
            or isinstance(mirror_size, bool)
            or not 0 < mirror_size <= 4 * 1024**3
        ):
            raise ValueError("Mirror 酱 BetterGI 安装包大小无效")
    # 失败/取消时保留独立下载目标，不删除可能仍由 FluxDown 写入的文件。
    await download_script_package(
        url,
        destination,
        source=source,
        timeout=30 * 60,
        proxy=Config.proxy,
        progress=progress,
    )
    if source == "MirrorChyan":
        await asyncio.to_thread(
            verify_installer, destination, mirror_size, mirror_digest, executable=False
        )
        await asyncio.to_thread(
            unpack_mirror_installer, destination, installer, name, size
        )
        if script_install.read_pe_architecture(installer) != "x86_64":
            raise ValueError("BetterGI 安装器架构不符")
    else:
        await asyncio.to_thread(verify_installer, installer, size, digest)
    await asyncio.to_thread(assert_idle, root)
    _utils_io.write_file(marker, {"target": str(target)})
    await run_installer(installer, root)
    await asyncio.to_thread(assert_idle, root)
    if await asyncio.to_thread(read_version, root) != target:
        raise script_install.InstallUnsafeError(
            "BetterGI 安装后版本未确认，请使用官方安装器修复"
        )
    marker.unlink()
    # 仅在确认安装器和全部子进程退出后回收；失败保留现场。
    import shutil

    shutil.rmtree(cache)
    return f"BetterGI 已更新至 {target}"


def recover_update_notice(root: Path) -> None:
    journal = script_install.workspace(root) / "bgi-notice.json"
    if journal.exists():
        assert_idle(root)
        try:
            _utils_io.restore_config_injection_journal(
                journal,
                root / "User/config.json",
                identity={"script_id": "BetterGI", "root": str(root.resolve())},
            )
        except Exception as error:
            raise script_install.InstallUnsafeError(
                "BetterGI 更新提示设置恢复失败，已保留恢复记录"
            ) from error


def suppress_update_notice(root: Path) -> None:
    path = root / "User/config.json"
    original = _utils_io.read_dict_file(path)
    injected = deepcopy(original)
    injected[NOTICE_KEY] = IGNORED_VERSION
    directory = script_install.workspace(root)
    directory.mkdir(parents=True, exist_ok=True)
    journal = directory / "bgi-notice.json"
    if journal.exists():
        raise script_install.InstallUnsafeError(
            "BetterGI 上次运行的更新提示设置尚未恢复"
        )
    _utils_io.write_file(
        journal,
        {
            "script_id": "BetterGI",
            "root": str(root.resolve()),
            "original": original,
            "injected": injected,
        },
    )
    _utils_io.write_file(path, injected)
