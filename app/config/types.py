"""内置 Annotated 字段类型（自动纠正 vs 校验）。

与一般字段同链；纠正型失败回退默认，校验型失败抛 ``ValueError``。
路径类 Wire 形态统一为 ``str``，非法纠正回退空字符串。
"""

from __future__ import annotations

import json
import os
import shlex
from datetime import datetime
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

from pydantic import AfterValidator, BeforeValidator

from app.utils.constants import (
    FORBIDDEN_PATH_EXACT,
    FORBIDDEN_PATH_PREFIXES,
    ILLEGAL_CHARS,
    KEYBOARD_KEYS,
    RESERVED_NAMES,
)

# ──────────────────────────── 共享常量 ────────────────────────────

DEFAULT_DATETIME = datetime.strptime("2000-01-01 00:00:00", "%Y-%m-%d %H:%M:%S")
"""日期/时间校验失败时的默认回退时刻。"""


# ──────────────────────────── 基础工具 ────────────────────────────


def _to_string(value: object) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def _resolve_windows_shortcut(path: Path) -> Path | None:
    """解析 ``.lnk`` 目标；失败返回 ``None``。"""
    try:
        import win32com.client  # 延迟导入
    except ImportError:
        return None
    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(str(path))
        target = getattr(shortcut, "TargetPath", "") or ""
        if not target:
            return None
        return Path(target)
    except Exception:  # noqa: BLE001
        return None


def _expand_raw_path(text: str) -> Path:
    """展开 ``~`` / ``%ENV%`` 并 resolve。"""
    expanded = os.path.expandvars(os.path.expanduser(text.strip()))
    return Path(expanded).resolve()


def _is_forbidden_path(resolved: Path, *, allow_cwd: bool) -> bool:
    """系统目录 / 精确禁根；可选禁止工作目录。"""
    if len(resolved.parts) <= 1:
        return True
    forbidden = (
        FORBIDDEN_PATH_PREFIXES
        if allow_cwd
        else (*FORBIDDEN_PATH_PREFIXES, Path.cwd().resolve())
    )
    for item in forbidden:
        if (
            resolved == item
            or resolved.is_relative_to(item)
            or item.is_relative_to(resolved)
        ):
            return True
    return resolved in FORBIDDEN_PATH_EXACT


def _normalize_path_input(value: object) -> str:
    """输入 → 展开后的绝对路径字符串；空 → ``\"\"``；非法 → ``\"\"``。"""
    if isinstance(value, Path):
        text = "" if not value.parts else str(value)
    elif value is None:
        text = ""
    else:
        text = str(value).strip()
    if not text:
        return ""
    try:
        path = _expand_raw_path(text)
        if path.suffix.lower() == ".lnk":
            if not path.is_file():
                return ""
            target = _resolve_windows_shortcut(path)
            if target is None:
                return ""
            path = _expand_raw_path(str(target))
        return path.as_posix()
    except (OSError, ValueError, RuntimeError):
        return ""


# ──────────────────────────── 路径类（纠正 → \"\"） ────────────────────────────


def _validate_file_path(value: object) -> str:
    """已存在普通文件；禁止工作目录与 ``FORBIDDEN_*``。"""
    text = _normalize_path_input(value)
    if not text:
        return ""
    path = Path(text)
    try:
        if not path.is_file() or _is_forbidden_path(path, allow_cwd=False):
            return ""
    except (OSError, ValueError):
        return ""
    return path.as_posix()


def _validate_folder_path(value: object) -> str:
    """已存在目录；禁止工作目录与 ``FORBIDDEN_*``。"""
    text = _normalize_path_input(value)
    if not text:
        return ""
    path = Path(text)
    try:
        if not path.is_dir() or _is_forbidden_path(path, allow_cwd=False):
            return ""
    except (OSError, ValueError):
        return ""
    return path.as_posix()


def _validate_script_root_path(value: object) -> str:
    """脚本根目录；放行工作目录，仍禁系统目录。"""
    text = _normalize_path_input(value)
    if not text:
        return ""
    path = Path(text)
    try:
        if not path.is_dir() or _is_forbidden_path(path, allow_cwd=True):
            return ""
    except (OSError, ValueError):
        return ""
    return path.as_posix()


def _validate_emulator_path(value: object) -> str:
    """模拟器/游戏管理程序路径：须为已存在文件；禁止工作目录与 ``FORBIDDEN_*``。

    带 ``emulator_type`` 的管理器 exe 定位仍由业务层完成；此处只做路径清洗与存在性。
    """
    return _validate_file_path(value)


def _validate_loose_path(value: object) -> str:
    """可不存在；仅展开与格式清洗。"""
    return _normalize_path_input(value)


# ──────────────────────────── 字符串 / 其它 ────────────────────────────


def _validate_json_dict_string(value: object) -> str:
    text = _to_string(value)
    if not text:
        return ""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError("JSON 字典字符串解析失败") from e
    if not isinstance(parsed, dict):
        raise ValueError("JSON 不是字典类型")
    return text


