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

"""miHoYo PC 游戏 provider (HoYoPlay)

通过 hyp-api 查询版本、全量包与增量补丁, 支持增量 hdiff 升级和全量安装。
绑定 GameConfig + GamePreset 后即可完成 检查 / 下载 / 打补丁 / 启动。
"""

from __future__ import annotations

import asyncio
import configparser
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Optional

import httpx

from app.utils import get_logger
from app.utils.downloader import download_file, download_many

from ..base import GameProvider, LatestInfo, ProgressEvent, kill_processes_under


def _parse_version(ver: str) -> tuple[int, ...]:
    """将版本字符串解析为可比较的元组, 如 '5.5.0' -> (5, 5, 0)"""
    try:
        return tuple(int(x) for x in ver.split("."))
    except (ValueError, AttributeError):
        return (0,)

logger = get_logger("游戏中心")

# ==================== 常量 ====================

# HoYoPlay 版本/包查询 API (免鉴权)
_HYP_API = "https://hyp-api.mihoyo.com/hyp/hyp-connect/api/getGamePackages"
# HoYoPlay 安装目录注册表 (HKCU)
_HYP_REG_KEY = r"Software\miHoYo\HYP\1_1"
_HYP_REG_VALUE = "InstallPath"


# ==================== 工具函数 ====================


def _find_tool(name: str) -> Path:
    """定位 7z.exe / hpatchz.exe

    优先读取 HoYoPlay 注册表 InstallPath, 其次 shutil.which。
    找不到时抛 RuntimeError 说明缺失工具。

    Args:
        name: 工具可执行文件名, 如 "7z.exe"

    Returns:
        工具完整路径

    Raises:
        RuntimeError: 未找到工具
    """
    candidates: list[Path] = []
    try:
        import winreg
    except ImportError:
        # 非 Windows 平台无 winreg, 跳过注册表查找
        pass
    else:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _HYP_REG_KEY) as key:
                install_path, _ = winreg.QueryValueEx(key, _HYP_REG_VALUE)
        except OSError:
            install_path = ""
        if install_path:
            base = Path(install_path)
            candidates.extend(
                [
                    base / name,
                    base / "launcher" / name,
                    base / "installer" / name,
                    base / "tools" / name,
                ]
            )
    which = shutil.which(name)
    if which:
        candidates.append(Path(which))
    for c in candidates:
        if c.is_file():
            return c
    raise RuntimeError(
        f"未找到 {name}: 请安装 HoYoPlay 启动器, 或将其所在目录加入 PATH"
    )


def _run_cmd(args: list[str], cwd: Optional[Path] = None) -> None:
    """同步执行外部命令, 非零退出码抛 RuntimeError"""
    proc = subprocess.run(args, capture_output=True, cwd=cwd)
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", "replace")
        raise RuntimeError(
            f"命令执行失败 ({proc.returncode}): {' '.join(args)}\n{stderr}"
        )


def _filename_from_url(url: str) -> str:
    """从下载地址提取文件名"""
    name = url.split("/")[-1].split("?")[0]
    return name if name else "download"


def _pkg_info(item: dict[str, Any]) -> dict[str, Any]:
    """从 game_pkg / patch 项提取 url/md5/size

    全量包字段直接挂在项上; 增量补丁字段挂在子键 ``pkg`` 下,
    这里统一兼容两种结构。
    """
    pkg = item.get("pkg", item)
    return {
        "url": pkg.get("url", ""),
        "md5": pkg.get("md5"),
        "size": int(pkg.get("size", 0) or 0),
    }


def _check_cancel(cancel_event: asyncio.Event) -> None:
    """取消事件已置位则抛 CancelledError"""
    if cancel_event.is_set():
        raise asyncio.CancelledError("安装/更新已取消")


def _resolve_inside(base: Path, rel: str) -> Optional[Path]:
    """将相对路径解析到 base 目录内, 越界时返回 None

    增量清单 (hdifffiles.txt / deletefiles.txt) 来自远端, 路径不可信,
    防穿越模式参考 hypergryph.py 的 _apply_delete_list_sync。
    """
    target = (base / rel).resolve()
    try:
        target.relative_to(base.resolve())
    except ValueError:
        return None
    return target


