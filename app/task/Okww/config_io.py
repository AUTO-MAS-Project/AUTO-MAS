#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   OK-WW 配置在 MAS 与脚本目录间的拷贝（对齐 General 脚本配置隔离模型）。

import shutil
from pathlib import Path

from app.models.config import OkwwConfig
from app.utils import get_logger

logger = get_logger("OK-WW 配置同步")


def mas_config_dir(script_id: str, config_owner: str) -> Path:
    return Path.cwd() / f"data/{script_id}/{config_owner}/ConfigFile"


def config_owner_for_mode(mode: str, user_uid: str) -> str:
    return "Default" if mode == "简洁" else user_uid


def script_config_path(script_config: OkwwConfig) -> Path:
    return Path(script_config.get("Script", "ConfigPath"))


def _is_folder_mode(script_config: OkwwConfig) -> bool:
    return script_config.get("Script", "ConfigPathMode") == "Folder"


def mas_config_ready(mas_dir: Path) -> bool:
    return mas_dir.is_dir() and any(mas_dir.iterdir())


def deploy_mas_config_to_script(
    script_config: OkwwConfig, script_id: str, config_owner: str
) -> None:
    """MAS ConfigFile → 脚本 ConfigPath（运行/配置会话前下发）。"""

    mas_dir = mas_config_dir(script_id, config_owner)
    target = script_config_path(script_config)
    if not mas_dir.exists():
        raise FileNotFoundError(f"未找到 MAS 侧 OK-WW 配置: {mas_dir}")

    target.parent.mkdir(parents=True, exist_ok=True)
    if _is_folder_mode(script_config):
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(mas_dir, target, dirs_exist_ok=True)
    else:
        src = mas_dir / target.name
        if not src.is_file():
            raise FileNotFoundError(f"未找到 MAS 侧配置文件: {src}")
        shutil.copy(src, target)
    logger.info(f"已从 MAS 下发 OK-WW 配置: {mas_dir} → {target}")


def pull_script_config_to_mas(
    script_config: OkwwConfig, script_id: str, config_owner: str
) -> None:
    """脚本 ConfigPath → MAS ConfigFile（配置会话结束后入库）。"""

    source = script_config_path(script_config)
    mas_dir = mas_config_dir(script_id, config_owner)
    if not source.exists():
        raise FileNotFoundError(f"未找到脚本侧 OK-WW 配置: {source}")

    shutil.rmtree(mas_dir, ignore_errors=True)
    mas_dir.mkdir(parents=True, exist_ok=True)
    if _is_folder_mode(script_config):
        shutil.copytree(source, mas_dir, dirs_exist_ok=True)
    else:
        shutil.copy(source, mas_dir / source.name)
    logger.success(f"已将 OK-WW 配置保存到 MAS: {source} → {mas_dir}")


def backup_script_config(
    script_config: OkwwConfig, temp_path: Path
) -> None:
    """备份脚本目录当前配置，供多用户任务结束后还原。"""

    source = script_config_path(script_config)
    temp_path.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        return
    if _is_folder_mode(script_config):
        shutil.copytree(source, temp_path, dirs_exist_ok=True)
    else:
        shutil.copy(source, temp_path / "config.temp")
    logger.info(f"已备份脚本侧 OK-WW 配置: {source} → {temp_path}")


def restore_script_config(script_config: OkwwConfig, temp_path: Path) -> None:
    """从 Temp 还原脚本目录配置。"""

    target = script_config_path(script_config)
    if _is_folder_mode(script_config):
        if not temp_path.exists():
            return
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(temp_path, target, dirs_exist_ok=True)
        shutil.rmtree(temp_path, ignore_errors=True)
    elif (temp_path / "config.temp").exists():
        shutil.copy(temp_path / "config.temp", target)
        shutil.rmtree(temp_path, ignore_errors=True)
    logger.info(f"已还原脚本侧 OK-WW 配置: {temp_path} → {target}")
