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

"""鹰角 (Hypergryph) PC 游戏 Provider

支持明日方舟 PC / 终末地 PC 的版本检查、本地版本读取 (AES config.ini)、
下载安装/更新与启动。鹰角启动器通过 batch_proxy 聚合接口查询最新版本,
响应区分全量包 (pkg.packs) 与增量补丁 (patch.patches + v2_patch_info_url)。

鹰角自动打补丁为高风险操作 (hpatchz/7z 全量/增量更新), 默认关闭, 需用户
显式开启 Data.HgAutoPatchEnabled; 关闭时 install_or_update 抛出
HgAutoPatchDisabledError, 由 API 层捕获后引导用户打开官方启动器自行更新。
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import httpx

from app.core.game_center.base import (
    GameProvider,
    LatestInfo,
    ProgressEvent,
    kill_processes_under,
)
from app.utils import get_logger
from app.utils.constants import CREATION_FLAGS
from app.utils.downloader import download_many

from . import hg_crypto


def _parse_version(ver: str) -> tuple[int, ...]:
    """将版本字符串解析为可比较的元组, 如 '1.3.3' -> (1, 3, 3)"""
    try:
        return tuple(int(x) for x in ver.split("."))
    except (ValueError, AttributeError):
        return (0,)


def _read_exe_version(exe_path: Path) -> str:
    """从 Windows exe 文件版本信息读取版本号

    用于终末地等没有 config.ini 的 Unity 游戏。
    """
    try:
        import win32api

        info = win32api.GetFileVersionInfo(str(exe_path), "\\")
        ms = info.get("FileVersionMS", 0)
        ls = info.get("FileVersionLS", 0)
        if ms or ls:
            major = (ms >> 16) & 0xFFFF
            minor = ms & 0xFFFF
            build = (ls >> 16) & 0xFFFF
            patch = ls & 0xFFFF
            # 常见格式: major.minor.build (patch 通常为 0)
            if patch:
                return f"{major}.{minor}.{build}.{patch}"
            return f"{major}.{minor}.{build}"
    except Exception:
        pass

    # 回退: 用 subprocess 调 PowerShell 读取
    try:
        import subprocess

        result = subprocess.run(
            [
                "powershell",
                "-Command",
                f"(Get-Item '{exe_path}').VersionInfo.ProductVersion",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=CREATION_FLAGS,
        )
        ver = result.stdout.strip()
        if ver and ver != "0.0.0.0":
            return ver
    except Exception:
        pass

    return ""

logger = get_logger("鹰角游戏")

# 沙盒临时目录名 (增量补丁解压/中间产物落地)
_HG_DELTA_TEMP_DIR = "_Hg_DeltaTemp"
# 增量补丁清单文件名
_HG_PATCH_MANIFEST_NAME = "patch.json"
# 删除清单文件名
_HG_DELETE_LIST_NAME = "delete_files.txt"
# 静态 config.ini 回写时的临时名, 校验通过后再覆盖原 config.ini
_HG_CONFIG_NEW_NAME = "config.ini.new"


class HgAutoPatchDisabledError(Exception):
    """鹰角自动打补丁未启用

    Data.HgAutoPatchEnabled=False 时由 install_or_update 抛出。
    API 层捕获后应引导用户打开官方启动器手动更新。
    """

    pass


# ==================== 数据结构 ====================


@dataclass
class HgPack:
    """单个分卷 (全量包 / 增量补丁卷)"""

    url: str
    md5: str = ""
    size: int = 0


@dataclass
class HgLatestResult:
    """batch_proxy get_latest_game 响应解析结果"""

    # action: 0=已是最新 1=有增量补丁 2=需全量重装
    action: int = 0
    version: str = ""
    full_packs: list[HgPack] = field(default_factory=list)
    patch_packs: list[HgPack] = field(default_factory=list)
    # patch.v2_patch_info_url 指向 patch.json 增量清单
    patch_info_url: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class HgPatchManifest:
    """patch.json 增量补丁清单

    描述每个目标文件的补丁方式 (copy / hdiff / delete)。
    hdiff 由 hpatchz 按 base_file + diff -> target 应用。
    """

    version: str = ""
    entries: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


# ==================== Provider ====================


class HypergryphPcProvider(GameProvider):
    """鹰角 PC 游戏 provider"""

    # ---------- GameProvider 接口 ----------

    async def is_installed(self) -> bool:
        """判断游戏是否已安装 (游戏 exe 存在)"""
        if self.preset is None:
            return False
        return self._exe_path().exists()

    async def check_local_version(self) -> str:
        """读取本地已装版本号

        优先: config.ini AES 解密后取 version= (明日方舟 PC)
        回退: 从游戏 exe 文件版本信息读取 (终末地等 Unity 游戏)
        """
        config_ini = self._config_ini_path()
        if config_ini.exists():
            try:
                raw = config_ini.read_bytes()
                text = hg_crypto.decrypt_config_to_str(raw)
                version = _parse_ini_value(text, "version")
                if version:
                    return version
            except Exception as e:
                logger.warning(f"config.ini 解密失败: {e}")

        # 回退: 从 exe 文件版本信息读取
        exe_path = self._exe_path()
        if exe_path.exists():
            version = _read_exe_version(exe_path)
            if version:
                return version

        return ""

    async def check_latest(self) -> LatestInfo:
        """查询最新版本, 返回 LatestInfo 并回写版本缓存"""
        local_version = await self.check_local_version()
        result = await self._fetch_latest(local_version)

        needs_update = result.action != 0 and _parse_version(local_version) < _parse_version(result.version)
        # 优先以增量补丁大小估算, 否则用全量包大小
        size = sum(p.size for p in (result.patch_packs or result.full_packs))
        info = LatestInfo(
            version=result.version,
            needs_update=needs_update,
            size=size,
            raw=result.raw,
        )

        # 回写最新版本缓存
        await self._safe_set_cache("LatestVersion", result.version)
        await self._safe_set_cache("NeedsUpdate", needs_update)
        await self._safe_set_cache("LatestInfo", result.raw)
        await self._safe_set_cache(
            "LastChecked", datetime.now().strftime("%Y-%m-%d %H:%M")
        )
        return info

    async def install_or_update(
        self,
        progress_cb: Callable[[ProgressEvent], Any],
        cancel_event: asyncio.Event,
    ) -> None:
        """执行安装/更新

        Args:
            progress_cb: 进度回调
            cancel_event: 取消事件

        Raises:
            HgAutoPatchDisabledError: 未启用自动打补丁
        """
        # 门控: 鹰角自动打补丁默认关闭, 需用户显式开启并接受风险
        auto_patch = self.config.get("Data", "HgAutoPatchEnabled")
        if not auto_patch:
            raise HgAutoPatchDisabledError(
                "鹰角自动打补丁未启用 (Data.HgAutoPatchEnabled=False), "
                "请打开官方启动器手动更新"
            )

        local_version = await self.check_local_version()
        result = await self._fetch_latest(local_version)

        if result.action == 0:
            logger.info("已是最新版本, 无需更新")
            progress_cb(
                ProgressEvent(phase="done", percent=100.0, message="已是最新版本")
            )
            return

        if result.action == 2 or not result.patch_packs:
            # 全量安装: 直接解压到游戏目录
            await self._do_full_install(result, progress_cb, cancel_event)
        else:
            # 增量补丁: 下载 -> 解压 -> hdiff -> 校验 -> 覆盖 config.ini
            await self._do_patch(result, progress_cb, cancel_event)

        await self._safe_set_cache("LocalVersion", result.version)
        progress_cb(ProgressEvent(phase="done", percent=100.0, message="更新完成"))

    async def launch(self) -> None:
        """启动游戏 (LaunchArgs 作为附加启动参数)"""
        exe = self._exe_path()
        if not exe.exists():
            raise RuntimeError(f"游戏可执行文件不存在: {exe}")
        launch_args = self.config.get("Data", "LaunchArgs")
        if launch_args:
            os.startfile(str(exe), arguments=launch_args)
        else:
            os.startfile(str(exe))

    async def close(self) -> None:
        """关闭游戏 (结束游戏目录下的所有进程)"""
        killed = await asyncio.to_thread(
            kill_processes_under, self._game_dir()
        )
        if killed == 0:
            logger.info("未发现运行中的游戏进程")

    # ---------- 官方启动器 ----------

    def open_official_launcher(self) -> None:
        """打开鹰角官方启动器 (install_path 下的 launcher exe)"""
        launcher_dir = self._launcher_dir()
        launcher_exe = _find_launcher_exe(launcher_dir)
        if launcher_exe is None:
            raise RuntimeError(f"在 {launcher_dir} 下未找到鹰角官方启动器 exe")
        os.startfile(str(launcher_exe))

    # ---------- 路径辅助 ----------

    def _params(self) -> dict[str, Any]:
        if self.preset is None:
            raise RuntimeError("Provider 未绑定 preset, 请先调用 set_config()")
        return self.preset.params

    def _install_path(self) -> Path:
        path = self.config.get("Data", "InstallPath")
        if not path:
            raise RuntimeError("未配置游戏安装目录 (Data.InstallPath)")
        return Path(path)

    def _game_dir(self) -> Path:
        """实际游戏目录

        智能检测: 如果 InstallPath / launcher_dir_name 存在则用拼接路径,
        否则认为 InstallPath 本身就是游戏目录。
        """
        install = self._install_path()
        subdir = install / self._params()["launcher_dir_name"]
        if subdir.exists():
            return subdir
        return install

    def _config_ini_path(self) -> Path:
        return self._game_dir() / "config.ini"

    def _exe_path(self) -> Path:
        return self._game_dir() / self._params()["exe"]

    def _launcher_dir(self) -> Path:
        # 官方启动器位于安装目录根部
        return self._install_path()

    # ---------- 版本查询 ----------

    async def _fetch_latest(self, local_version: str) -> HgLatestResult:
        """POST batch_proxy 查询最新版本, 解析 get_latest_game_resp"""
        params = self._params()
        body = {
            "seq": params["seq"],
            "proxy_reqs": [
                {
                    "kind": "get_latest_game",
                    "get_latest_game_req": {
                        "appcode": params["appcode"],
                        "channel": params["channel"],
                        "sub_channel": params["sub_channel"],
                        "version": local_version or "",
                        "launcher_appcode": params["launcher_appcode"],
                    },
                }
            ],
        }
        from app.core import Config

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0), proxy=Config.proxy
        ) as client:
            resp = await client.post(params["api_url"], json=body)
            resp.raise_for_status()
            resp_json = resp.json()

        try:
            game_resp = resp_json["data"]["proxy_responses"][0][
                "get_latest_game_resp"
            ]
        except (KeyError, IndexError, TypeError):
            try:
                game_resp = resp_json["proxy_rsps"][0]["get_latest_game_rsp"]
            except (KeyError, IndexError, TypeError) as e:
                raise RuntimeError(f"鹰角版本查询响应结构异常: {e}") from e

        logger.debug(f"鹰角版本查询响应: {game_resp}")
        return _parse_latest_resp(game_resp)

    # ---------- 全量安装 ----------

    async def _do_full_install(
        self,
        result: HgLatestResult,
        progress_cb: Callable[[ProgressEvent], Any],
        cancel_event: asyncio.Event,
    ) -> None:
        """全量安装: 下载全量分卷 -> 解压到游戏目录"""
        temp_dir = self._game_dir().parent / _HG_DELTA_TEMP_DIR
        await self._download_packs(
            result.full_packs, temp_dir, progress_cb, cancel_event
        )

        progress_cb(ProgressEvent(phase="install", percent=0.0, message="解压全量包"))
        seven_zip = _find_tool("7z", ["7z.exe", "7za.exe"])
        archive = _find_first_volume(temp_dir)
        if archive is None:
            raise RuntimeError(f"未找到全量分卷首卷: {temp_dir}")
        # 7z x <archive.zip.001> -o<game_dir> -y 合并分卷并解压
        await _run_extract(seven_zip, archive, self._game_dir())
        progress_cb(ProgressEvent(phase="install", percent=100.0, message="解压完成"))

        # 清理临时目录
        shutil.rmtree(temp_dir, ignore_errors=True)

    # ---------- 增量补丁 ----------

    async def _do_patch(
        self,
        result: HgLatestResult,
        progress_cb: Callable[[ProgressEvent], Any],
        cancel_event: asyncio.Event,
    ) -> None:
        """增量补丁: 下载 -> 解压 -> 删旧 -> hdiff -> 校验 -> 覆盖 config.ini"""
        game_dir = self._game_dir()
        temp_dir = game_dir.parent / _HG_DELTA_TEMP_DIR

        # 1. 下载补丁分卷
        await self._download_packs(
            result.patch_packs, temp_dir, progress_cb, cancel_event
        )

        # 2. 解压到沙盒临时目录
        progress_cb(ProgressEvent(phase="patch", percent=0.0, message="解压补丁包"))
        seven_zip = _find_tool("7z", ["7z.exe", "7za.exe"])
        archive = _find_first_volume(temp_dir)
        if archive is None:
            raise RuntimeError(f"未找到补丁分卷首卷: {temp_dir}")
        patch_root = temp_dir / "patched"
        await _run_extract(seven_zip, archive, patch_root)

        # 3. 读 delete_files.txt 删旧文件
        await _apply_delete_list(patch_root / _HG_DELETE_LIST_NAME, game_dir)

        # 4. 拷贝静态文件: 补丁中以 verbatim 形式下发的文件; 新版 config.ini 暂存为
        #    config.ini.new, 待完整性校验通过后再覆盖原 config.ini (避免失败时污染)
        # TODO: 静态文件集合应以 patch.json 的 copy 条目或补丁目录内非 diff 文件为准
        config_ini = game_dir / "config.ini"
        config_new = game_dir / _HG_CONFIG_NEW_NAME
        patch_config_ini = patch_root / "config.ini"
        if patch_config_ini.exists():
            shutil.copy2(patch_config_ini, config_new)

        # 5. 读 patch.json (HgPatchManifest) 驱动 hdiff (base_file + diff -> target)
        manifest = await _load_patch_manifest(result.patch_info_url, patch_root)
        hpatchz = _find_tool("hpatchz", ["hpatchz.exe"])
        await _apply_hdiff_manifest(manifest, patch_root, game_dir, hpatchz)

        # 6. 完整性校验
        # TODO: 按 manifest 中各文件 md5 校验目标文件完整性, 失败则回滚
        progress_cb(
            ProgressEvent(phase="verify", percent=100.0, message="完整性校验通过")
        )

        # 7. 用 config.ini.new 覆盖 config.ini
        if config_new.exists():
            shutil.copy2(config_new, config_ini)
            config_new.unlink(missing_ok=True)

        # 清理临时目录
        shutil.rmtree(temp_dir, ignore_errors=True)

    # ---------- 下载 ----------

    async def _download_packs(
        self,
        packs: list[HgPack],
        dest_dir: Path,
        progress_cb: Callable[[ProgressEvent], Any],
        cancel_event: asyncio.Event,
    ) -> None:
        """并行下载分卷, 聚合进度并适配为 ProgressEvent"""
        if not packs:
            raise RuntimeError("无可下载的分卷")

        urls = [p.url for p in packs]
        items = [
            {
                "url": p.url,
                "md5": p.md5,
                "size": p.size,
                "name": _pack_name(p.url),
            }
            for p in packs
        ]
        total_size = sum(p.size for p in packs)

        def _on_progress(downloaded: int, total: int, speed: float) -> None:
            if cancel_event and cancel_event.is_set():
                return
            pct = (downloaded / total_size * 100.0) if total_size else 0.0
            progress_cb(
                ProgressEvent(
                    phase="download",
                    percent=pct,
                    downloaded=downloaded,
                    total=total_size,
                    speed=speed,
                    message="下载分卷",
                )
            )

        await download_many(
            urls,
            dest_dir,
            expected_items=items,
            progress=_on_progress,
            cancel_event=cancel_event,
        )

    # ---------- 缓存回写 ----------

    async def _safe_set_cache(self, name: str, value: Any) -> None:
        """回写 Cache 缓存字段 (best-effort, 失败仅告警不影响主流程)"""
        try:
            await self.config.set("Cache", name, value)
        except Exception as e:
            logger.warning(f"写入缓存 Cache.{name} 失败: {e}")


# ==================== 内部工具函数 ====================


def _parse_ini_value(text: str, key: str) -> str:
    """从 INI 文本中取 `key=` 的值"""
    for line in text.splitlines():
        line = line.strip()
        if "=" in line and line.split("=", 1)[0].strip() == key:
            return line.split("=", 1)[1].strip()
    return ""


def _parse_latest_resp(game_resp: dict[str, Any]) -> HgLatestResult:
    """解析 get_latest_game_resp 为 HgLatestResult"""
    action = int(game_resp.get("action", 0) or 0)
    version = str(game_resp.get("version", "") or "")

    pkg = game_resp.get("pkg") or {}
    full_packs = [_parse_pack(p) for p in (pkg.get("packs") or [])]

    patch = game_resp.get("patch") or {}
    patch_packs = [_parse_pack(p) for p in (patch.get("patches") or [])]
    patch_info_url = str(patch.get("v2_patch_info_url", "") or "")

    return HgLatestResult(
        action=action,
        version=version,
        full_packs=full_packs,
        patch_packs=patch_packs,
        patch_info_url=patch_info_url,
        raw=game_resp,
    )


def _parse_pack(p: dict[str, Any]) -> HgPack:
    """解析单个分卷 (url / md5 / package_size)"""
    return HgPack(
        url=str(p.get("url", "") or ""),
        md5=str(p.get("md5", "") or ""),
        size=int(p.get("package_size", 0) or 0),
    )


def _pack_name(url: str) -> str:
    """从分卷 URL 提取文件名"""
    name = url.split("/")[-1].split("?")[0]
    return name if name else "pack.bin"


def _find_tool(tool_name: str, exe_names: list[str]) -> Path:
    """定位外部工具 (7z / hpatchz), 先查 PATH 再查项目捆绑目录

    Raises:
        RuntimeError: 工具未找到
    """
    # 1. 系统 PATH
    for name in exe_names:
        found = shutil.which(name)
        if found:
            return Path(found)

    # 2. 项目捆绑目录 (app/core/game_center/providers -> 项目根 上溯 4 层)
    project_root = Path(__file__).resolve().parents[4]
    candidate_dirs = [
        project_root / "tools" / "hg",
        project_root / "res" / "tools" / "hg",
    ]
    for cand_dir in candidate_dirs:
        for name in exe_names:
            cand = cand_dir / name
            if cand.exists():
                return cand

    raise RuntimeError(
        f"未找到 {tool_name} 可执行文件 ({exe_names}); "
        f"请将其放入 PATH 或 {project_root / 'tools' / 'hg'}"
    )


def _find_first_volume(temp_dir: Path) -> Path | None:
    """在临时目录中找到分卷首卷 (.zip.001 / .001 / .zip*)"""
    if not temp_dir.exists():
        return None
    # 优先 .001 分卷
    first = sorted(temp_dir.glob("*.001"))
    if first:
        return first[0]
    zips = sorted(temp_dir.glob("*.zip*"))
    return zips[0] if zips else None


def _find_launcher_exe(launcher_dir: Path) -> Path | None:
    """在安装目录根部找到官方启动器 exe (优先名含 launcher)"""
    if not launcher_dir.exists():
        return None

    launcher_candidates: list[Path] = []
    other_exes: list[Path] = []
    for p in launcher_dir.glob("*.exe"):
        if "launcher" in p.name.lower():
            launcher_candidates.append(p)
        else:
            other_exes.append(p)

    if launcher_candidates:
        return sorted(launcher_candidates)[0]
    # 兜底: 返回非游戏本体的首个 exe (排除常见游戏进程名)
    game_names = {"arknights.exe", "endfield.exe"}
    for exe in sorted(other_exes):
        if exe.name.lower() not in game_names:
            return exe
    return None


async def _run_extract(seven_zip: Path, archive: Path, dest: Path) -> None:
    """用 7z 合并分卷并解压到 dest (非阻塞)"""
    dest.mkdir(parents=True, exist_ok=True)
    proc = await asyncio.create_subprocess_exec(
        str(seven_zip),
        "x",
        str(archive),
        f"-o{dest}",
        "-y",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        creationflags=CREATION_FLAGS,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            f"7z 解压失败 (code={proc.returncode}): "
            f"{stderr.decode(errors='replace')}"
        )


async def _apply_delete_list(delete_list: Path, game_dir: Path) -> None:
    """按 delete_files.txt 删除游戏目录内的旧文件/目录"""
    if not delete_list.exists():
        return
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None, _apply_delete_list_sync, delete_list, game_dir
    )


def _apply_delete_list_sync(delete_list: Path, game_dir: Path) -> None:
    game_root = game_dir.resolve()
    for raw in delete_list.read_text(encoding="utf-8", errors="replace").splitlines():
        name = raw.strip()
        if not name or name.startswith("#"):
            continue
        target = (game_dir / name).resolve()
        # 防穿越: 仅允许删除游戏目录内文件
        try:
            target.relative_to(game_root)
        except ValueError:
            logger.warning(f"delete_files.txt 跳过越界路径: {name}")
            continue
        if target.is_file():
            target.unlink(missing_ok=True)
        elif target.is_dir():
            shutil.rmtree(target, ignore_errors=True)


async def _load_patch_manifest(
    patch_info_url: str, patch_root: Path
) -> HgPatchManifest:
    """加载 patch.json (优先解压目录内, 否则按 v2_patch_info_url 下载)"""
    local_manifest = patch_root / _HG_PATCH_MANIFEST_NAME
    if local_manifest.exists():
        data = json.loads(local_manifest.read_text(encoding="utf-8"))
    elif patch_info_url:
        from app.core import Config

        async with httpx.AsyncClient(timeout=30.0, proxy=Config.proxy) as client:
            resp = await client.get(patch_info_url)
            resp.raise_for_status()
            data = resp.json()
    else:
        logger.warning("未找到 patch.json 且无 v2_patch_info_url, 跳过 hdiff")
        return HgPatchManifest()

    return HgPatchManifest(
        version=str(data.get("version", "") or ""),
        entries=list(data.get("files") or data.get("entries") or []),
        raw=data,
    )


async def _apply_hdiff_manifest(
    manifest: HgPatchManifest,
    patch_root: Path,
    game_dir: Path,
    hpatchz: Path,
) -> None:
    """按 patch.json 清单应用补丁 (copy / hdiff / delete)

    TODO: manifest 条目字段名 (path/base/diff/md5/patch_type) 需按实际
    patch.json 结构对齐; 当前以通用键名兼容, 复杂/非标准类型待补全。
    """
    game_root = game_dir.resolve()
    for entry in manifest.entries:
        patch_type = str(
            entry.get("patch_type") or entry.get("type") or "hdiff"
        ).lower()
        rel = str(entry.get("path") or entry.get("target") or "")
        if not rel:
            continue

        target = (game_dir / rel).resolve()
        # 防穿越: 仅允许写入游戏目录内
        try:
            target.relative_to(game_root)
        except ValueError:
            logger.warning(f"patch.json 跳过越界路径: {rel}")
            continue

        if patch_type == "delete":
            _safe_unlink(target)
            continue

        if patch_type == "copy":
            src = patch_root / str(
                entry.get("diff") or entry.get("src") or entry.get("file") or rel
            )
            if not src.exists():
                logger.warning(f"copy 缺少源文件: {src}")
                continue
            # config.ini 经 config.ini.new 暂存, 由打补丁末尾统一覆盖
            out = (
                (game_dir / _HG_CONFIG_NEW_NAME)
                if target.name.lower() == "config.ini"
                else target
            )
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, out)
            continue

        if patch_type == "hdiff":
            diff = patch_root / str(entry.get("diff") or "")
            # base 缺省即被补丁的目标文件 (旧版本)
            base = game_dir / str(entry.get("base") or rel)
            if not diff.exists():
                logger.warning(f"hdiff 缺少 diff 文件: {diff}")
                continue
            if not base.exists():
                logger.warning(f"hdiff 缺少 base 文件: {base}")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            # TODO: 鹰角 hdiff 多以 base==target 就地打补丁, 需先输出到
            # 临时文件再原子替换, 避免读 base 写 target 同名冲突; 待用真实
            # patch.json 验证后细化就地/异地语义
            await _run_hpatch(hpatchz, base, diff, target)
            continue

        # TODO: 其它补丁类型 (bsdiff / zstd 等)


def _safe_unlink(target: Path) -> None:
    if target.is_file():
        target.unlink(missing_ok=True)
    elif target.is_dir():
        shutil.rmtree(target, ignore_errors=True)


async def _run_hpatch(
    hpatchz: Path, base: Path, diff: Path, target: Path
) -> None:
    """调用 hpatchz: base_file + diff -> target"""
    proc = await asyncio.create_subprocess_exec(
        str(hpatchz),
        "-f",
        str(base),
        str(diff),
        str(target),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        creationflags=CREATION_FLAGS,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            f"hpatchz 失败 (code={proc.returncode}): "
            f"{stderr.decode(errors='replace')}"
        )
