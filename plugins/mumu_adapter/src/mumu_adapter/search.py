"""注册表搜索本机 MuMu → 未激活 MuMuGame。"""

from __future__ import annotations

import asyncio
import re
import winreg
from pathlib import Path

from .config import MuMuGame, locate_mumu
from .constants import _CMDLINE_PATH, _EMULATOR_TYPE


async def search() -> list[MuMuGame]:
    """按 EMULATOR_PATH_BOOK['mumu'] 在卸载项中搜索，直接构造未激活配置。"""
    from auto_mas_core.utils import EMULATOR_PATH_BOOK, get_logger

    book = EMULATOR_PATH_BOOK.get(_EMULATOR_TYPE)
    log = get_logger("模拟器搜索/mumu")
    if not book:
        return []

    def scan() -> list[MuMuGame]:
        def from_cmdline(value: str) -> str:
            s = value.strip()
            if not s:
                return ""
            m = re.match(r'^\s*"([^"]+)"', s)
            if m:
                return re.sub(r",\d+\s*$", "", m.group(1).strip()).strip()
            m = _CMDLINE_PATH.search(s)
            if m:
                return re.sub(r",\d+\s*$", "", m.group(1).strip()).strip()
            return s.strip().strip('"')

        found: list[MuMuGame] = []
        seen: set[str] = set()
        keywords = [k.casefold() for k in book.get("registry_display_keywords", [])]
        for hive, flag in (
            (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY),
            (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
            (winreg.HKEY_CURRENT_USER, 0),
        ):
            for sub in (
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
            ):
                try:
                    root = winreg.OpenKey(hive, sub, 0, winreg.KEY_READ | flag)
                except OSError:
                    continue
                i = 0
                while True:
                    try:
                        name = winreg.EnumKey(root, i)
                    except OSError:
                        break
                    i += 1
                    try:
                        key = winreg.OpenKey(root, name)
                    except OSError:
                        continue
                    try:
                        display, _ = winreg.QueryValueEx(key, "DisplayName")
                    except OSError:
                        winreg.CloseKey(key)
                        continue
                    disp = str(display)
                    if not any(k in disp.casefold() for k in keywords):
                        winreg.CloseKey(key)
                        continue
                    loc = ""
                    for field in ("InstallLocation", "DisplayIcon", "UninstallString"):
                        try:
                            raw, _ = winreg.QueryValueEx(key, field)
                            loc = from_cmdline(str(raw))
                            if loc:
                                break
                        except OSError:
                            continue
                    winreg.CloseKey(key)
                    hit = locate_mumu(loc)
                    manager = Path(hit) if hit is not None else None
                    if (
                        manager is None
                        or not manager.is_file()
                        or manager.name.casefold() != "mumumanager.exe"
                    ):
                        continue
                    dedupe = str(manager.resolve()).casefold()
                    if dedupe in seen:
                        continue
                    seen.add(dedupe)
                    resolved = manager.resolve()
                    label = book.get("name", "MuMu")
                    found.append(
                        MuMuGame(
                            info=MuMuGame.Info(
                                name=f"{label} ({resolved})",
                                path=resolved,
                                type="emulator",
                            )
                        )
                    )
                    log.info(f"找到 MuMu: {resolved}")
                winreg.CloseKey(root)
        log.info(f"搜索完成，共 {len(found)} 个")
        return found

    return await asyncio.to_thread(scan)
