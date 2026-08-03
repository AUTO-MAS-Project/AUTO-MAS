#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.


import asyncio
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Literal
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

import aiofiles
import httpx

from app.models.emulator import DeviceBase, DeviceInfo, DeviceStatus
from app.utils import ProcessRunner, get_logger
from app.utils.constants import ARKNIGHTS_PACKAGE_NAME


logger = get_logger("明日方舟安装服务")

_BILIBILI_GAME_INFO_URL = (
    "https://line3-h5-mobile-api.biligame.com/"
    "game/center/h5/detail/gameinfo/v2"
    "?game_base_id=101772&client=h5&sdk_type=1"
)
_APKPURE_XAPK_URL = "https://d.apkpure.net/b/XAPK/{package_name}?version=latest"
_PACKAGE_DIR = Path.cwd() / "data" / "game_center" / "apk"


@dataclass(frozen=True)
class ArknightsPackageResource:
    """单个 MAA 服务器对应的 Android 包与下载资源。"""

    server: str
    display_name: str
    package_name: str
    download_url: str
    package_format: Literal["apk", "xapk"]
    resolve_bilibili_download: bool = False


ARKNIGHTS_PACKAGE_RESOURCES: dict[str, ArknightsPackageResource] = {
    "Official": ArknightsPackageResource(
        server="Official",
        display_name="官服",
        package_name=ARKNIGHTS_PACKAGE_NAME["Official"],
        download_url="https://ak.hypergryph.com/downloads/android_lastest",
        package_format="apk",
    ),
    "Bilibili": ArknightsPackageResource(
        server="Bilibili",
        display_name="B服",
        package_name=ARKNIGHTS_PACKAGE_NAME["Bilibili"],
        download_url=_BILIBILI_GAME_INFO_URL,
        package_format="apk",
        resolve_bilibili_download=True,
    ),
    "YoStarEN": ArknightsPackageResource(
        server="YoStarEN",
        display_name="国际服",
        package_name=ARKNIGHTS_PACKAGE_NAME["YoStarEN"],
        download_url=_APKPURE_XAPK_URL.format(
            package_name=ARKNIGHTS_PACKAGE_NAME["YoStarEN"]
        ),
        package_format="xapk",
    ),
    "YoStarJP": ArknightsPackageResource(
        server="YoStarJP",
        display_name="日服",
        package_name=ARKNIGHTS_PACKAGE_NAME["YoStarJP"],
        download_url=_APKPURE_XAPK_URL.format(
            package_name=ARKNIGHTS_PACKAGE_NAME["YoStarJP"]
        ),
        package_format="xapk",
    ),
    "YoStarKR": ArknightsPackageResource(
        server="YoStarKR",
        display_name="韩服",
        package_name=ARKNIGHTS_PACKAGE_NAME["YoStarKR"],
        download_url=_APKPURE_XAPK_URL.format(
            package_name=ARKNIGHTS_PACKAGE_NAME["YoStarKR"]
        ),
        package_format="xapk",
    ),
    "txwy": ArknightsPackageResource(
        server="txwy",
        display_name="繁中服",
        package_name=ARKNIGHTS_PACKAGE_NAME["txwy"],
        download_url=_APKPURE_XAPK_URL.format(
            package_name=ARKNIGHTS_PACKAGE_NAME["txwy"]
        ),
        package_format="xapk",
    ),
}


