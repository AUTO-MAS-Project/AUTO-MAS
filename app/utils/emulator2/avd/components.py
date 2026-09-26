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

"""官方模拟器组件：检查、许可证、测速、下载、校验、解压。

**不用 sdkmanager、不要 JDK。** 新版 cmdline-tools 已经变成「Android CLI」外壳，分号包名
静默跳过、退出码 0xC0000409（预研 §6.1）；旧版又得自带 JDK。这里直接按官方仓库里的
包地址下载 zip，校验 sha1 后解压到 SDK 目录，再补上模拟器认版本用的 ``source.properties``。

**不分发任何 Google 文件**：只在用户勾选同意《Android SDK 许可协议》之后，由用户电脑
直接从下载源拉取。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import time
import xml.etree.ElementTree as ElementTree
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from app.utils import get_logger

from .constants import (
    AVD_DIR,
    COMPONENTS_DIR,
    DOWNLOAD_SOURCES,
    DOWNLOADS_DIR,
    FOSSIFY_LAUNCHER,
    LICENSE_ID,
    LICENSE_MANIFEST,
    METADATA_FILE,
    REQUIRED_COMPONENTS,
    SDK_DIR,
    Component,
    DownloadSource,
    LauncherComponent,
)

logger = get_logger("官方模拟器组件")

#: 解压后大约占多少（字节），只用于下载前的磁盘空间预检，宁多勿少。
_EXTRACTED_SIZE = {
    "platform-tools": 30 * 1024**2,
    "emulator": 1200 * 1024**2,
    "system-image": 4600 * 1024**2,
}
#: 预检时额外留的余量：第一台实例开机就要写几 GB 数据盘。
_DISK_MARGIN = 2 * 1024**3

#: 每个组件解压后必须存在的文件——只看 ``source.properties`` 不够，解压到一半断掉的
#: 目录里它可能已经在了。
_KEY_FILES = {
    "platform-tools": ("adb.exe",),
    "emulator": ("emulator.exe", "qemu/windows-x86_64/qemu-system-x86_64.exe"),
    "system-image": ("system.img", "vendor.img", "kernel-ranchu", "ramdisk.img"),
}

#: 测速：各源拉系统镜像包的前这么多字节，最多等这么久。
_PROBE_BYTES = 3 * 1024 * 1024
_PROBE_TIMEOUT_SECONDS = 10.0

_HTTP_TIMEOUT = httpx.Timeout(30.0, connect=15.0)
_CHUNK = 256 * 1024
#: 单个文件下载失败后的重试次数（每次都从断点续传）。
_DOWNLOAD_RETRIES = 5
_RETRY_DELAY_SECONDS = 3.0
#: 进度推送的最小间隔。收尾事件不受限。
_PROGRESS_THROTTLE_SECONDS = 0.5


class DownloadCancelled(Exception):
    """用户取消了下载。已经下载的部分留在 ``downloads\\``，下次接着下。"""


class ComponentError(RuntimeError):
    """组件准备失败；消息直接给用户看。"""


# ---- 根目录与元数据 --------------------------------------------------------


def root_key(root: str | Path) -> str:
    """根目录的规范化键，任务表与元数据按它去重。"""
    return os.path.normcase(os.path.abspath(str(root)))


def sdk_dir(root: str | Path) -> Path:
    return Path(root) / SDK_DIR


def emulator_exe(root: str | Path) -> Path:
    return sdk_dir(root) / "emulator" / "emulator.exe"


def adb_exe(root: str | Path) -> Path:
    return sdk_dir(root) / "platform-tools" / "adb.exe"


def avd_home(root: str | Path) -> Path:
    return Path(root) / AVD_DIR


def launcher_apk(root: str | Path) -> Path:
    return Path(root) / COMPONENTS_DIR / FOSSIFY_LAUNCHER.file_name


def root_from_manager_exe(manager_exe: str | Path) -> Path:
    """``<根>\\sdk\\emulator\\emulator.exe`` → ``<根>``。"""
    return Path(manager_exe).resolve().parents[2]


def read_metadata(root: str | Path) -> dict[str, Any]:
    """读 ``mas-avd.json``。不存在或读不出按空字典处理。"""
    path = Path(root) / METADATA_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_metadata(root: str | Path, data: dict[str, Any]) -> None:
    """原子写 ``mas-avd.json``：先写临时文件再替换，写到一半断电也不留半个 JSON。"""
    path = Path(root) / METADATA_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def update_metadata(root: str | Path, **changes: Any) -> dict[str, Any]:
    data = read_metadata(root)
    data.update(changes)
    write_metadata(root, data)
    return data


def _read_properties(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    result: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            result[key.strip()] = value.strip()
    return result


def _expected_revision(component: Component) -> str:
    return _read_properties_text(component.source_properties).get("Pkg.Revision", "")


def _read_properties_text(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            result[key.strip()] = value.strip()
    return result


def component_installed(root: str | Path, component: Component) -> bool:
    """组件是否已按固定版本装好：版本号对得上，关键文件都在。"""
    target = sdk_dir(root) / component.target
    props = _read_properties(target / "source.properties")
    if props.get("Pkg.Revision") != _expected_revision(component):
        return False
    return all((target / name).is_file() for name in _KEY_FILES[component.id])


def launcher_downloaded(root: str | Path) -> bool:
    path = launcher_apk(root)
    try:
        return path.stat().st_size == FOSSIFY_LAUNCHER.size
    except OSError:
        return False


def read_emulator_version(root: str | Path) -> str | None:
    """``sdk\\emulator\\source.properties`` 的 ``Pkg.Revision``。没有返回 ``None``。"""
    props = _read_properties(sdk_dir(root) / "emulator" / "source.properties")
    return props.get("Pkg.Revision") or None


def _partial_size(root: str | Path, file_name: str) -> int:
    try:
        return (Path(root) / DOWNLOADS_DIR / (file_name + ".part")).stat().st_size
    except OSError:
        return 0


def _archive_name(component: Component) -> str:
    return component.url.rsplit("/", 1)[-1]


def install_status(root: str | Path) -> dict[str, Any]:
    """根目录里组件的现状。只读，不联网。"""
    root = Path(root)
    metadata = read_metadata(root)
    items: list[dict[str, Any]] = []
    missing_bytes = 0
    for component in REQUIRED_COMPONENTS:
        installed = component_installed(root, component)
        partial = 0 if installed else _partial_size(root, _archive_name(component))
        if not installed:
            missing_bytes += max(0, component.size - partial)
        items.append(
            {
                "id": component.id,
                "name": component.name,
                "version": component.version,
                "sizeBytes": component.size,
                "installed": installed,
                "downloadedBytes": partial,
                "optional": False,
                "license": component.license,
            }
        )
    launcher_ok = launcher_downloaded(root)
    items.append(
        {
            "id": FOSSIFY_LAUNCHER.id,
            "name": FOSSIFY_LAUNCHER.name,
            "version": FOSSIFY_LAUNCHER.version,
            "sizeBytes": FOSSIFY_LAUNCHER.size,
            "installed": launcher_ok,
            "downloadedBytes": FOSSIFY_LAUNCHER.size if launcher_ok else 0,
            "optional": True,
            "license": FOSSIFY_LAUNCHER.license,
        }
    )
    ready = all(item["installed"] for item in items if not item["optional"])
    try:
        free_bytes = shutil.disk_usage(_existing_ancestor(root)).free
    except OSError:
        free_bytes = None
    return {
        "root": str(root),
        "ready": ready,
        "components": items,
        "missingBytes": missing_bytes,
        "requiredDiskBytes": _required_disk_bytes(root) if not ready else 0,
        "freeDiskBytes": free_bytes,
        "licenseAccepted": bool(metadata.get("licenseAcceptedAt")),
        "licenseAcceptedAt": metadata.get("licenseAcceptedAt") or "",
        "source": metadata.get("source") or "",
    }


def _existing_ancestor(path: Path) -> Path:
    """磁盘空间要问一个真实存在的目录；根目录可能还没建。"""
    current = path
    while not current.exists() and current.parent != current:
        current = current.parent
    return current


def _required_disk_bytes(root: Path) -> int:
    total = 0
    for component in REQUIRED_COMPONENTS:
        if component_installed(root, component):
            continue
        total += max(0, component.size - _partial_size(root, _archive_name(component)))
        total += _EXTRACTED_SIZE[component.id]
    return total


def check_disk_space(root: str | Path) -> None:
    """下载前的空间预检。不够就明确拒绝，不下到一半才因为磁盘满失败。"""
    root = Path(root)
    required = _required_disk_bytes(root)
    if required == 0:
        return
    free = shutil.disk_usage(_existing_ancestor(root)).free
    if free < required + _DISK_MARGIN:
        raise ComponentError(
            f"磁盘空间不足：下载并解压官方模拟器组件约需 {_gib(required + _DISK_MARGIN)}，"
            f"{_existing_ancestor(root).anchor} 只剩 {_gib(free)}。"
            "游戏资源也会放在这个目录里，请选空间更大的盘"
        )


def _gib(value: int) -> str:
    return f"{value / 1024**3:.1f} GB"


# ---- 许可证与测速 ----------------------------------------------------------


def _source_by_id(source_id: str | None) -> DownloadSource | None:
    for source in DOWNLOAD_SOURCES:
        if source.id == source_id:
            return source
    return None


def list_sources() -> list[dict[str, str]]:
    return [
        {"id": source.id, "name": source.name, "url": source.root}
        for source in DOWNLOAD_SOURCES
    ]


def parse_license(manifest_xml: bytes | str, license_id: str = LICENSE_ID) -> str:
    """从仓库清单里取许可证全文。取不到抛 :class:`ComponentError`。"""
    try:
        root = ElementTree.fromstring(manifest_xml)
    except ElementTree.ParseError as e:
        raise ComponentError(f"下载源返回的仓库清单无法解析: {e}") from e
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag == "license" and element.get("id") == license_id:
            text = (element.text or "").strip()
            if text:
                return text
    raise ComponentError(f"仓库清单里没有许可证 {license_id}")


async def fetch_license(source_id: str | None = None) -> dict[str, str]:
    """从下载源取《Android SDK 许可协议》全文。

    按用户选的源取；没选就按默认顺序逐个试，第一个取到的为准。
    """
    candidates = [_source_by_id(source_id)] if source_id else list(DOWNLOAD_SOURCES)
    errors: list[str] = []
    async with httpx.AsyncClient(
        timeout=_HTTP_TIMEOUT, follow_redirects=True
    ) as client:
        for source in candidates:
            if source is None:
                continue
            try:
                response = await client.get(source.root + LICENSE_MANIFEST)
                response.raise_for_status()
                text = parse_license(response.content)
            except Exception as e:  # noqa: BLE001 - 换下一个源
                errors.append(f"{source.name}: {e}")
                continue
            return {"licenseId": LICENSE_ID, "text": text, "source": source.id}
    raise ComponentError("取不到许可协议全文：" + "；".join(errors))


async def probe_sources(
    *, probe_bytes: int = _PROBE_BYTES, timeout: float = _PROBE_TIMEOUT_SECONDS
) -> list[dict[str, Any]]:
    """各源依次拉系统镜像包的前几 MB 测速，按速度从快到慢返回；失败的源排在最后。

    依次而不是并发测：并发时几个源抢同一条宽带，量出来的是分到的份额，不是源的速度。
    """
    results: list[dict[str, Any]] = []
    probe_path = REQUIRED_COMPONENTS[-1].url
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout, connect=min(timeout, 8.0)),
        follow_redirects=True,
    ) as client:
        for source in DOWNLOAD_SOURCES:
            item: dict[str, Any] = {
                "id": source.id,
                "name": source.name,
                "url": source.root,
                "ok": False,
                "speedBytesPerSec": None,
                "error": "",
            }
            received = 0
            started = time.monotonic()
            try:
                async with asyncio.timeout(timeout):
                    async with client.stream(
                        "GET",
                        source.root + probe_path,
                        headers={
                            "Range": f"bytes=0-{probe_bytes - 1}",
                            "Accept-Encoding": "identity",
                        },
                    ) as response:
                        response.raise_for_status()
                        async for chunk in response.aiter_raw(_CHUNK):
                            received += len(chunk)
                            if received >= probe_bytes:
                                break
            except TimeoutError:
                # 慢源在限时内拉到多少算多少：能拉到一点就说明源是通的
                if received == 0:
                    item["error"] = "超时"
            except Exception as e:  # noqa: BLE001 - 失败的源排除
                item["error"] = f"{type(e).__name__}: {e}"
            elapsed = max(time.monotonic() - started, 1e-3)
            if received > 0 and not item["error"]:
                item["ok"] = True
                item["speedBytesPerSec"] = round(received / elapsed, 1)
            results.append(item)
    results.sort(key=lambda item: (not item["ok"], -(item["speedBytesPerSec"] or 0.0)))
    return results


# ---- 下载与校验 -----------------------------------------------------------


ProgressCallback = Callable[[int], None]


async def download_file(
    client: httpx.AsyncClient,
    url: str,
    part_path: Path,
    expected_size: int,
    *,
    on_bytes: ProgressCallback,
    cancel: asyncio.Event,
) -> None:
    """把 ``url`` 下到 ``part_path``，支持断点续传。

    已有部分就带 ``Range`` 续；服务器不认 Range（回 200）就从头来。每拿到一块都检查取消，
    取消时抛 :class:`DownloadCancelled`，已下载部分原样保留。
    """
    part_path.parent.mkdir(parents=True, exist_ok=True)
    existing = part_path.stat().st_size if part_path.exists() else 0
    if existing > expected_size:
        # 比应有的还大，内容一定不对，丢掉重下
        part_path.unlink()
        existing = 0
    if existing == expected_size:
        return

    # 必须要原始字节：dl.google.com 在客户端声明支持 gzip 时会把 zip 再 gzip 一遍传，
    # Range 就落在压缩流上，续传的那一段解不开（09-26 实测）。
    headers = {"Accept-Encoding": "identity"}
    if existing:
        headers["Range"] = f"bytes={existing}-"
    async with client.stream("GET", url, headers=headers) as response:
        if response.status_code not in (200, 206):
            response.raise_for_status()
            raise ComponentError(f"下载失败: HTTP {response.status_code}")
        mode = "ab"
        resumed = response.status_code == 206 and response.headers.get(
            "content-range", ""
        ).startswith(f"bytes {existing}-")
        if existing and not resumed:
            logger.warning(f"下载源没有按断点续传返回，从头下载: {url}")
            on_bytes(-existing)
            existing = 0
            mode = "wb"
        elif existing:
            logger.info(f"从 {existing} 字节处续传: {url}")
        with part_path.open(mode) as file:
            async for chunk in response.aiter_raw(_CHUNK):
                if cancel.is_set():
                    raise DownloadCancelled()
                file.write(chunk)
                on_bytes(len(chunk))
    size = part_path.stat().st_size
    if size != expected_size:
        raise ComponentError(
            f"下载不完整：应为 {expected_size} 字节，实际 {size} 字节（{url}）"
        )


def file_digest(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as file:
        while True:
            block = file.read(4 * 1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def extract_component(
    root: Path,
    component: Component,
    archive: Path,
    on_progress: Callable[[int, int], None] | None = None,
) -> None:
    """解压一个组件到 ``sdk\\<target>``，并补写 ``source.properties``。

    先解压到 ``sdk\\.staging\\<id>``，整个包解完再挪到目标位置，解到一半断掉的目录
    不会被当成已安装。
    """
    sdk = sdk_dir(root)
    staging = sdk / ".staging" / component.id
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        total = sum(member.file_size for member in members) or 1
        done = 0
        prefix = component.archive_root.rstrip("/") + "/"
        for member in members:
            name = member.filename.replace("\\", "/")
            if not name.startswith(prefix):
                continue
            # zip 里的路径不能跳出暂存目录（防 ../ 与绝对路径）
            relative = Path(*[part for part in name.split("/") if part])
            destination = (staging / relative).resolve()
            if staging.resolve() not in destination.parents and destination != (
                staging.resolve()
            ):
                raise ComponentError(f"压缩包里有非法路径: {member.filename}")
            bundle.extract(member, staging)
            done += member.file_size
            if on_progress is not None:
                on_progress(done, total)

    extracted = staging / component.archive_root
    if not extracted.is_dir():
        raise ComponentError(f"压缩包结构不对：没有 {component.archive_root}/ 目录")
    props = extracted / "source.properties"
    if not props.is_file():
        props.write_text(component.source_properties, encoding="utf-8")

    target = sdk / component.target
    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(extracted, target)
    shutil.rmtree(sdk / ".staging", ignore_errors=True)


# ---- 后台安装任务 ---------------------------------------------------------


ProgressSink = Callable[[dict[str, Any]], None]


@dataclass
class InstallJob:
    """一次后台下载安装。每个根目录同一时间只有一个。

    进度快照 :attr:`snapshot` 是给 HTTP 查询和 WebSocket 推送共用的一份，字段含义见
    ``WSEmulator2AvdInstallProgressData``。
    """

    job_id: str
    root: Path
    source: DownloadSource
    include_launcher: bool
    sink: ProgressSink | None = None
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None
    snapshot: dict[str, Any] = field(default_factory=dict)
    on_success: Callable[[], Any] | None = None

    # 进度累计
    _total: int = 0
    _done: int = 0
    _last_emit: float = 0.0
    _last_sample: tuple[float, int] | None = None
    _speed: float | None = None
    #: 本次任务里已经装好的字节（组件解压完、.part 已删，磁盘上看不出来了）
    _installed_in_job: int = 0

    def cancel(self) -> None:
        self.cancel_event.set()

    @property
    def finished(self) -> bool:
        return self.snapshot.get("status") in ("success", "failed", "cancelled")

    def _emit(self, force: bool = False, **fields: Any) -> None:
        now = time.monotonic()
        self.snapshot.update(fields)
        if (
            not force
            and self._last_emit
            and now - self._last_emit < _PROGRESS_THROTTLE_SECONDS
        ):
            return
        if self.snapshot.get("stage") == "downloading":
            if self._last_sample is not None:
                elapsed = now - self._last_sample[0]
                if elapsed > 0.2:
                    self._speed = max(
                        0.0, (self._done - self._last_sample[1]) / elapsed
                    )
                    self._last_sample = (now, self._done)
            else:
                self._last_sample = (now, self._done)
        self._last_emit = now
        remaining = max(0, self._total - self._done)
        self.snapshot.update(
            downloadedBytes=self._done,
            totalBytes=self._total,
            percent=round(self._done / self._total * 100, 1) if self._total else None,
            speedBytesPerSec=round(self._speed, 1) if self._speed else None,
            etaSeconds=(
                int(remaining / self._speed)
                if self._speed and self.snapshot.get("stage") == "downloading"
                else None
            ),
        )
        if self.sink is not None:
            try:
                self.sink(dict(self.snapshot))
            except Exception as e:  # noqa: BLE001 - 推送失败不影响下载
                logger.debug(f"推送下载进度失败: {e}")

    async def run(self) -> None:
        root = self.root
        self.snapshot = {
            "jobId": self.job_id,
            "root": str(root),
            "source": self.source.id,
            "sourceName": self.source.name,
            "stage": "preparing",
            "status": "running",
            "message": "正在准备下载",
            "component": "",
            "componentName": "",
            "componentIndex": 0,
            "componentCount": 0,
            "error": "",
        }
        try:
            await self._run(root)
        except DownloadCancelled:
            logger.info(f"官方模拟器组件下载已取消: {root}")
            self._emit(
                force=True,
                stage="cancelled",
                status="cancelled",
                message="下载已取消，已下载的部分会保留，下次继续",
            )
        except Exception as e:  # noqa: BLE001 - 失败原因交给界面
            logger.opt(exception=True).warning(f"官方模拟器组件准备失败: {e}")
            self._emit(
                force=True,
                stage="failed",
                status="failed",
                message=f"组件准备失败: {e}",
                error=str(e),
            )

    async def _run(self, root: Path) -> None:
        pending = [c for c in REQUIRED_COMPONENTS if not component_installed(root, c)]
        need_launcher = self.include_launcher and not launcher_downloaded(root)
        await asyncio.to_thread(check_disk_space, root)

        steps: list[Component | LauncherComponent] = list(pending)
        if need_launcher:
            steps.append(FOSSIFY_LAUNCHER)
        self._total = sum(step.size for step in steps)
        self._done = sum(
            min(step.size, _partial_size(root, _step_file(step))) for step in steps
        )
        self.snapshot["componentCount"] = len(steps)

        async with httpx.AsyncClient(
            timeout=_HTTP_TIMEOUT, follow_redirects=True
        ) as client:
            for position, step in enumerate(steps, start=1):
                self.snapshot.update(
                    component=step.id,
                    componentName=step.name,
                    componentIndex=position,
                )
                if isinstance(step, LauncherComponent):
                    await self._fetch_launcher(client, root, step)
                else:
                    await self._fetch_component(client, root, step)

        update_metadata(
            root,
            components={
                **{c.id: c.version for c in REQUIRED_COMPONENTS},
                **(
                    {FOSSIFY_LAUNCHER.id: FOSSIFY_LAUNCHER.version}
                    if launcher_downloaded(root)
                    else {}
                ),
            },
            source=self.source.id,
            installedAt=datetime.now().isoformat(timespec="seconds"),
        )
        from .maa_shim import ensure_mumu_shim

        await asyncio.to_thread(ensure_mumu_shim, root)
        if self.on_success is not None:
            result = self.on_success()
            if asyncio.iscoroutine(result):
                await result
        self._done = self._total
        self._emit(
            force=True,
            stage="completed",
            status="success",
            message="官方模拟器组件已全部就绪",
            component="",
            componentName="",
        )

    def _count(self, delta: int) -> None:
        self._done += delta
        self._emit()

    async def _download_with_retry(
        self, client: httpx.AsyncClient, url: str, part: Path, size: int
    ) -> None:
        for attempt in range(1, _DOWNLOAD_RETRIES + 1):
            try:
                await download_file(
                    client,
                    url,
                    part,
                    size,
                    on_bytes=self._count,
                    cancel=self.cancel_event,
                )
                return
            except DownloadCancelled:
                raise
            except (httpx.HTTPError, OSError, ComponentError) as e:
                if attempt >= _DOWNLOAD_RETRIES:
                    raise ComponentError(f"下载 {part.stem} 失败: {e}") from e
                logger.warning(
                    f"下载 {url} 第 {attempt} 次失败，{_RETRY_DELAY_SECONDS:.0f} 秒后续传: {e}"
                )
                # 重新对齐已下载字节数：失败那一块可能只写了一半
                self._done = self._done_on_disk()
                self._emit(force=True, message=f"下载中断，正在重试（第 {attempt} 次）")
                await asyncio.sleep(_RETRY_DELAY_SECONDS)
            if self.cancel_event.is_set():
                raise DownloadCancelled()

    def _done_on_disk(self) -> int:
        """按磁盘上的真实文件重算已下载字节：已装好的组件算满，其余按 .part 大小。"""
        done = 0
        for component in REQUIRED_COMPONENTS:
            if component_installed(self.root, component):
                continue
            done += min(
                component.size, _partial_size(self.root, _archive_name(component))
            )
        if self.include_launcher and not launcher_downloaded(self.root):
            done += _partial_size(self.root, FOSSIFY_LAUNCHER.file_name)
        # 本次任务里已经装好的组件也要算进去
        return min(self._total, done + self._installed_in_job)

    async def _fetch_component(
        self, client: httpx.AsyncClient, root: Path, component: Component
    ) -> None:
        archive_name = _archive_name(component)
        part = root / DOWNLOADS_DIR / (archive_name + ".part")
        self._emit(
            force=True,
            stage="downloading",
            message=f"正在下载 {component.name}",
        )
        await self._download_with_retry(
            client, self.source.root + component.url, part, component.size
        )

        self._emit(force=True, stage="verifying", message=f"正在校验 {component.name}")
        digest = await asyncio.to_thread(file_digest, part, "sha1")
        if digest.lower() != component.sha1.lower():
            # 内容坏了，续传也救不回来，删掉让下次从头下
            part.unlink(missing_ok=True)
            self._done -= component.size
            raise ComponentError(
                f"{component.name} 校验失败（sha1 {digest} ≠ {component.sha1}），"
                "已删除损坏的文件，请重新下载"
            )
        if self.cancel_event.is_set():
            raise DownloadCancelled()

        self._emit(force=True, stage="extracting", message=f"正在解压 {component.name}")
        loop = asyncio.get_running_loop()

        def report(done: int, total: int) -> None:
            loop.call_soon_threadsafe(
                lambda: self._emit(
                    extractPercent=round(done / total * 100, 1),
                )
            )

        await asyncio.to_thread(extract_component, root, component, part, report)
        part.unlink(missing_ok=True)
        self._installed_in_job += component.size
        self.snapshot["extractPercent"] = None
        logger.info(f"官方模拟器组件已安装: {component.name} → {root}")

    async def _fetch_launcher(
        self, client: httpx.AsyncClient, root: Path, launcher: LauncherComponent
    ) -> None:
        part = root / DOWNLOADS_DIR / (launcher.file_name + ".part")
        self._emit(force=True, stage="downloading", message=f"正在下载 {launcher.name}")
        errors: list[str] = []
        for url in launcher.urls:
            try:
                await self._download_with_retry(client, url, part, launcher.size)
            except ComponentError as e:
                errors.append(str(e))
                continue
            digest = await asyncio.to_thread(file_digest, part, "sha256")
            if digest.lower() != launcher.sha256.lower():
                part.unlink(missing_ok=True)
                self._done = self._done_on_disk()
                errors.append(f"{url} 校验失败")
                continue
            target = launcher_apk(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(part, target)
            self._installed_in_job += launcher.size
            return
        # 轻量桌面是可选组件：下不到不拦整个安装，只记下来
        logger.warning(f"轻量桌面下载失败，跳过: {'；'.join(errors)}")
        self.snapshot["launcherError"] = "；".join(errors)


def _step_file(step: Component | LauncherComponent) -> str:
    if isinstance(step, LauncherComponent):
        return step.file_name
    return _archive_name(step)


_JOBS: dict[str, InstallJob] = {}


def get_job(root: str | Path) -> InstallJob | None:
    return _JOBS.get(root_key(root))


def find_job(job_id: str) -> InstallJob | None:
    for job in _JOBS.values():
        if job.job_id == job_id:
            return job
    return None


def start_job(job: InstallJob) -> InstallJob:
    """登记并在后台启动一个安装任务。同一根目录已有未结束的任务时直接返回那个。"""
    key = root_key(job.root)
    existing = _JOBS.get(key)
    if existing is not None and not existing.finished and existing.task is not None:
        return existing
    _JOBS[key] = job
    job.task = asyncio.create_task(job.run(), name=f"avd-install-{job.job_id}")
    return job


__all__ = [
    "AVD_DIR",
    "ComponentError",
    "DownloadCancelled",
    "InstallJob",
    "adb_exe",
    "avd_home",
    "check_disk_space",
    "component_installed",
    "download_file",
    "emulator_exe",
    "extract_component",
    "fetch_license",
    "file_digest",
    "find_job",
    "get_job",
    "install_status",
    "launcher_apk",
    "launcher_downloaded",
    "list_sources",
    "parse_license",
    "probe_sources",
    "read_emulator_version",
    "read_metadata",
    "root_from_manager_exe",
    "root_key",
    "sdk_dir",
    "start_job",
    "update_metadata",
    "write_metadata",
]
