"""GitHub 按差异量重建，自建站限定版本范围；均以官方整包 SHA256 验收。"""

import json
import os
import shutil
import threading
import zipfile
from contextlib import suppress
from functools import partial
from pathlib import Path

import httpx
from packaging.version import Version

from app.core import Config
from app.core.downloads import download_file
from app.services import script_install
from app.services.common.update import transport
from app.services.common.update.transport import DownloadProgress
from app.task.MaaFW.tools.core.project_update.projection_heal import RangeHTTPReader
from app.task.MaaFW.tools.core.project_update.range_delta import RangeSpeedGuard
from app.utils import get_logger
from app.utils.common.zip_delta import MAX_PATCH_BYTES, apply_patch
from app.utils.common.zip_range import rebuild_zip

logger = get_logger("MaaEnd 增量下载")
MAX_INDEX_BYTES = 512 * 1024


def read_policy(
    path: Path,
    current: str,
    target: str,
    size: int,
    digest: str,
    arch: str,
    channel: str,
) -> bool:
    """下载站只能缩小可用范围，不能替代 GitHub 官方摘要或放宽同号 beta 规则。"""
    with zipfile.ZipFile(path) as archive:
        info = archive.getinfo("manifest.json")
        if info.file_size > MAX_INDEX_BYTES:
            raise ValueError("更新索引过大")
        policy = json.loads(archive.read(info))
    return policy_allows(policy, current, target, size, digest, arch, channel)


def policy_allows(
    policy: dict,
    current: str,
    target: str,
    size: int,
    digest: str,
    arch: str,
    channel: str,
) -> bool:
    current_version, target_version = Version(current), Version(target)
    if (
        policy.get("version") != 2
        or policy.get("mode") != "range-zip"
        or policy.get("channel") != channel
        or policy.get("arch") != arch
        or policy.get("target_sha256") != digest
        or policy.get("target_size") != size
        or Version(policy["target_version"]) != target_version
    ):
        raise ValueError("增量索引与官方目标不一致")
    bases = [Version(value) for value in policy["bases"]]
    if (
        len(bases) > 3
        or len(set(bases)) != len(bases)
        or any(base.is_prerelease or base.is_devrelease for base in bases)
    ):
        raise ValueError("增量正式基线无效")
    if channel == "stable":
        if target_version.is_prerelease or any(
            base >= target_version for base in bases
        ):
            raise ValueError("正式版增量范围无效")
        return current_version in bases
    anchor = Version(policy["beta_base"]) if policy.get("beta_base") else None
    if (
        not target_version.is_prerelease
        or anchor is None
        or bases != [anchor]
        or anchor.is_prerelease
        or anchor.release != target_version.release
    ):
        return False
    return current_version == anchor or (
        current_version.is_prerelease
        and current_version.release == anchor.release
        and current_version < target_version
    )


def _rebuild_remote(
    baseline: Path,
    url: str,
    destination: Path,
    size: int,
    digest: str,
    proxy: httpx.Proxy | None,
    guard_speed: bool,
    cancelled: threading.Event,
) -> None:
    """复用现有 Range 读取器的区间校验、预算与取消，不复用 MFW 的文件树安装语义。"""
    guard = RangeSpeedGuard() if guard_speed else None
    if guard is not None:
        guard.planned_total = int(size * 0.4)
        guard.phase = "ZIP 重建"
    with httpx.Client(proxy=proxy, follow_redirects=True, timeout=30) as client:
        reader = RangeHTTPReader(
            client,
            url,
            expected_size=size,
            max_bytes=int(size * 0.4),
            cancelled=cancelled.is_set,
            over_limit_reason="变化或区间读取超过整包 40%，回退全量",
            on_chunk=guard.observe if guard is not None else None,
        )
        try:
            reused, changed = rebuild_zip(
                baseline,
                reader,
                destination,
                size,
                digest,
                cancelled,
                progress=lambda *_: reader.forget(reader.tell()),
            )
            logger.info(
                f"MaaEnd ZIP 重建通过官方 SHA256：复用 {reused}，取回 {changed} 个条目，读取 {reader.fetched} 字节"
            )
        finally:
            reader.close()


