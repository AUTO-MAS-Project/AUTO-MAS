from __future__ import annotations

import base64
import json
from pathlib import Path


_CLIENT_RELATIVE_PATH = Path("Client/Binaries/Win64/Client-Win64-Shipping.exe")
_LAUNCHER_PREFERENCE_RELATIVE_PATH = Path("kr_game_cache/kr_game_temp.bin")


def _find_wegame_process_path_from_registry() -> Path:
    try:
        import winreg
    except ImportError as exc:
        raise FileNotFoundError("当前系统无法读取 WeGame 游戏路径") from exc

    uninstall_paths = (
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
    )
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for uninstall_path in uninstall_paths:
            try:
                uninstall_key = winreg.OpenKey(hive, uninstall_path)
            except OSError:
                continue
            with uninstall_key:
                for index in range(winreg.QueryInfoKey(uninstall_key)[0]):
                    try:
                        key_name = winreg.EnumKey(uninstall_key, index)
                        with winreg.OpenKey(uninstall_key, key_name) as entry:
                            display_name = str(winreg.QueryValueEx(entry, "DisplayName")[0])
                            install_location = str(
                                winreg.QueryValueEx(entry, "InstallLocation")[0]
                            )
                    except (OSError, TypeError):
                        continue
                    if (
                        "鸣潮" not in display_name
                        and "wuthering waves" not in display_name.lower()
                    ):
                        continue
                    candidate = Path(install_location) / _CLIENT_RELATIVE_PATH
                    if candidate.is_file():
                        return candidate

    raise FileNotFoundError("未找到 WeGame 鸣潮客户端路径，请重新导入启动器")


def _decode_official_launcher_process_path(launcher_path: Path) -> Path:
    if launcher_path.name.lower() != "launcher.exe":
        raise ValueError("请选择鸣潮官方启动器 launcher.exe 或 WeGame.exe")

    preference_path = launcher_path.parent / _LAUNCHER_PREFERENCE_RELATIVE_PATH
    if not preference_path.is_file():
        raise FileNotFoundError(
            "未找到鸣潮启动器的游戏路径记录，请重新导入正确的官方启动器"
        )
    try:
        encrypted = base64.b64decode(
            preference_path.read_text(encoding="ascii").strip(), validate=True
        )
        payload = json.loads(bytes(value ^ 0x63 for value in encrypted).decode("utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError("鸣潮启动器游戏路径记录无法解码，请重新导入启动器") from exc

    install_dir = payload.get("installDirPath") if isinstance(payload, dict) else None
    if not isinstance(install_dir, str) or not install_dir.strip():
        raise ValueError(
            "鸣潮启动器游戏路径记录缺少 installDirPath，请重新导入启动器"
        )

    process_path = Path(install_dir) / _CLIENT_RELATIVE_PATH
    if not process_path.is_file():
        raise FileNotFoundError(
            "启动器记录的鸣潮客户端不存在，请确认游戏已安装后重新导入启动器"
        )
    return process_path


def resolve_wuthering_waves_process_path(launcher_path: Path) -> Path:
    if not launcher_path.is_file():
        raise FileNotFoundError("鸣潮启动器不存在，请重新导入启动器")
    if launcher_path.name.lower() == "wegame.exe":
        return _find_wegame_process_path_from_registry()
    return _decode_official_launcher_process_path(launcher_path)
