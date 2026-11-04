# Copyright © 2025-2026 AUTO-MAS Team
# SPDX-License-Identifier: AGPL-3.0-or-later
"""BAAH 官方更新 ZIP：预下载不占安装锁、不写安装目录，应用阶段才切换目录。"""

import asyncio
import hashlib
import shutil
import tempfile
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx
import psutil
from packaging.version import Version

from app.core import Config
from app.core.script_update import download_script_package
from app.services import script_install
from app.services.common.update.transport import (
    DownloadProgress,
    request_mirror_resource,
)
from app.utils import io as io_utils

REPOSITORY = "BlueArchiveArisHelper/BAAH"
PROTECTED = frozenset({"baah_configs", ".git"})


@dataclass(frozen=True)
class PreparedUpdate:
    root: Path
    base_exe_sha256: str
    version: Version
    archive: Path
    size: int
    digest: str


def exe_digest(root: Path) -> str:
    with (root / "BAAH.exe").open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def read_version(root: Path) -> Version:
    identity = script_install.workspace(root) / "baah-version.json"
    if identity.exists():
        state = io_utils.read_dict_file(identity)
        if state["exe_sha256"] == exe_digest(root):
            return Version(state["version"])
    # 与上游 update.py 相同的公开安装版本记录；不读取任务配置语义。
    state = io_utils.read_dict_file(root / "DATA/CONFIGS/software_config.json")
    return Version(str(state["NOWVERSION"]).removeprefix("BAAH").strip())


def assert_idle(root: Path) -> None:
    for process in psutil.process_iter(["exe", "name"]):
        try:
            exe = process.info["exe"]
            name = str(process.info.get("name", "")).casefold()
            if not exe and name in {"baah.exe", "baah_update.exe", "update_temp.exe"}:
                raise script_install.InstallUnsafeError(
                    "无法确认 BAAH 更新器已退出，请以管理员身份重试"
                )
            if exe and Path(exe).resolve().is_relative_to(root.resolve()):
                raise script_install.InstallUnsafeError(
                    "BAAH 或其更新器仍在运行，请退出后重试"
                )
        except psutil.NoSuchProcess:
            continue
        except psutil.AccessDenied as error:
            raise script_install.InstallUnsafeError(
                "无法确认 BAAH 进程状态，请以管理员身份重试"
            ) from error


async def confirm_current_install(root: Path) -> None:
    await asyncio.to_thread(assert_idle, root)
    if (script_install.workspace(root) / "transaction.json").exists():
        raise script_install.InstallUnsafeError("BAAH 安装尚未确认，请开启更新托管修复")
    if script_install.read_pe_architecture(root / "BAAH.exe") != "x86_64":
        raise script_install.InstallUnsafeError(
            "BAAH 安装架构不可识别，请使用官方包修复"
        )
    receipt = script_install.workspace(root) / "installed.json"
    if receipt.exists() and not await script_install.run_worker(
        script_install.verify_installed_files, root
    ):
        raise script_install.InstallUnsafeError(
            "BAAH 安装文件与校验记录不符，请开启更新托管修复"
        )


async def request_release(channel: str) -> dict:
    path = "releases/latest" if channel == "stable" else "releases?per_page=100"
    async with httpx.AsyncClient(
        proxy=Config.proxy, timeout=15, follow_redirects=True
    ) as client:
        response = await client.get(f"https://api.github.com/repos/{REPOSITORY}/{path}")
        response.raise_for_status()
        data = response.json()
    candidates = []
    for release in data if isinstance(data, list) else [data]:
        if not isinstance(release, dict) or release.get("draft"):
            continue
        try:
            version = Version(release["tag_name"].removeprefix("BAAH"))
        except (KeyError, ValueError, TypeError):
            continue
        if channel == "stable" and (release.get("prerelease") or version.is_prerelease):
            continue
        candidates.append((version, release))
    if not candidates:
        raise ValueError("未找到可识别的 BAAH 官方发行版")
    return max(candidates, key=lambda item: item[0])[1]


def verify_package(
    archive: Path, size: int, digest: str, cancelled: threading.Event
) -> None:
    script_install.verify_archive(archive, size, digest, cancelled)
    with zipfile.ZipFile(archive) as package:
        names = {
            script_install._member_name(item.filename).casefold()
            for item in package.infolist()
        }
        if "baah.exe" not in names:
            raise ValueError("BAAH 更新包缺少主程序")
        for name in names:
            if (
                name.startswith(
                    (
                        "baah_configs/",
                        "data/logs/",
                        "data/user_storage/",
                        "data/crash_reports/",
                        "data/tmp/",
                    )
                )
                or name == "data/configs/software_config.json"
            ):
                raise ValueError("BAAH 更新包试图覆盖用户配置或运行数据")