def remember_package(
    root: Path,
    archive: Path,
    size: int,
    digest: str,
    cancelled: threading.Event,
    *,
    version: str = "",
) -> None:
    """只缓存已通过官方摘要校验的归档；缓存不可用不改变安装成功结论。"""
    script_install.verify_archive(archive, size, digest, cancelled)
    directory = (
        Config.data_path
        / "maaend_package_cache"
        / script_install.record_directory(root).name
    )
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / f"{os.urandom(8).hex()}.part"
    try:
        shutil.copyfile(archive, temporary)
        script_install.verify_archive(temporary, size, digest, cancelled)
        temporary.replace(directory / "baseline.zip")
        metadata = directory / "baseline.json.part"
        metadata.write_text(
            json.dumps({"size": size, "sha256": digest, "version": version}),
            encoding="utf-8",
        )
        metadata.replace(directory / "baseline.json")
        if version and not Version(version).is_prerelease:
            # beta 更新不能覆盖正式基准；只额外保留一份最近的正式归档。
            shutil.copyfile(directory / "baseline.zip", directory / "stable.zip.part")
            (directory / "stable.zip.part").replace(directory / "stable.zip")
            shutil.copyfile(directory / "baseline.json", directory / "stable.json.part")
            (directory / "stable.json.part").replace(directory / "stable.json")
    finally:
        temporary.unlink(missing_ok=True)


async def download_incremental(
    root: Path,
    destination: Path,
    size: int,
    digest: str,
    *,
    proxy: httpx.Proxy | None = None,
    arch: str,
    channel: str,
    current_version: str,
    target_version: str,
    official_url: str,
    guard_speed: bool = False,
    progress: DownloadProgress | None = None,
) -> bool:
    """先尝试 GitHub Range，再按发布范围尝试自建站；均失败时由调用方全量下载。"""
    directory = (
        Config.data_path
        / "maaend_package_cache"
        / script_install.record_directory(root).name
    )
    patch = destination.with_suffix(".delta")
    try:
        metadata = json.loads((directory / "baseline.json").read_text(encoding="utf-8"))
        baseline = directory / "baseline.zip"
        await script_install.run_worker(
            script_install.verify_archive,
            baseline,
            metadata["size"],
            metadata["sha256"],
        )
        try:
            await script_install.run_worker(
                _rebuild_remote,
                baseline,
                official_url,
                destination,
                size,
                digest,
                proxy,
                guard_speed,
            )
            return True
        except Exception as error:
            logger.info(f"GitHub 区间重建不可用（{type(error).__name__}），尝试自建站")
            destination.unlink(missing_ok=True)
        architecture = "x64" if arch == "x86_64" else "arm64"
        public_url = (
            "https://data.auto-mas.top/api/v1/files/auto-mas/Client/"
            f"maaend-{architecture}-{channel}-delta/download"
        )
        await download_file(
            public_url,
            patch,
            proxy=proxy,
            downloader="builtin",
            source="MAS",
            timeout=300,
            progress=progress,
            http_download=partial(transport.download_file, max_bytes=MAX_PATCH_BYTES),
        )
        eligible = await script_install.run_worker(
            lambda cancelled: read_policy(
                patch, current_version, target_version, size, digest, arch, channel
            )
        )
        if not eligible:
            logger.info("MaaEnd 当前版本不在增量覆盖范围，使用全量")
            return False
        if channel == "beta" and (directory / "stable.json").is_file():
            stable_metadata = json.loads(
                (directory / "stable.json").read_text(encoding="utf-8")
            )
            baseline = directory / "stable.zip"
            await script_install.run_worker(
                script_install.verify_archive,
                baseline,
                stable_metadata["size"],
                stable_metadata["sha256"],
            )
        await script_install.run_worker(
            apply_patch, baseline, patch, destination, size, digest
        )
        logger.info("MaaEnd 增量包重建完成，官方整包 SHA256 校验通过")
        return True
    except Exception as error:
        logger.info(f"增量下载不可用（{type(error).__name__}），回退全量更新")
        destination.unlink(missing_ok=True)
        return False
    finally:
        # 收尾期限到达时 run_worker 仍可能持有归档，保留独立缓存而不遮蔽取消。
        with suppress(OSError):
            patch.unlink(missing_ok=True)