# ==================== Provider ====================


class MihoyoPcProvider(GameProvider):
    """miHoYo PC 游戏 provider (HoYoPlay 统一 launcher_id)"""

    # ---------- 版本查询 ----------

    async def is_installed(self) -> bool:
        """判断游戏是否已安装 (可执行文件存在)"""
        install_path = self.config.get("Data", "InstallPath")
        if not install_path:
            return False
        exe = self.preset.params.get("exe", "") if self.preset else ""
        if not exe:
            return False
        return (Path(install_path) / exe).is_file()

    async def check_local_version(self) -> str:
        """读取游戏目录下 config.ini 的 game_version, 未安装返回空串"""
        install_path = self.config.get("Data", "InstallPath")
        if not install_path:
            return ""
        config_ini = Path(install_path) / "config.ini"
        if not config_ini.is_file():
            return ""
        return await asyncio.to_thread(_read_game_version, config_ini)

    async def check_latest(self) -> LatestInfo:
        """查询最新版本及下载量, 返回 LatestInfo

        HoYoPlay API 的 main.major.version 是当前可下载的全量安装包版本,
        可能落后于已安装版本(因为增量补丁已将本地升级到更新版本)。
        真正的最新版本 = max(本地版本, API major.version)。
        """
        package = await self._fetch_game_package()
        major = package.get("main", {}).get("major", {})
        major_version = major.get("version", "")
        if not major_version:
            raise RuntimeError("API 未返回主版本号")

        local = await self.check_local_version()

        # latest_version = max(本地, API major), 因为 API 的全量包可能落后
        if _parse_version(local) > _parse_version(major_version):
            version = local
        else:
            version = major_version

        # 仅当本地 < 最新版本时才需要更新
        needs_update = _parse_version(local) < _parse_version(version)

        # 优先按本地版本匹配增量补丁, 否则取全量包
        patch = self._find_patch(package, local)
        if patch is not None:
            size = _pkg_info(patch)["size"]
        else:
            size = sum(
                _pkg_info(p)["size"] for p in major.get("game_pkgs", [])
            )
        return LatestInfo(
            version=version,
            needs_update=needs_update,
            size=size,
            raw=package,
        )

    # ---------- 安装/更新 ----------

    async def install_or_update(
        self,
        progress_cb: Callable[[ProgressEvent], Any],
        cancel_event: asyncio.Event,
    ) -> None:
        """执行安装/更新

        本地版本命中增量补丁则走 hdiff 升级, 否则全量安装。
        """
        try:
            package = await self._fetch_game_package()
            major = package.get("main", {}).get("major", {})
            latest = major.get("version", "")
            if not latest:
                raise RuntimeError("API 未返回主版本号")

            local = await self.check_local_version()
            install_path = self.config.get("Data", "InstallPath")
            if not install_path:
                raise RuntimeError("未配置安装路径 (Data/InstallPath)")
            install_dir = Path(install_path)
            install_dir.mkdir(parents=True, exist_ok=True)

            progress_cb(
                ProgressEvent(
                    phase="check",
                    percent=0.0,
                    message=f"本地 {local or '未安装'} -> 最新 {latest}",
                )
            )
            _check_cancel(cancel_event)

            # 命中增量补丁: 仅在已安装且版本不同时
            patch = (
                self._find_patch(package, local)
                if (local and local != latest)
                else None
            )
            if patch is not None:
                await self._apply_patch(
                    patch, install_dir, progress_cb, cancel_event
                )
            else:
                await self._install_full(
                    major, install_dir, progress_cb, cancel_event
                )

            # 回写版本号
            await self._write_local_version(install_dir, latest)
            progress_cb(
                ProgressEvent(
                    phase="done", percent=100.0, message=f"已更新到 {latest}"
                )
            )
            logger.info(f"miHoYo 游戏已更新到 {latest}")
        except asyncio.CancelledError:
            # 取消事件的进度推送由 GameCenterManager 统一发出 (phase=cancelled)
            raise
        except Exception as e:
            logger.exception("miHoYo 安装/更新失败")
            progress_cb(ProgressEvent(phase="error", message=str(e)))
            raise

    # ---------- 启动 ----------

    async def launch(self) -> None:
        """启动游戏可执行文件 (LaunchArgs 作为附加启动参数)"""
        install_path = self.config.get("Data", "InstallPath")
        if not install_path:
            raise RuntimeError("未配置安装路径 (Data/InstallPath)")
        exe = self.preset.params.get("exe", "") if self.preset else ""
        if not exe:
            raise RuntimeError("preset 缺少 exe")
        exe_path = Path(install_path) / exe
        if not exe_path.is_file():
            raise RuntimeError(f"游戏可执行文件不存在: {exe_path}")
        launch_args = self.config.get("Data", "LaunchArgs")
        if launch_args:
            os.startfile(str(exe_path), arguments=launch_args)
        else:
            os.startfile(str(exe_path))
        logger.info(f"启动游戏: {exe_path} {launch_args}".rstrip())

    async def close(self) -> None:
        """关闭游戏 (结束游戏目录下的所有进程)"""
        install_path = self.config.get("Data", "InstallPath")
        if not install_path:
            raise RuntimeError("未配置安装路径 (Data/InstallPath)")
        killed = await asyncio.to_thread(
            kill_processes_under, Path(install_path)
        )
        if killed == 0:
            logger.info("未发现运行中的游戏进程")

    # ---------- 内部: API ----------

    async def _fetch_game_package(self) -> dict[str, Any]:
        """请求 hyp-api, 返回首个 game_package"""
        if not self.preset:
            raise RuntimeError("provider 未绑定 preset")
        launcher_id = self.preset.params.get("launcher_id", "")
        game_id = self.preset.params.get("game_id", "")
        if not launcher_id or not game_id:
            raise RuntimeError("preset 缺少 launcher_id / game_id")
        params = {"launcher_id": launcher_id, "game_ids[]": game_id}
        from app.core import Config

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
            proxy=Config.proxy,
        ) as client:
            resp = await client.get(_HYP_API, params=params)
            resp.raise_for_status()
            data = resp.json()
        if data.get("retcode", -1) != 0:
            raise RuntimeError(
                f"miHoYo API 返回错误: {data.get('message', data)}"
            )
        packages = data.get("data", {}).get("game_packages", [])
        if not packages:
            raise RuntimeError("API 未返回 game_packages")
        return packages[0]

    def _find_patch(
        self, package: dict[str, Any], local_version: str
    ) -> Optional[dict[str, Any]]:
        """匹配本地版本的增量补丁, 无则返回 None"""
        if not local_version:
            return None
        patches = package.get("main", {}).get("patches", [])
        for p in patches:
            if p.get("version") == local_version:
                return p
        return None

    # ---------- 内部: 下载回调桥接 ----------

    def _make_dl_cb(
        self,
        progress_cb: Callable[[ProgressEvent], Any],
        phase: str,
        message: str,
    ) -> Callable[[int, int, float], Any]:
        """把下载器 (downloaded, total, speed) 回调桥接为 ProgressEvent"""

        def cb(downloaded: int, total: int, speed: float) -> None:
            percent = (downloaded / total * 100.0) if total else 0.0
            progress_cb(
                ProgressEvent(
                    phase=phase,
                    percent=percent,
                    downloaded=downloaded,
                    total=total,
                    speed=speed,
                    message=message,
                )
            )

        return cb

    # ---------- 内部: 增量升级 ----------

    async def _apply_patch(
        self,
        patch: dict[str, Any],
        install_dir: Path,
        progress_cb: Callable[[ProgressEvent], Any],
        cancel_event: asyncio.Event,
    ) -> None:
        """下载并应用单个增量 hdiff 补丁包"""
        info = _pkg_info(patch)
        tmp_dir = Path(tempfile.mkdtemp(prefix="mihoyo_patch_"))
        try:
            progress_cb(
                ProgressEvent(
                    phase="download", percent=0.0, message="下载增量补丁"
                )
            )
            patch_arch = tmp_dir / "patch.7z"
            await download_file(
                info["url"],
                patch_arch,
                expected_md5=info["md5"],
                expected_size=info["size"],
                progress=self._make_dl_cb(
                    progress_cb, "download", "下载增量补丁"
                ),
                cancel_event=cancel_event,
            )
            _check_cancel(cancel_event)

            # 解压增量包到临时目录
            progress_cb(
                ProgressEvent(
                    phase="patch", percent=0.0, message="解压增量补丁"
                )
            )
            extract_dir = tmp_dir / "extracted"
            extract_dir.mkdir()
            sevenz = _find_tool("7z.exe")
            await asyncio.to_thread(
                _run_cmd,
                [str(sevenz), "x", str(patch_arch), f"-o{extract_dir}", "-y"],
            )
            _check_cancel(cancel_event)

            # 按 hdifffiles.txt 逐个打补丁, 再按 deletefiles.txt 删除
            await self._apply_hdiffs(
                extract_dir, install_dir, progress_cb, cancel_event
            )
            await self._apply_deletes(extract_dir, install_dir)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    async def _apply_hdiffs(
        self,
        extract_dir: Path,
        install_dir: Path,
        progress_cb: Callable[[ProgressEvent], Any],
        cancel_event: asyncio.Event,
    ) -> None:
        """按 hdifffiles.txt 逐个调用 hpatchz 应用补丁"""
        hdiff_list = extract_dir / "hdifffiles.txt"
        if not hdiff_list.is_file():
            logger.warning("增量补丁缺少 hdifffiles.txt, 跳过 hdiff")
            return
        hpatchz = _find_tool("hpatchz.exe")
        entries = await asyncio.to_thread(_read_diff_entries, hdiff_list)
        total = len(entries)
        if total == 0:
            return
        for i, (game_rel, diff_rel) in enumerate(entries):
            _check_cancel(cancel_event)
            old_file = _resolve_inside(install_dir, game_rel)
            diff_file = _resolve_inside(extract_dir, diff_rel)
            if old_file is None or diff_file is None:
                logger.warning(
                    f"hdifffiles.txt 跳过越界路径: {game_rel};{diff_rel}"
                )
                continue
            if not diff_file.is_file():
                logger.debug(f"跳过缺失的补丁文件: {diff_rel}")
                continue
            if not old_file.parent.exists():
                old_file.parent.mkdir(parents=True, exist_ok=True)
            if not old_file.is_file():
                logger.warning(f"待补丁的源文件不存在, 跳过: {game_rel}")
                continue
            await asyncio.to_thread(
                _patch_one_file, hpatchz, old_file, diff_file
            )
            percent = (i + 1) / total * 100.0
            progress_cb(
                ProgressEvent(
                    phase="patch",
                    percent=percent,
                    message=f"应用补丁 {i + 1}/{total}",
                )
            )

    async def _apply_deletes(
        self, extract_dir: Path, install_dir: Path
    ) -> None:
        """按 deletefiles.txt 删除过期文件"""
        del_list = extract_dir / "deletefiles.txt"
        if not del_list.is_file():
            return
        rels = await asyncio.to_thread(_read_lines, del_list)
        for rel in rels:
            rel = rel.strip().lstrip("\\/")
            if not rel:
                continue
            target = _resolve_inside(install_dir, rel)
            if target is None:
                logger.warning(f"deletefiles.txt 跳过越界路径: {rel}")
                continue
            if target.is_file():
                try:
                    target.unlink()
                except OSError as e:
                    logger.warning(f"删除失败 {rel}: {e}")

    # ---------- 内部: 全量安装 ----------

    async def _install_full(
        self,
        major: dict[str, Any],
        install_dir: Path,
        progress_cb: Callable[[ProgressEvent], Any],
        cancel_event: asyncio.Event,
    ) -> None:
        """下载全量分卷并解压到游戏目录"""
        pkgs = major.get("game_pkgs", [])
        if not pkgs:
            raise RuntimeError("API 未返回全量包 game_pkgs")
        urls: list[str] = []
        expected_items: list[dict[str, Any]] = []
        for p in pkgs:
            info = _pkg_info(p)
            name = _filename_from_url(info["url"])
            urls.append(info["url"])
            expected_items.append(
                {
                    "url": info["url"],
                    "md5": info["md5"],
                    "size": info["size"],
                    "name": name,
                }
            )
        tmp_dir = Path(tempfile.mkdtemp(prefix="mihoyo_full_"))
        try:
            progress_cb(
                ProgressEvent(
                    phase="download", percent=0.0, message="下载全量包"
                )
            )
            files = await download_many(
                urls,
                tmp_dir,
                expected_items=expected_items,
                progress=self._make_dl_cb(
                    progress_cb, "download", "下载全量包"
                ),
                cancel_event=cancel_event,
            )
            _check_cancel(cancel_event)

            # 多分卷取第一个分卷, 7z 自动续接 .001/.002...
            progress_cb(
                ProgressEvent(
                    phase="install", percent=0.0, message="解压安装"
                )
            )
            sevenz = _find_tool("7z.exe")
            await asyncio.to_thread(
                _run_cmd,
                [str(sevenz), "x", str(files[0]), f"-o{install_dir}", "-y"],
            )
            progress_cb(
                ProgressEvent(
                    phase="install", percent=100.0, message="解压完成"
                )
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # ---------- 内部: 版本回写 ----------

    async def _write_local_version(
        self, install_dir: Path, version: str
    ) -> None:
        """回写游戏目录 config.ini 的 game_version"""
        config_ini = install_dir / "config.ini"
        await asyncio.to_thread(_write_game_version, config_ini, version)


# ==================== 模块级辅助 (线程内执行) ====================


def _read_game_version(config_ini: Path) -> str:
    """用 configparser 读取 config.ini 的 game_version"""
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(config_ini, encoding="utf-8-sig")
    for section in parser.sections():
        for key in ("game_version", "GameVersion"):
            if parser.has_option(section, key):
                return parser.get(section, key).strip()
    return ""


def _write_game_version(config_ini: Path, version: str) -> None:
    """回写 config.ini, 缺 [General] 段时自动创建"""
    parser = configparser.ConfigParser(interpolation=None)
    if config_ini.is_file():
        parser.read(config_ini, encoding="utf-8-sig")
    if not parser.has_section("General"):
        parser.add_section("General")
    parser.set("General", "game_version", version)
    with open(config_ini, "w", encoding="utf-8") as f:
        parser.write(f)


def _read_lines(path: Path) -> list[str]:
    """读取文件为去行尾的行列表"""
    with open(path, "r", encoding="utf-8-sig") as f:
        return f.read().splitlines()


def _read_diff_entries(path: Path) -> list[tuple[str, str]]:
    """解析 hdifffiles.txt

    每行格式 ``<游戏相对路径>;<补丁相对路径>``, 补丁相对路径以 .hdiff 结尾。
    仅单列且以 .hdiff 结尾时, 游戏路径为去掉后缀的列本身。
    跳过空行、注释行及版本头等非 .hdiff 行。

    Returns:
        (game_rel, diff_rel) 列表, 路径均为相对且去除前导分隔符
    """
    entries: list[tuple[str, str]] = []
    for line in _read_lines(path):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(";")
        if len(parts) >= 2:
            game_rel = parts[0].strip().lstrip("\\/")
            diff_rel = parts[1].strip().lstrip("\\/")
            if diff_rel.lower().endswith(".hdiff"):
                entries.append((game_rel, diff_rel))
            # 其余 (如 1.0;2.0 版本头) 跳过
        elif len(parts) == 1:
            name = parts[0].strip().lstrip("\\/")
            if name.lower().endswith(".hdiff"):
                entries.append((name[: -len(".hdiff")], name))
    return entries


def _patch_one_file(
    hpatchz: Path, old_file: Path, diff_file: Path
) -> None:
    """用 hpatchz 给单个文件打补丁 (写临时输出后替换原文件)"""
    tmp_out = old_file.with_name(old_file.name + ".patched.tmp")
    if tmp_out.exists():
        tmp_out.unlink()
    _run_cmd([str(hpatchz), str(old_file), str(diff_file), str(tmp_out)])
    os.replace(tmp_out, old_file)