async def prepare_update(
    root: Path, config, *, progress: DownloadProgress | None = None
) -> PreparedUpdate | None:
    """只读当前版本，在 MAS 数据目录下载并校验；允许与上一脚本运行并行。"""
    channel = config.Update.Channel
    cdk = (
        config.Update.MirrorChyanCDK.strip()
        or Config.setting.Update.MirrorChyanCDK.strip()
    )
    proxy = Config.proxy
    root = root.resolve()
    baseline = await asyncio.to_thread(exe_digest, root)
    current = await asyncio.to_thread(read_version, root)
    release = await request_release(channel)
    target = Version(release["tag_name"].removeprefix("BAAH"))
    receipt = script_install.workspace(root) / "installed.json"
    verified = not receipt.exists() or await script_install.run_worker(
        script_install.verify_installed_files, root
    )
    if target <= current and verified:
        return None
    if target < current:
        raise script_install.InstallUnsafeError(
            "当前 BAAH 安装未通过校验，不会自动降级，请手动修复"
        )
    name = f"{release['tag_name']}_update.zip"
    assets = [item for item in release.get("assets", []) if item.get("name") == name]
    if len(assets) != 1:
        raise ValueError("BAAH 发行版缺少唯一的官方更新包")
    asset = assets[0]
    size, digest = asset.get("size"), str(asset.get("digest", ""))
    if (
        not isinstance(size, int)
        or isinstance(size, bool)
        or size <= 0
        or not digest.startswith("sha256:")
    ):
        raise ValueError("BAAH 官方更新包缺少大小或 SHA256")
    digest = digest[7:]
    url = f"https://github.com/{REPOSITORY}/releases/download/{quote(release['tag_name'], safe='')}/{quote(name, safe='')}"
    source = "GitHub"
    if cdk:
        # BAAH 无平台参数的 Mirror 资源就是官方 *_update.zip，不传 current_version，避免增量协议混入。
        payload = await request_mirror_resource(
            "BAAH",
            params={"cdk": cdk, "channel": channel},
            proxy=proxy,
        )
        data = payload.get("data", {})
        if (
            Version(str(data.get("version_name", "")).removeprefix("BAAH")) != target
            or data.get("update_type") != "full"
        ):
            raise ValueError("Mirror 酱更新包版本与 BAAH 官方发行版不一致")
        url = str(data.get("url", ""))
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError("Mirror 酱更新包地址无效")
        source = "MirrorChyan"
    cache = Config.data_path / "baah_update"
    cache.mkdir(parents=True, exist_ok=True)
    destination = Path(tempfile.mkdtemp(prefix="download-", dir=cache)) / name
    # 未确认停止的下载保留独立目标，不能删除仍由下载器持有的文件。
    await download_script_package(
        url,
        destination,
        source=source,
        proxy=proxy,
        timeout=1800,
        progress=progress,
    )
    await script_install.run_worker(verify_package, destination, size, digest)
    return PreparedUpdate(root, baseline, target, destination, size, digest)


async def apply_update(root: Path, prepared: PreparedUpdate) -> None:
    """调用者持安装锁；重新验证安装身份和包体后，才允许修改安装目录。"""
    if (
        root.resolve() != prepared.root
        or await asyncio.to_thread(exe_digest, root) != prepared.base_exe_sha256
    ):
        raise ValueError("BAAH 安装在预下载后发生变化，请重新检查更新")
    await asyncio.to_thread(assert_idle, root)
    await script_install.run_worker(
        verify_package, prepared.archive, prepared.size, prepared.digest
    )

    def validate(path: Path) -> None:
        if script_install.read_pe_architecture(path / "BAAH.exe") != "x86_64":
            raise ValueError("BAAH 更新包程序架构无效")

    await script_install.run_worker(
        script_install.install_package,
        root,
        prepared.archive,
        prepared.size,
        prepared.digest,
        PROTECTED,
        validate,
        lambda: assert_idle(root),
    )
    io_utils.write_file(
        script_install.workspace(root) / "baah-version.json",
        {"version": str(prepared.version), "exe_sha256": exe_digest(root)},
    )
    shutil.rmtree(prepared.archive.parent)


async def update_before_run(
    root: Path, config, *, progress: DownloadProgress | None = None
) -> str:
    await script_install.run_worker(
        script_install.recover_install, root, lambda: assert_idle(root)
    )
    candidate = await prepare_update(root, config, progress=progress)
    if candidate is None:
        await confirm_current_install(root)
        return "BAAH 当前版本无需更新"
    await apply_update(root, candidate)
    return f"BAAH 已更新至 {candidate.version}，完整性校验通过"
