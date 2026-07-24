"""内置 Annotated 字段类型（自动纠正 vs 校验）。

与一般字段同链；纠正型失败回退默认，校验型失败抛 ``ValueError``。
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

from pydantic import AfterValidator, BeforeValidator, Field, PlainSerializer

from .support.constants import DEFAULT_DATETIME, DEFAULT_FILE_PATH


def _to_string(value: object) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


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
    import pyautogui  # 延迟导入，避免无谓的依赖加载

    if text not in pyautogui.KEYBOARD_KEYS:
        raise ValueError(f"无效的键盘按键: {text}")
    return text


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


def _try_existing_file_path(value: object) -> Path | None:
    """将输入规范为「已存在的普通文件」绝对路径；空输入 → 默认；非法 → ``None``。"""
    if isinstance(value, Path):
        text = "" if value == DEFAULT_FILE_PATH else str(value)
    elif value is None:
        text = ""
    else:
        text = str(value).strip()
    if not text:
        return DEFAULT_FILE_PATH
    try:
        text = os.path.expandvars(os.path.expanduser(text))
        path = Path(text).resolve()
        # Windows 快捷方式：先要求 .lnk 自身是文件，再解析到目标文件
        if path.suffix.lower() == ".lnk":
            if not path.is_file():
                return None
            target = _resolve_windows_shortcut(path)
            if target is None:
                return None
            path = Path(os.path.expandvars(os.path.expanduser(str(target)))).resolve()
        # 仅普通文件：目录 / 不存在 / 特殊节点一律非法
        if not path.is_file():
            return None
        return path
    except (OSError, ValueError, RuntimeError):
        return None


def _validate_file_path(value: object) -> Path:
    """纠正型：非法 / 非文件 → ``DEFAULT_FILE_PATH``。"""
    resolved = _try_existing_file_path(value)
    return DEFAULT_FILE_PATH if resolved is None else resolved


def _serialize_file_path(value: Path) -> str:
    if value == DEFAULT_FILE_PATH or not value.parts:
        return ""
    return value.as_posix()


JsonDictString = Annotated[str, AfterValidator(_validate_json_dict_string)]
JsonListString = Annotated[str, AfterValidator(_validate_json_list_string)]
HHMMString = Annotated[str, AfterValidator(_validate_hhmm_string)]
YmdString = Annotated[str, AfterValidator(_validate_ymd_string)]
YmdHmString = Annotated[str, AfterValidator(_validate_ymd_hm_string)]
YmdHmsString = Annotated[str, AfterValidator(_validate_ymd_hms_string)]
UrlString = Annotated[str, AfterValidator(_validate_url_string)]
KeyboardKeyString = Annotated[str, AfterValidator(_validate_keyboard_key)]
NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveInt = Annotated[int, Field(ge=1)]
DayCount = Annotated[int, Field(ge=-1, le=9999)]
FilePath = Annotated[
    Path,
    BeforeValidator(_validate_file_path),
    PlainSerializer(_serialize_file_path, return_type=str),
]
"""内存 ``Path``、落盘 ``str``；展开 ``~`` / ``%ENV%``、解析 ``.lnk``；须为已存在文件，否则回落 ``DEFAULT_FILE_PATH``。"""
