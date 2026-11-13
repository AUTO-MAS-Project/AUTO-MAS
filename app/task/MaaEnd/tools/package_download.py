"""MaaEnd 自建站字节增量下载：重建后仍要求官方整包 SHA256，安装流程保持不变。"""

import json
import os
import shutil
import threading
from contextlib import suppress
from functools import partial
from pathlib import Path

import httpx

from app.core import Config
from app.core.update import download_file
from app.services import script_install
from app.services.common.update import transport
from app.services.common.update.transport import DownloadProgress
from app.utils import get_logger
from app.utils.common.zip_delta import MAX_PATCH_BYTES, apply_patch

logger = get_logger("MaaEnd 增量下载")


def remember_package(
    root: Path, archive: Path, size: int, digest: str, cancelled: threading.Event
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
            json.dumps({"size": size, "sha256": digest}), encoding="utf-8"
        )
        metadata.replace(directory / "baseline.json")
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
    progress: DownloadProgress | None = None,
) -> bool:
    """从独立下载站获取字节增量；不可用时由调用方全量下载。"""
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
