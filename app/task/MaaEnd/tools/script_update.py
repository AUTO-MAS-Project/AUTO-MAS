#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""MaaEnd 官方完整包更新。开发者确认允许直接解压，MAS 承担校验和安装。

不依赖 MXU 私有待更新文件或日志推断安装成功；版本来自 PI V2 interface，
架构来自发行程序 PE 头，安装使用通用可恢复目录切换。
"""

import asyncio
import base64
import json
import os
import tempfile
from contextlib import suppress
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx
import psutil
from packaging.version import Version

from app.core import Config
from app.core.update import download_file
from app.models.config import MaaEndConfig
from app.services import script_install
from app.services.update_transport import DownloadProgress, request_mirror_resource
from app.utils import io as _utils_io

REPOSITORY = "MaaEnd/MaaEnd"
# 官方包的 data/ 是资源目录（如 AutoDelivery/catalog.json），必须更新；
# 未在分发清单中的用户文件随安装副本保留，不按目录名误判为官方文件。
PROTECTED = frozenset({"config", "debug", "logs", "user", ".git"})


def assert_idle(root: Path) -> None:
    """覆盖 MXU、agent 和独立更新器；无法读取进程路径时不猜成空闲。"""
    for process in psutil.process_iter(["exe", "name"]):
        try:
            executable = process.info["exe"]
            if not executable and str(process.info.get("name", "")).casefold() in {
                "maaend.exe",
                "go-service.exe",
                "cpp-algo.exe",
            }:
                raise script_install.InstallUnsafeError(
                    "无法确认 MaaEnd 相关进程路径，请以管理员身份重试"
                )
            if executable and any(
                Path(executable).resolve().is_relative_to(path.resolve())
                for path in (root, script_install.workspace(root))
            ):
                raise script_install.InstallUnsafeError(
                    "MaaEnd 或其子程序仍在运行，请退出后重试"
                )
        except psutil.NoSuchProcess:
            continue
        except psutil.AccessDenied as error:
            raise script_install.InstallUnsafeError(
                "无法确认 MaaEnd 相关进程已退出，请以管理员身份重试"
            ) from error


def read_install(root: Path) -> tuple[Version, str]:
    interface = _utils_io.read_dict_file(root / "interface.json", format=".json5")
    if interface.get("name") != "MaaEnd":
        raise ValueError("安装目录不是 MaaEnd 官方项目")
    version = Version(str(interface.get("version", "")))
    if not (root / "resource").is_dir() or not (root / "agent").is_dir():
        raise ValueError("MaaEnd 程序或资源目录不完整")
    return version, script_install.read_pe_architecture(root / "MaaEnd.exe")


async def request_release(channel: str) -> dict:
    path = "releases/latest" if channel == "stable" else "releases?per_page=100"
    async with httpx.AsyncClient(
        proxy=Config.proxy, timeout=15, follow_redirects=True
    ) as client:
        response = await client.get(f"https://api.github.com/repos/{REPOSITORY}/{path}")
        response.raise_for_status()
        payload = response.json()
    candidates = payload if isinstance(payload, list) else [payload]
    releases = []
    for item in candidates:
        if not isinstance(item, dict) or item.get("draft"):
            continue
        if channel == "stable" and item.get("prerelease"):
            continue
        try:
            version = Version(item["tag_name"])
        except (ValueError, KeyError, TypeError):
            continue
        if not version.is_devrelease and not (
            channel == "stable" and version.is_prerelease
        ):
            releases.append((version, item))
    if not releases:
        raise ValueError("MaaEnd 没有可识别的官方发行版")
    return max(releases, key=lambda item: item[0])[1]


def select_package(release: dict, arch: str) -> tuple[Version, str, str, int, str]:
    tag = release["tag_name"]
    version = Version(tag)
    name = f"MaaEnd-win-{arch}-{tag}.zip"
    for asset in release.get("assets", []):
        if asset.get("name") != name:
            continue
        digest = str(asset.get("digest", ""))
        if not digest.startswith("sha256:"):
            raise ValueError("MaaEnd 官方发行包缺少 SHA256，无法自动安装")
        size = asset.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise ValueError("MaaEnd 官方发行包大小无效")
        url = f"https://github.com/{REPOSITORY}/releases/download/{quote(tag, safe='')}/{quote(name, safe='')}"
        return version, name, url, size, digest[7:]
    raise ValueError("MaaEnd 官方发行版没有当前安装架构的完整包")


async def update_before_run(
    root: Path, config: MaaEndConfig, *, progress: DownloadProgress | None = None
) -> str:
    """调用方持安装锁；所有下载失败都发生在原安装尚未改动时。"""
    await asyncio.to_thread(assert_idle, root)
    try:
        current, arch = await asyncio.to_thread(read_install, root)
    except (OSError, ValueError):
        # 曾经成功安装过的目录可按原架构修复损坏的 exe/interface；不按主机架构猜测。
        identity = _utils_io.read_dict_file(
            script_install.workspace(root) / "program-identity.json"
        )
        arch = identity.get("arch")
        if arch not in ("x86_64", "aarch64"):
            raise script_install.InstallUnsafeError(
                "无法识别 MaaEnd 原安装架构，请先手动修复"
            )
        current = Version("0")
    target, name, url, size, digest = select_package(
        await request_release(config.Update.Channel), arch
    )
    verified = await script_install.run_worker(
        script_install.verify_installed_files, root
    )
    if target == current and verified:
        return f"MaaEnd 当前版本 {current} 无需更新"
    if target < current:
        if verified:
            return f"MaaEnd 当前版本 {current} 高于所选通道，无需更新"
        raise ValueError(
            "当前 MaaEnd 高于所选更新通道，且安装尚未通过校验，请选择匹配通道"
        )
    cdk = (
        config.Update.MirrorChyanCDK.strip()
        or Config.setting.Update.MirrorChyanCDK.strip()
    )
    source = "GitHub"
    if cdk:
        payload = await request_mirror_resource(
            "MaaEnd",
            params={
                "cdk": cdk,
                "os": "win",
                "arch": "x64" if arch == "x86_64" else "arm64",
                "channel": config.Update.Channel,
            },
            proxy=Config.proxy,
        )
        data = payload.get("data", {})
        if (
            data.get("update_type") != "full"
            or Version(str(data.get("version_name", ""))) != target
        ):
            raise ValueError("Mirror 酱完整包版本与官方发行版本不一致")
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
    # 每次独立暂存，不覆盖取消尚未确认的下载目标；恢复时也不依赖缓存内容。
    import tempfile

    cache = Path.cwd() / "data" / "maaend_update"
    cache.mkdir(parents=True, exist_ok=True)
    destination = Path(tempfile.mkdtemp(dir=cache, prefix="download-")) / name
    await download_file(
        url,
        destination,
        timeout=30 * 60,
        proxy=Config.proxy,
        downloader="fluxdown"
        if Config.setting.Update.FluxdownTakeoverAll
        else "builtin",
        source=source,
        progress=progress,
    )

    def validate(path: Path) -> None:
        version, actual_arch = read_install(path)
        if version != target or actual_arch != arch:
            raise ValueError("MaaEnd 更新包版本或架构与目标不一致")

    # 下载成功才回收本次包；下载取消或续传未确认时保留独立目标。
    try:
        await script_install.run_worker(
            script_install.install_package,
            root,
            destination,
            size,
            digest,
            PROTECTED,
            validate,
            lambda: assert_idle(root),
        )
        _utils_io.write_file(
            script_install.workspace(root) / "program-identity.json", {"arch": arch}
        )
        return f"MaaEnd 已更新至 {target}，完整性校验通过"
    finally:
        # run_worker 在取消时等待安装线程结束，避免删掉仍在使用的压缩包。
        with suppress(OSError):
            destination.unlink(missing_ok=True)
            destination.parent.rmdir()

async def confirm_current_install(root: Path) -> None:
    if (script_install.workspace(root) / "transaction.json").exists():
        raise script_install.InstallUnsafeError(
            "MaaEnd 安装状态尚未确认，不能沿用旧版运行"
        )
    await asyncio.to_thread(assert_idle, root)
    try:
        await asyncio.to_thread(read_install, root)
    except (ValueError, OSError) as error:
        raise script_install.InstallUnsafeError(
            "MaaEnd 当前安装不可识别，请开启更新接管修复"
        ) from error
    receipt = script_install.workspace(root) / "installed.json"
    if receipt.exists() and not await script_install.run_worker(
        script_install.verify_installed_files, root
    ):
        raise script_install.InstallUnsafeError(
            "MaaEnd 已安装文件与上次校验记录不符，请开启更新接管修复"
        )


def recover_runtime_interface(root: Path) -> None:
    """只恢复仍等于注入值的公开接口文件，不覆盖外部修改。"""
    directory = script_install.workspace(root)
    journal = directory / "runtime-interface.json"
    if not journal.exists():
        return
    try:
        state = json.loads(journal.read_text(encoding="utf-8"))
        original = base64.b64decode(state["original"], validate=True)
        injected = base64.b64decode(state["injected"], validate=True)
        path = root / "interface.json"
        current = path.read_bytes()
        if current not in (original, injected):
            raise script_install.InstallUnsafeError(
                "托管期间 MaaEnd 接口文件被外部修改，已保留现场，请手动确认"
            )
        if current == injected:
            _write_interface(path, original)
        journal.unlink()
    except script_install.InstallUnsafeError:
        raise
    except Exception as error:
        raise script_install.InstallUnsafeError(
            "MaaEnd 运行接口恢复失败，不能继续启动"
        ) from error


def suspend_native_updates(root: Path) -> None:
    """PI V2 公开更新来源的可恢复覆盖，不伪造版本或读取 WebView 私有存储。"""
    recover_runtime_interface(root)
    path = root / "interface.json"
    original = path.read_bytes()
    interface = _utils_io.read_dict_file(path, format=".json5")
    interface.pop("mirrorchyan_rid", None)
    injected = json.dumps(interface, ensure_ascii=False, indent=4).encode("utf-8")
    directory = script_install.workspace(root)
    directory.mkdir(exist_ok=True)
    journal = directory / "runtime-interface.json"
    temporary = directory / "runtime-interface.tmp"
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "original": base64.b64encode(original).decode(),
                "injected": base64.b64encode(injected).decode(),
            },
            handle,
        )
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(journal)
    _write_interface(path, injected)


def _write_interface(path: Path, content: bytes) -> None:
    temporary = path.with_name(".mas-interface.tmp")
    with temporary.open("wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def managed_launch_environment() -> dict[str, str]:
    """WebView2 官方环境变量隔离旧的待安装记录；不读写原生浏览器数据。"""
    directory = Path.cwd() / "data" / "maaend_webview"
    directory.mkdir(parents=True, exist_ok=True)
    profile = tempfile.mkdtemp(prefix="run-", dir=directory)
    return {**os.environ, "WEBVIEW2_USER_DATA_FOLDER": profile}
