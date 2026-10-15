#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""通过 BetterGI 公开 JS 接口校验本次米游社启动的角色。"""

from __future__ import annotations

import ctypes
import re
from pathlib import Path
from shutil import copy2

from app.utils import resource_path
from app.utils.io import ConfigCorruptedError, read_dict_file, read_file, write_file

_GROUP_PREFIX = "MAS米游社登录校验-"
_SCRIPT_PREFIX = "MASMiyousheLoginCheck-"
_ASSET_NAMES = ("main.js", "manifest.json", "settings.json")
_RUN_ID_PATTERN = re.compile(r"[a-f0-9]{32}")
_RES_TEMPLATE_DIR = resource_path("templates", "BetterGI")


def read_game_arguments(root_path: Path) -> list[str]:
    """透传 BetterGI 原有启动参数，按 Windows 命令行规则保留引号内容。

    只读取上游 ``genshinStartConfig.genshinStartArgs``，不改写上游设置；原有
    登录票据参数与本次票据冲突时拒绝启动，异常中不包含任何参数内容。
    """
    config_path = root_path / "User" / "config.json"
    config = read_dict_file(config_path)
    start_config = config.get("genshinStartConfig", {})
    if not isinstance(start_config, dict):
        raise ConfigCorruptedError(config_path)
    configured_arguments = start_config.get("genshinStartArgs", "")
    if not isinstance(configured_arguments, str):
        raise ConfigCorruptedError(config_path)
    if not configured_arguments.strip():
        return []

    # 添加虚拟程序名，避免 CommandLineToArgvW 把首个参数当作程序路径处理。
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    split_arguments = shell32.CommandLineToArgvW
    split_arguments.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    split_arguments.restype = ctypes.POINTER(ctypes.c_wchar_p)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    count = ctypes.c_int()
    parsed = split_arguments("game.exe " + configured_arguments, ctypes.byref(count))
    if not parsed:
        raise RuntimeError("无法解析 BetterGI 的游戏启动参数")
    try:
        arguments = [parsed[index] for index in range(1, count.value)]
    finally:
        kernel32.LocalFree(parsed)
    if any(
        re.match(r"^-*login_auth_ticket(?:=|$)", argument, re.IGNORECASE)
        for argument in arguments
    ):
        raise RuntimeError("请先移除 BetterGI 启动参数中已有的登录票据")
    return arguments


def write_login_check_group(root_path: Path, *, expected_uid: str, run_id: str) -> Path:
    """生成独立校验组，设置中只包含角色 UID 与本次运行标识。

    调用方单独执行返回路径的 ``stem``，收到本次脚本的 SUCCESS 结果后才可
    启动后续任务。角色识别由上游 ``genshin.uid()`` 完成，不读取游戏内部状态。
    """
    if not _RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("米游社登录校验运行标识无效")
    if not re.fullmatch(r"[1-9][0-9]*", expected_uid):
        raise ValueError("米游社登录校验角色 UID 无效")

    group_name = f"{_GROUP_PREFIX}{run_id}"
    script_folder = f"{_SCRIPT_PREFIX}{run_id}"
    group_path = root_path / "User" / "ScriptGroup" / f"{group_name}.json"
    script_dir = root_path / "User" / "JsScript" / script_folder
    if group_path.exists() or script_dir.exists():
        raise FileExistsError("米游社登录校验资产已存在，请重新运行任务")

    template_path = _RES_TEMPLATE_DIR / "MAS米游社登录校验.json"
    template = read_file(template_path)
    if (
        not isinstance(template, dict)
        or not isinstance(template.get("projects"), list)
        or len(template["projects"]) != 1
        or not isinstance(template["projects"][0], dict)
    ):
        raise RuntimeError("米游社登录校验配置组模板无效")
    template["name"] = group_name
    project = template["projects"][0]
    project["folderName"] = script_folder
    project["jsScriptSettingsObject"] = {
        "expectedUid": expected_uid,
        "runId": run_id,
    }

    script_dir.mkdir(parents=True)
    try:
        for name in _ASSET_NAMES:
            copy2(_RES_TEMPLATE_DIR / "MASMiyousheLoginCheck" / name, script_dir / name)
        write_file(group_path, template)
    except Exception:
        remove_login_check_group(root_path, group_path)
        raise
    return group_path


def remove_login_check_group(root_path: Path, group_path: Path) -> None:
    """清理本次校验组及三个自建脚本文件，保留目录内其他文件。"""
    run_id = group_path.stem.removeprefix(_GROUP_PREFIX)
    expected_path = root_path / "User" / "ScriptGroup" / f"{_GROUP_PREFIX}{run_id}.json"
    if (
        not _RUN_ID_PATTERN.fullmatch(run_id)
        or group_path.resolve() != expected_path.resolve()
    ):
        raise ValueError("米游社登录校验清理路径无效")
    group_path.unlink(missing_ok=True)
    script_dir = root_path / "User" / "JsScript" / f"{_SCRIPT_PREFIX}{run_id}"
    if script_dir.is_dir():
        for name in _ASSET_NAMES:
            (script_dir / name).unlink(missing_ok=True)
        if not any(script_dir.iterdir()):
            script_dir.rmdir()
