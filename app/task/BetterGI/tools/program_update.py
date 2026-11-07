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
from app.utils.common.process.runner import wait_for_process_cleanup

REPOSITORY = "babalae/better-genshin-impact"
NOTICE_KEY = "notShowNewVersionNoticeEndVersion"
# BetterGI 使用严格 SemVer 比较，不能填通配符或空的版本号。
IGNORED_VERSION = "2147483647.0.0"
_INSTALLER_CLEANUP_SECONDS = 5


def assert_idle(root: Path) -> None:
    script_install.assert_no_pending_process(root)
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


async def confirm_safe_game_update(root: Path) -> None:
    """游戏客户端更新不启动 BetterGI，但必须排除本体安装仍在进行。"""
    await asyncio.to_thread(assert_no_active_installer, root)


def assert_no_active_installer(root: Path) -> None:
    workspace = script_install.workspace(root)
    if (workspace / "bgi-install.json").exists():
        raise script_install.InstallUnsafeError(
            "BetterGI 上次本体安装未确认，禁止在安装过程中执行游戏更新"
        )
    for process in psutil.process_iter(["exe", "name"]):
        try:
            executable = process.info.get("exe")
            name = str(process.info.get("name") or "").casefold()
            if executable and not name:
                name = Path(executable).name.casefold()
            if not (
                name.startswith("bettergi.install.") or name == "bettergi.update.exe"
            ):
                continue
            if executable and not any(
                Path(executable).resolve().is_relative_to(path.resolve())
                for path in (workspace, root)
            ):
                continue
            raise script_install.InstallUnsafeError(
                "BetterGI 本体安装器尚未退出，请先完成安装"
            )
        except psutil.NoSuchProcess:
            continue
        except psutil.AccessDenied as error:
            raise script_install.InstallUnsafeError(
                "无法确认 BetterGI 安装器已退出，请以管理员身份重试"
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
        prerelease = bool(release.get("prerelease") or version.is_prerelease)
        if channel == "stable" and prerelease:
            continue
        if channel != "stable" and not prerelease:
            continue
        releases.append((version, release))
    if not releases:
        raise ValueError(
            "未找到带官方安装器的 BetterGI 对应通道 Release；"
            "公测构建可能仅发布于 Actions，不会回退使用正式版"
        )
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
    archive: Path, destination: Path, name: str, size: int | None
) -> None:
    # BGI 不带 os/arch 的 Mirror 资源是安装器 ZIP；不执行其中的其他文件，
    # 上游会给 Mirror 包内安装器追加 VC 运行库，因此不能用 GitHub 的哈希校验它。
    with zipfile.ZipFile(archive) as package:
        # 上游 7z 直接归档 ./downloads/BetterGI_Install/<exe>，
        # ZIP 可带目录前缀；限定为官方已知布局且仅包含一个可执行文件。
        allowed = {name, f"downloads/BetterGI_Install/{name}"}
        files = [member for member in package.infolist() if not member.is_dir()]
        directories = [
            member.filename for member in package.infolist() if member.is_dir()
        ]
        if (
            len(files) != 1
            or files[0].filename not in allowed
            or any(
                directory not in {"downloads/", "downloads/BetterGI_Install/"}
                for directory in directories
            )
        ):
            raise ValueError("Mirror 酱包不是预期的 BetterGI 完整安装器")
        info = files[0]
        minimum = size if size is not None else 1
        maximum = (
            size + 256 * 1024**2
            if size is not None
            else min(4 * 1024**3, archive.stat().st_size + 512 * 1024**2)
        )
        if not minimum <= info.file_size <= maximum or info.flag_bits & 1:
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
    except (asyncio.CancelledError, TimeoutError) as error:
        # 不强杀写盘中的官方安装器；任务结束后，目录锁由退出等待者接管。
        try:
            await wait_for_process_cleanup(waiter, timeout=_INSTALLER_CLEANUP_SECONDS)
        except TimeoutError as cleanup_error:
            script_install.defer_installation_release(root, waiter)
            raise script_install.InstallUnsafeError(
                "BetterGI 安装器尚未退出，任务已停止等待，安装目录将保持占用直至进程结束"
            ) from cleanup_error
        if isinstance(error, TimeoutError):
            raise script_install.InstallUnsafeError(
                "BetterGI 官方安装器超时时尚未退出，现已结束；已保留安装现场，请手动确认"
            ) from error
        raise
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
    cdk = (
        config.Update.MirrorChyanCDK.strip()
        or Config.setting.Update.MirrorChyanCDK.strip()
    )
    # 公测构建由上游上传到 Mirror，但不一定创建 GitHub prerelease。
    # 优先使用 Mirror 自己的可信版本和包校验信息，不能依赖 Release 推断。
    mirror_data = None
    if cdk and config.Update.Channel != "stable":
        payload = await request_mirror_resource(
            "BGI",
            params={"cdk": cdk, "channel": "alpha"},
            proxy=Config.proxy,
        )
        mirror_data = payload.get("data", {})
        mirror_version = str(mirror_data.get("version_name", ""))
        if not re.fullmatch(
            r"v?\d+\.\d+\.\d+-(?:alpha|beta|rc)\.\d+",
            mirror_version,
            flags=re.IGNORECASE,
        ):
            raise ValueError("Mirror 酱 BetterGI 公测版本格式无效")
        target = Version(mirror_version)
        name = f"BetterGI.Install.{mirror_version.removeprefix('v')}.exe"
        size = None
        digest = ""
        url = ""
    else:
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
    source = "GitHub"
    destination = installer
    if cdk:
        if mirror_data is None:
            payload = await request_mirror_resource(
                "BGI",
                params={"cdk": cdk, "channel": "stable"},
                proxy=Config.proxy,
            )
            mirror_data = payload.get("data", {})
        data = mirror_data
        if (
            data.get("update_type") != "full"
            or Version(str(data.get("version_name", ""))) != target
        ):
            raise ValueError("Mirror 酱安装包版本与所选通道版本不一致")
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
        # 上游为公测发布的带运行库安装器未必有 GitHub Release，
        # 其整包完整性只能由 Mirror API 的 SHA256 和大小共同校验。
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
