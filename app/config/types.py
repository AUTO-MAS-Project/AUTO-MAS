"""内置 Annotated 字段类型（自动纠正 vs 校验）。

路径类内存为 ``pathlib.Path | None``，非法/空纠正为 ``None``；json 落盘走 pydantic 对 Path 的标准序列化。
日期时间为标准库 ``date`` / ``time`` / ``datetime``：加载与导出走 pydantic 标准序列化；
``date`` 字段若收到 ``datetime``，由 ConfigGroup 先强制目标时区再存为 ``date``。
"""

from __future__ import annotations

import json
import os
import shlex
from dataclasses import dataclass
from datetime import tzinfo
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


def _normalize_path_input(value: object) -> Path | None:
    """输入 → 展开后的绝对 Path；空 / 非法 → ``None``。"""
    if value is None:
        return None
    if isinstance(value, Path):
        if not value.parts:
            return None
        text = str(value)
    else:
        text = str(value).strip()
    if not text:
        return None
    try:
        path = _expand_raw_path(text)
        if path.suffix.lower() == ".lnk":
            if not path.is_file():
                return None
            target = _resolve_windows_shortcut(path)
            if target is None:
                return None
            path = _expand_raw_path(str(target))
        return path
    except (OSError, ValueError, RuntimeError):
        return None


# ──────────────────────────── 路径类（纠正 → None） ────────────────────────────


def _validate_file_path(value: object) -> Path | None:
    """已存在普通文件；禁止工作目录与 ``FORBIDDEN_*``。"""
    path = _normalize_path_input(value)
    if path is None:
        return None
    try:
        if not path.is_file() or _is_forbidden_path(path, allow_cwd=False):
            return None
    except (OSError, ValueError):
        return None
    return path


def _validate_folder_path(value: object) -> Path | None:
    """已存在目录；禁止工作目录与 ``FORBIDDEN_*``。"""
    path = _normalize_path_input(value)
    if path is None:
        return None
    try:
        if not path.is_dir() or _is_forbidden_path(path, allow_cwd=False):
            return None
    except (OSError, ValueError):
        return None
    return path


def _validate_script_root_path(value: object) -> Path | None:
    """脚本根目录；放行工作目录，仍禁系统目录。"""
    path = _normalize_path_input(value)
    if path is None:
        return None
    try:
        if not path.is_dir() or _is_forbidden_path(path, allow_cwd=True):
            return None
    except (OSError, ValueError):
        return None
    return path


_EXECUTABLE_SUFFIXES = {".exe", ".bat", ".cmd", ".com"}
"""可执行扩展名：Windows 可直接运行的程序 / 批处理。"""


def _validate_executable_path(value: object) -> Path | None:
    """可执行文件：在文件校验基础上补充后缀名校验；禁止工作目录与 ``FORBIDDEN_*``。"""
    path = _validate_file_path(value)
    if path is None:
        return None
    if path.suffix.lower() not in _EXECUTABLE_SUFFIXES:
        return None
    return path


def _validate_loose_path(value: object) -> Path | None:
    """可不存在；仅展开与格式清洗。"""
    return _normalize_path_input(value)


# ──────────────────────────── 时区标记 / date←datetime ────────────────────────────


@dataclass(frozen=True)
class TzMarker:
    """字段级时区覆盖；置于 ``Annotated[date, tz(...)]``（date 收到 datetime 时用）。"""

    tz: tzinfo


def tz(info: tzinfo) -> TzMarker:
    """声明字段目标时区（覆盖 ``ConfigEntry.timezone``）。"""
    return TzMarker(tz=info)


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
UrlString = Annotated[str, AfterValidator(_validate_url_string)]
KeyboardKeyString = Annotated[str, AfterValidator(_validate_keyboard_key)]
WindowsNameString = Annotated[str, AfterValidator(_validate_windows_name)]
CliArgumentString = Annotated[str, AfterValidator(_validate_cli_argument)]
CliArgumentListString = Annotated[str, AfterValidator(_validate_cli_argument_list)]

FilePath = Annotated[Path | None, BeforeValidator(_validate_file_path)]
"""已存在文件路径；展开 ``~``/``%ENV%``、解析 ``.lnk``；非法 / 空 → ``None``。"""

FolderPath = Annotated[Path | None, BeforeValidator(_validate_folder_path)]
"""已存在目录路径；非法 / 空 → ``None``。"""

ScriptRootPath = Annotated[Path | None, BeforeValidator(_validate_script_root_path)]
"""脚本根目录；放行工作目录；非法 / 空 → ``None``。"""

ExecutablePath = Annotated[Path | None, BeforeValidator(_validate_executable_path)]
"""可执行文件路径；展开 ``~``/``%ENV%``、解析 ``.lnk``；非法 / 空 / 非可执行后缀 → ``None``。"""

LoosePath = Annotated[Path | None, BeforeValidator(_validate_loose_path)]
"""宽松路径；可不存在，仅展开清洗；非法 / 空 → ``None``。"""