class _ArknightsPackageService:
    """根据 MAA 用户服务器，通过模拟器 ADB 卸载或安装明日方舟。"""

    def __init__(self) -> None:
        self._download_locks: dict[str, asyncio.Lock] = {}

    @staticmethod
    def get_resource(server: str) -> ArknightsPackageResource:
        """返回服务器对应资源；未知服务器不回退到其他包。"""

        try:
            return ARKNIGHTS_PACKAGE_RESOURCES[server]
        except KeyError as exc:
            raise ValueError(f"不支持的明日方舟服务器资源: {server}") from exc

    async def uninstall(
        self,
        emulator: DeviceBase,
        *,
        server: str,
        emulator_type: str,
        emulator_path: str,
        emulator_index: str,
    ) -> None:
        """通过 ``adb uninstall`` 卸载指定服务器的明日方舟。"""

        resource = self.get_resource(server)
        adb_path, serial = await self._prepare_device(
            emulator,
            emulator_type=emulator_type,
            emulator_path=emulator_path,
            emulator_index=emulator_index,
        )
        result = await ProcessRunner.run_process(
            adb_path,
            "-s",
            serial,
            "uninstall",
            resource.package_name,
            timeout=120,
        )
        output = self._process_output(result.stdout, result.stderr)
        output_lower = output.lower()

        if "success" in output_lower:
            logger.success(f"明日方舟{resource.display_name}卸载成功: {serial}")
            return
        if "unknown package" in output_lower or "not installed" in output_lower:
            logger.info(
                f"设备 {serial} 未安装明日方舟{resource.display_name}，跳过卸载"
            )
            return

        raise RuntimeError(
            f"adb uninstall 失败 (code={result.returncode}): {output or '无输出'}"
        )

    async def install(
        self,
        emulator: DeviceBase,
        *,
        server: str,
        emulator_type: str,
        emulator_path: str,
        emulator_index: str,
        proxy: httpx.Proxy | str | None,
    ) -> None:
        """下载并通过 ADB 安装指定服务器的明日方舟。"""

        resource = self.get_resource(server)
        adb_path, serial = await self._prepare_device(
            emulator,
            emulator_type=emulator_type,
            emulator_path=emulator_path,
            emulator_index=emulator_index,
        )
        package_path = await self._download_package(resource, proxy=proxy)

        logger.info(
            f"开始安装明日方舟{resource.display_name}: {serial} / {package_path.name}"
        )
        if resource.package_format == "apk":
            await self._install_apks(adb_path, serial, [package_path])
        else:
            await self._install_xapk(adb_path, serial, resource, package_path)

        logger.success(f"明日方舟{resource.display_name}安装成功: {serial}")

    async def _prepare_device(
        self,
        emulator: DeviceBase,
        *,
        emulator_type: str,
        emulator_path: str,
        emulator_index: str,
    ) -> tuple[Path, str]:
        """启动模拟器并返回可用的 ADB 路径和设备序列号。"""

        device_info: DeviceInfo
        if await emulator.getStatus(emulator_index) == DeviceStatus.ONLINE:
            devices = await emulator.getInfo(emulator_index)
            if emulator_index not in devices:
                raise RuntimeError(f"模拟器未返回实例信息: {emulator_index}")
            device_info = devices[emulator_index]
        else:
            logger.info(f"模拟器实例 {emulator_index} 未在线，正在启动")
            device_info = await emulator.open(emulator_index)

        serial = device_info.adb_address
        if not serial or serial == "Unknown":
            raise RuntimeError(f"无法获取模拟器实例 {emulator_index} 的 ADB 地址")

        adb_path = self._resolve_adb_path(
            emulator_type=emulator_type,
            emulator_path=emulator_path,
        )
        await self._ensure_connected(adb_path, serial)
        return adb_path, serial

    @staticmethod
    def _resolve_adb_path(*, emulator_type: str, emulator_path: str) -> Path:
        """按 6.0 游戏中心规则定位模拟器的 adb 可执行文件。"""

        configured_path = Path(emulator_path)
        base_dir = (
            configured_path if configured_path.is_dir() else configured_path.parent
        )

        candidates: list[Path] = []
        if emulator_type == "mumu":
            candidates.extend([base_dir / "shell" / "adb.exe", base_dir / "adb.exe"])
        else:
            candidates.append(base_dir / "adb.exe")

        for candidate in candidates:
            if candidate.is_file():
                return candidate

        system_adb = shutil.which("adb")
        if system_adb:
            return Path(system_adb)

        raise FileNotFoundError(
            f"无法找到 adb.exe，请检查模拟器配置路径: {emulator_path}"
        )

    async def _ensure_connected(self, adb_path: Path, serial: str) -> None:
        """确保指定 ADB 设备处于 ``device`` 状态。"""

        for attempt in range(1, 4):
            devices_result = await ProcessRunner.run_process(
                adb_path, "devices", timeout=10
            )
            if self._device_is_ready(devices_result.stdout, serial):
                return

            if ":" in serial:
                connect_result = await ProcessRunner.run_process(
                    adb_path, "connect", serial, timeout=15
                )
                logger.debug(
                    f"adb connect {serial}: "
                    f"{self._process_output(connect_result.stdout, connect_result.stderr)}"
                )

            if attempt < 3:
                await asyncio.sleep(1)

        raise RuntimeError(f"ADB 设备未就绪: {serial}")

    async def _download_package(
        self,
        resource: ArknightsPackageResource,
        *,
        proxy: httpx.Proxy | str | None,
    ) -> Path:
        """按服务器资源下载 APK/XAPK，并原子替换本地缓存。"""

        lock = self._download_locks.setdefault(resource.server, asyncio.Lock())
        async with lock:
            download_url = await self._resolve_download_url(resource, proxy=proxy)
            _PACKAGE_DIR.mkdir(parents=True, exist_ok=True)
            package_path = _PACKAGE_DIR / (
                f"{resource.package_name}.{resource.package_format}"
            )
            temp_path = package_path.with_name(
                f"{package_path.name}.{uuid4().hex}.download"
            )

            logger.info(
                f"开始下载明日方舟{resource.display_name}"
                f" {resource.package_format.upper()}: {download_url}"
            )
            downloaded = 0
            next_progress = 10

            try:
                timeout = httpx.Timeout(connect=15, read=120, write=30, pool=30)
                async with httpx.AsyncClient(
                    follow_redirects=True,
                    proxy=proxy,
                    timeout=timeout,
                ) as client:
                    async with client.stream("GET", download_url) as response:
                        response.raise_for_status()
                        total = int(response.headers.get("content-length", 0) or 0)

                        async with aiofiles.open(temp_path, "wb") as package_file:
                            async for chunk in response.aiter_bytes(
                                chunk_size=1024 * 1024
                            ):
                                if not chunk:
                                    continue
                                await package_file.write(chunk)
                                downloaded += len(chunk)

                                if total:
                                    progress = downloaded * 100 // total
                                    if progress >= next_progress:
                                        logger.info(
                                            f"明日方舟{resource.display_name}下载进度: "
                                            f"{progress}%"
                                        )
                                        next_progress = min(
                                            progress // 10 * 10 + 10, 100
                                        )

                if downloaded == 0:
                    raise RuntimeError(
                        f"明日方舟{resource.display_name}下载结果为空"
                    )

                temp_path.replace(package_path)
                logger.success(
                    f"明日方舟{resource.display_name}下载完成: {package_path}"
                )
                return package_path
            finally:
                if temp_path.exists():
                    temp_path.unlink()

    async def _resolve_download_url(
        self,
        resource: ArknightsPackageResource,
        *,
        proxy: httpx.Proxy | str | None,
    ) -> str:
        """解析需要动态获取的服务器下载链接。"""

        if not resource.resolve_bilibili_download:
            return resource.download_url

        timeout = httpx.Timeout(connect=15, read=30, write=30, pool=30)
        async with httpx.AsyncClient(
            follow_redirects=True,
            proxy=proxy,
            timeout=timeout,
            headers={
                "Referer": "https://app.biligame.com/",
                "User-Agent": "Mozilla/5.0 (Linux; Android 13)",
            },
        ) as client:
            response = await client.get(resource.download_url)
            response.raise_for_status()
            payload = response.json()

        if payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
            raise RuntimeError("哔哩哔哩游戏中心未返回有效的明日方舟资源")

        data = payload["data"]
        package_name = data.get("android_pkg_name")
        if package_name != resource.package_name:
            raise RuntimeError(
                "哔哩哔哩游戏中心返回的包名不匹配: "
                f"{package_name or '空'}"
            )

        download_url = data.get("download_link") or data.get("download_link2")
        if not isinstance(download_url, str) or not download_url.startswith("https://"):
            raise RuntimeError("哔哩哔哩游戏中心未返回有效的 APK 下载链接")
        return download_url

    async def _install_xapk(
        self,
        adb_path: Path,
        serial: str,
        resource: ArknightsPackageResource,
        xapk_path: Path,
    ) -> None:
        """解包 XAPK，安装 APK 分包并推送 OBB 资源。"""

        temp_dir = TemporaryDirectory(prefix=f"auto-mas-{resource.server}-")
        extract_dir = Path(temp_dir.name)
        try:
            apk_paths, obb_paths = await asyncio.to_thread(
                self._extract_xapk,
                xapk_path,
                extract_dir,
                resource,
            )
            await self._install_apks(adb_path, serial, apk_paths)
            if obb_paths:
                await self._push_obb_files(
                    adb_path,
                    serial,
                    resource.package_name,
                    obb_paths,
                )
        finally:
            await asyncio.to_thread(temp_dir.cleanup)

    @staticmethod
    def _extract_xapk(
        xapk_path: Path,
        extract_dir: Path,
        resource: ArknightsPackageResource,
    ) -> tuple[list[Path], list[Path]]:
        """安全提取 XAPK 中安装所需的 APK 与 OBB 文件。"""

        apk_paths: list[Path] = []
        obb_paths: list[Path] = []
        try:
            with ZipFile(xapk_path) as archive:
                for member in archive.infolist():
                    if member.is_dir():
                        continue

                    relative_path = PurePosixPath(member.filename.replace("\\", "/"))
                    if relative_path.is_absolute() or ".." in relative_path.parts:
                        raise RuntimeError(
                            f"XAPK 包含不安全路径: {member.filename}"
                        )

                    suffix = relative_path.suffix.lower()
                    if suffix not in (".apk", ".obb"):
                        continue

                    target_path = extract_dir.joinpath(*relative_path.parts)
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as source, target_path.open("wb") as target:
                        shutil.copyfileobj(source, target, length=1024 * 1024)

                    if suffix == ".apk":
                        apk_paths.append(target_path)
                    else:
                        obb_paths.append(target_path)
        except BadZipFile as exc:
            raise RuntimeError(f"明日方舟{resource.display_name} XAPK 文件无效") from exc

        if not apk_paths:
            raise RuntimeError(
                f"明日方舟{resource.display_name} XAPK 中未找到 APK 文件"
            )

        preferred_base_names = {"base.apk", f"{resource.package_name}.apk"}
        apk_paths.sort(
            key=lambda path: (
                0 if path.name in preferred_base_names else 1,
                path.name,
            )
        )
        obb_paths.sort(key=lambda path: path.name)
        return apk_paths, obb_paths

    async def _install_apks(
        self,
        adb_path: Path,
        serial: str,
        apk_paths: list[Path],
    ) -> None:
        """安装单 APK 或 split APK 集合。"""

        install_command = "install" if len(apk_paths) == 1 else "install-multiple"
        result = await ProcessRunner.run_process(
            adb_path,
            "-s",
            serial,
            install_command,
            "-r",
            *(str(path) for path in apk_paths),
            timeout=900,
        )
        output = self._process_output(result.stdout, result.stderr)
        if "success" not in output.lower():
            raise RuntimeError(
                f"adb {install_command} 失败 (code={result.returncode}): "
                f"{output or '无输出'}"
            )

    async def _push_obb_files(
        self,
        adb_path: Path,
        serial: str,
        package_name: str,
        obb_paths: list[Path],
    ) -> None:
        """将 XAPK 中的 OBB 资源推送到目标包目录。"""

        remote_dir = f"/sdcard/Android/obb/{package_name}"
        mkdir_result = await ProcessRunner.run_process(
            adb_path,
            "-s",
            serial,
            "shell",
            "mkdir",
            "-p",
            remote_dir,
            timeout=30,
        )
        if mkdir_result.returncode != 0:
            output = self._process_output(mkdir_result.stdout, mkdir_result.stderr)
            raise RuntimeError(f"创建 OBB 目录失败: {output or '无输出'}")

        for obb_path in obb_paths:
            push_result = await ProcessRunner.run_process(
                adb_path,
                "-s",
                serial,
                "push",
                str(obb_path),
                f"{remote_dir}/{obb_path.name}",
                timeout=900,
            )
            if push_result.returncode != 0:
                output = self._process_output(
                    push_result.stdout,
                    push_result.stderr,
                )
                raise RuntimeError(
                    f"推送 OBB 文件 {obb_path.name} 失败: {output or '无输出'}"
                )

    @staticmethod
    def _device_is_ready(devices_output: str, serial: str) -> bool:
        for line in devices_output.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0] == serial and parts[1] == "device":
                return True
        return False

    @staticmethod
    def _process_output(stdout: str, stderr: str) -> str:
        return "\n".join(part.strip() for part in (stdout, stderr) if part.strip())


ArknightsPackage = _ArknightsPackageService()