def _validate_json_list_string(value: object) -> str:
    text = _to_string(value)
    if not text:
        return ""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError("JSON 列表字符串解析失败") from e
    if not isinstance(parsed, list):
        raise ValueError("JSON 不是列表类型")
    return text


def _validate_hhmm_string(value: object) -> str:
    text = _to_string(value)
    if not text:
        return DEFAULT_DATETIME.strftime("%H:%M")
    try:
        datetime.strptime(text, "%H:%M")
        return text
    except ValueError:
        return DEFAULT_DATETIME.strftime("%H:%M")


def _validate_ymd_string(value: object) -> str:
    text = _to_string(value)
    if not text:
        return DEFAULT_DATETIME.strftime("%Y-%m-%d")
    try:
        datetime.strptime(text, "%Y-%m-%d")
        return text
    except ValueError:
        return DEFAULT_DATETIME.strftime("%Y-%m-%d")


def _validate_ymd_hm_string(value: object) -> str:
    text = _to_string(value)
    if not text:
        return DEFAULT_DATETIME.strftime("%Y-%m-%d %H:%M")
    try:
        datetime.strptime(text, "%Y-%m-%d %H:%M")
        return text
    except ValueError:
        return DEFAULT_DATETIME.strftime("%Y-%m-%d %H:%M")


def _validate_ymd_hms_string(value: object) -> str:
    text = _to_string(value)
    if not text:
        return DEFAULT_DATETIME.strftime("%Y-%m-%d %H:%M:%S")
    try:
        datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        return text
    except ValueError:
        return DEFAULT_DATETIME.strftime("%Y-%m-%d %H:%M:%S")


def _validate_url_string(value: object) -> str:
    text = _to_string(value)
    if not text:
        return ""
    parsed = urlparse(text)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("URL 格式错误")
    return text


def _validate_keyboard_key(value: object) -> str:
    text = _to_string(value).lower()
    if not text:
        return ""
    if text not in KEYBOARD_KEYS:
        raise ValueError(f"无效的键盘按键: {text}")
    return text


def _validate_windows_name(value: object) -> str:
    """Windows 名称纠正（对齐 ``UserNameValidator``）。"""
    if not isinstance(value, str):
        return "默认用户名"
    text = value.strip().strip(".")
    text = "".join(ch for ch in text if ch not in ILLEGAL_CHARS)
    if not text or text.upper() in RESERVED_NAMES:
        return "默认用户名"
    if len(text) > 255:
        return text[:255]
    return text


def _validate_cli_argument(value: object) -> str:
    text = _to_string(value)
    if not text:
        return ""
    try:
        shlex.split(text.strip())
        return text
    except ValueError:
        return ""


def _validate_cli_argument_list(value: object) -> str:
    text = _to_string(value)
    if not text:
        return ""
    try:
        for segment in text.split("|"):
            segment = segment.strip()
            if not segment:
                continue
            param_str = segment.split("%", 1)[-1].strip()
            shlex.split(param_str)
        return text
    except ValueError:
        return ""


# ──────────────────────────── 导出类型 ────────────────────────────

JsonDictString = Annotated[str, AfterValidator(_validate_json_dict_string)]
JsonListString = Annotated[str, AfterValidator(_validate_json_list_string)]
HHMMString = Annotated[str, AfterValidator(_validate_hhmm_string)]
YmdString = Annotated[str, AfterValidator(_validate_ymd_string)]
YmdHmString = Annotated[str, AfterValidator(_validate_ymd_hm_string)]
YmdHmsString = Annotated[str, AfterValidator(_validate_ymd_hms_string)]
UrlString = Annotated[str, AfterValidator(_validate_url_string)]
KeyboardKeyString = Annotated[str, AfterValidator(_validate_keyboard_key)]
WindowsNameString = Annotated[str, AfterValidator(_validate_windows_name)]
CliArgumentString = Annotated[str, AfterValidator(_validate_cli_argument)]
CliArgumentListString = Annotated[str, AfterValidator(_validate_cli_argument_list)]

FilePath = Annotated[str, BeforeValidator(_validate_file_path)]
"""已存在文件路径（str）；展开 ``~``/``%ENV%``、解析 ``.lnk``；非法 → ``\"\"``。"""

FolderPath = Annotated[str, BeforeValidator(_validate_folder_path)]
"""已存在目录路径（str）；非法 → ``\"\"``。"""

ScriptRootPath = Annotated[str, BeforeValidator(_validate_script_root_path)]
"""脚本根目录（str）；放行工作目录；非法 → ``\"\"``。"""

EmulatorPath = Annotated[str, BeforeValidator(_validate_emulator_path)]
"""模拟器/游戏管理程序路径（str）；非法 → ``\"\"``。"""

LoosePath = Annotated[str, BeforeValidator(_validate_loose_path)]
"""宽松路径（str）；可不存在，仅展开清洗；非法 → ``\"\"``。"""
