"""鸣潮 PC 客户端游戏根目录路径工具（Okww 专项）"""

from pathlib import Path

WUWA_GAME_ROOT_FOLDER = "Wuthering Waves Game"
WUWA_CLIENT_EXE_REL = Path("Client/Binaries/Win64/Client-Win64-Shipping.exe")
WUWA_CLIENT_PROCESS_NAME = WUWA_CLIENT_EXE_REL.name
INVALID_GAME_ROOT_MESSAGE = (
    f"选择游戏根目录错误，请选择 {WUWA_GAME_ROOT_FOLDER} 文件夹"
)


def build_wuthering_client_exe_path(game_root_folder: str) -> Path:
    norm = game_root_folder.replace("\\", "/").rstrip("/")
    return Path(f"{norm}/{WUWA_CLIENT_EXE_REL.as_posix()}")


def validate_wuthering_game_root_selection(picked_folder: str) -> tuple[bool, str]:
    exe_path = build_wuthering_client_exe_path(picked_folder)
    if exe_path.is_file():
        return True, ""
    return False, INVALID_GAME_ROOT_MESSAGE
