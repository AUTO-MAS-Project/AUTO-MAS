"""内置 Annotated 字段类型（自动纠正 vs 校验）。

路径类内存为 ``pathlib.Path | None``；``path_policy`` 声明类型、后缀、存在性及阻止目录。
路径导出沿用 Pydantic 原生序列化：``Path`` 转字符串，``None`` 保留为空值。
日期时间统一为完整 ``datetime``：Pydantic 写入时归一为 UTC，读取时按 ``tz`` 预设转换。
"""

from __future__ import annotations

import json
import os
import re
import shlex
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import timezone, tzinfo
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import (
    BaseModel,
    BeforeValidator,
    GetCoreSchemaHandler,
)
from pydantic_core import PydanticUseDefault, core_schema

from app.utils.constants import (
    FORBIDDEN_PATH_EXACT,
    FORBIDDEN_PATH_PREFIXES,
    ILLEGAL_CHARS,
    KEYBOARD_KEYS,
    RESERVED_NAMES,
)

type PathKind = Literal["file", "folder", "any"]


def _path_for_comparison(path: Path) -> Path:
    """统一 Windows 长路径前缀以比较路径关系，实际 Path 保留原有 I/O 能力。"""
    text = path.as_posix()
    if os.name == "nt":
        if text.lower().startswith("//?/unc/"):
            return Path("//" + text[8:])
        if text.startswith(("//?/", "//./")) and text[5:7] == ":/":
            return Path(text[4:])
    return path


class PathBlockPreset(Enum):
    """来源框架的特殊目录边界；在校验时展开，不传递给 UI。"""

    ROOTS = "roots"
    SYSTEM = "system"
    APP = "app"
    PROGRAM_FILES_ROOTS = "program_files_roots"


SYSTEM_BLOCKED_DIRS = (
    PathBlockPreset.ROOTS,
    PathBlockPreset.SYSTEM,
    PathBlockPreset.PROGRAM_FILES_ROOTS,
)
STANDARD_BLOCKED_DIRS = (*SYSTEM_BLOCKED_DIRS, PathBlockPreset.APP)


@dataclass(frozen=True, kw_only=True)
class PathPolicy:
    """路径声明与 UI 选择提示共用元数据，阻止目录只由后端执行。

    普通阻止目录覆盖自身与后代，预设保留来源的系统、工作目录及根目录边界。
    ``any`` 且允许不存在时无法判断实体类型，后缀只约束已知文件。
    """

    kind: PathKind
    extensions: Sequence[str] = ()
    must_exist: bool = False
    blocked_dirs: Sequence[str | Path | PathBlockPreset] = ()

    def __post_init__(self) -> None:
        if self.kind not in {"file", "folder", "any"}:
            raise ValueError("路径类型仅支持 file、folder、any")
        if not isinstance(self.must_exist, bool):
            raise TypeError("must_exist 必须为布尔值")
        if isinstance(self.extensions, (str, bytes)) or not isinstance(
            self.extensions, Sequence
        ):
            raise TypeError("extensions 必须为后缀字符串列表或元组")
        extensions = []
        for extension in self.extensions:
            if not isinstance(extension, str):
                raise TypeError("后缀必须为字符串")
            extension = extension.strip().removeprefix(".").lower()
            if (
                not extension
                or any(not part for part in extension.split("."))
                or any(c.isspace() or c in '\\/:*?[]{}<>|"\x00' for c in extension)
            ):
                raise ValueError("后缀必须为具体扩展名，不支持通配符或路径")
            extensions.append(extension)
        if self.kind == "folder" and extensions:
            raise ValueError("目录类型不能声明文件后缀")
        if isinstance(self.blocked_dirs, (str, bytes)) or not isinstance(
            self.blocked_dirs, Sequence
        ):
            raise TypeError("blocked_dirs 必须为目录或预设的列表或元组")
        blocked_dirs = []
        for directory in self.blocked_dirs:
            if not isinstance(directory, (str, Path, PathBlockPreset)):
                raise TypeError("阻止目录必须为字符串、Path 或 PathBlockPreset")
            if isinstance(directory, str):
                if not directory.strip() or "\x00" in directory:
                    raise ValueError("阻止目录不能为空或包含空字符")
                directory = Path(directory.strip())
            blocked_dirs.append(directory)
        object.__setattr__(self, "extensions", tuple(dict.fromkeys(extensions)))
        object.__setattr__(self, "blocked_dirs", tuple(dict.fromkeys(blocked_dirs)))

    def __get_pydantic_core_schema__(self, source, handler: GetCoreSchemaHandler):
        def normalize(value):
            path = normalize_path_input(value)
            if path is None:
                return None
            try:
                # 校验时解析预设及普通目录，保留动态工作目录和符号链接的含义。
                blocked_trees: list[Path] = []
                blocked_overlaps: list[Path] = []
                blocked_exact: list[Path] = []
                for rule in self.blocked_dirs:
                    if rule is PathBlockPreset.SYSTEM:
                        blocked_overlaps.extend(FORBIDDEN_PATH_PREFIXES)
                    elif rule is PathBlockPreset.APP:
                        blocked_overlaps.append(Path.cwd())
                    elif rule is PathBlockPreset.PROGRAM_FILES_ROOTS:
                        blocked_exact.extend(FORBIDDEN_PATH_EXACT)
                    elif isinstance(rule, (str, Path)):
                        blocked_trees.append(_expand_raw_path(str(rule)))
                blocked_trees = [
                    _path_for_comparison(p.resolve()) for p in blocked_trees
                ]
                blocked_overlaps = [
                    _path_for_comparison(p.resolve()) for p in blocked_overlaps
                ]
                blocked_exact = [
                    _path_for_comparison(p.resolve()) for p in blocked_exact
                ]

                def allowed(candidate: Path, *, directory: bool) -> bool:
                    if (directory and self.kind == "file") or (
                        not directory and self.kind == "folder"
                    ):
                        return False
                    if not directory and self.extensions:
                        if not any(
                            candidate.name.lower().endswith("." + extension)
                            for extension in self.extensions
                        ):
                            return False
                    compared = _path_for_comparison(candidate)
                    if PathBlockPreset.ROOTS in self.blocked_dirs and compared == Path(
                        compared.anchor
                    ):
                        return False
                    return not (
                        compared in blocked_exact
                        or any(compared.is_relative_to(p) for p in blocked_trees)
                        or any(
                            compared.is_relative_to(p) or p.is_relative_to(compared)
                            for p in blocked_overlaps
                        )
                    )

                is_file, is_dir = path.is_file(), path.is_dir()
                if (is_file and allowed(path, directory=False)) or (
                    is_dir and allowed(path, directory=True)
                ):
                    return path
                if not self.must_exist:
                    if not path.exists() and (
                        allowed(path, directory=False) or allowed(path, directory=True)
                    ):
                        return path
                    return None
                # 仅要求存在的目录规则尝试一次去后缀；现有目录完整保留。
                if self.kind != "file" and not is_dir:
                    candidate = path.with_suffix("").resolve()
                    if (
                        candidate != path
                        and candidate.is_dir()
                        and allowed(candidate, directory=True)
                    ):
                        return candidate
            except (OSError, ValueError, RuntimeError):
                return None
            return None

        return core_schema.no_info_before_validator_function(
            normalize,
            handler(source),
        )


def path_policy(
    *,
    kind: PathKind,
    extensions: Sequence[str] = (),
    must_exist: bool = False,
    blocked_dirs: Sequence[str | Path | PathBlockPreset] = (),
) -> PathPolicy:
    """声明路径的四项属性；选择提示直接从同一份元数据派生。"""
    return PathPolicy(
        kind=kind,
        extensions=extensions,
        must_exist=must_exist,
        blocked_dirs=blocked_dirs,
    )


# ──────────────────────────── 基础工具 ────────────────────────────


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


def normalize_path_input(value: object) -> Path | None:
    """输入 → 绝对 Path；统一展开、解析符号链接及 Windows 快捷方式。"""
    if value is None or not isinstance(value, (str, os.PathLike)):
        return None
    if isinstance(value, Path) and not value.parts:
        return None
    try:
        text = os.fspath(value)
        if not isinstance(text, str) or not text.strip() or "\x00" in text:
            return None
        path = _expand_raw_path(text)
        visited: set[Path] = set()
        while path.suffix.lower() == ".lnk" and not path.is_dir():
            if path in visited or not path.is_file():
                return None
            visited.add(path)
            target = _resolve_windows_shortcut(path)
            if not target or not str(target).strip():
                return None
            expanded = Path(os.path.expandvars(os.path.expanduser(str(target).strip())))
            if not expanded.is_absolute():
                expanded = path.parent / expanded
            path = expanded.resolve()
        return path
    except (OSError, ValueError, RuntimeError):
        return None


# ──────────────────────────── 日期时间读取预设 ────────────────────────────


@dataclass(frozen=True)
class TzMarker[TModel: BaseModel]:
    """读取时使用的固定偏移时区，或接收所属 Pydantic 分组的只读方法。"""

    tz: tzinfo | Callable[[TModel], tzinfo]

    def resolve(self, model: TModel) -> timezone:
        """每次读取重新解析；预设不得修改配置或递归读取自身字段。"""
        zone = self.tz(model) if callable(self.tz) else self.tz
        if not isinstance(zone, timezone):
            raise ValueError("读取时区预设必须返回固定偏移 timezone 对象")
        return zone


def tz[TModel: BaseModel](
    info: tzinfo | Callable[[TModel], tzinfo],
) -> TzMarker[TModel]:
    """声明读取时区；写入不调用预设，无时区输入始终按 UTC 解释。"""
    return TzMarker(tz=info)


# ──────────────────────────── 字符串 / 其它 ────────────────────────────


def _validate_json_dict_string(value: object) -> str:
    """保留有效对象字符串，空值、类型错误及解析失败沿用 dev 的空对象回退。"""
    if not isinstance(value, str):
        return "{ }"
    try:
        return value if isinstance(json.loads(value), dict) else "{ }"
    except ValueError:
        return "{ }"


def _validate_json_list_string(value: object) -> str:
    """保留有效数组字符串，空值、类型错误及解析失败沿用 dev 的空数组回退。"""
    if not isinstance(value, str):
        return "[ ]"
    try:
        return value if isinstance(json.loads(value), list) else "[ ]"
    except ValueError:
        return "[ ]"


def _validate_url_string(value: object) -> str:
    """沿用 dev 默认 URL 策略：协议与网络位置齐全时原样保留，否则清空。"""
    if not isinstance(value, str):
        return ""
    try:
        parsed = urlparse(value)
        return value if parsed.scheme and parsed.netloc else ""
    except ValueError:
        return ""


def _validate_keyboard_key(value: object) -> str:
    """按键转小写；非法输入交由 Pydantic 使用字段声明的合法默认键位。"""
    if isinstance(value, str):
        key = value.lower()
        if key in KEYBOARD_KEYS:
            return key
    raise PydanticUseDefault()


def _validate_windows_name(value: object) -> str:
    """沿用 dev 名称规则；清理和截断后一次得到可重复校验的有效名称。"""
    if not isinstance(value, str):
        return "默认用户名"
    text = "".join(ch for ch in value if ch not in ILLEGAL_CHARS)
    # 空白和点号共同构成边缘；先清左侧再截断，最后清理截断暴露的右边缘。
    text = re.sub(r"^[\s.]+", "", text)[:255]
    text = re.sub(r"[\s.]+$", "", text)
    if not text or text.upper() in RESERVED_NAMES:
        return "默认用户名"
    return text


def _validate_cli_argument(value: object) -> str:
    """沿用 dev 的 shlex 语法检查，合法输入保留原始空白及引号。"""
    if not isinstance(value, str):
        return ""
    try:
        shlex.split(value.strip())
    except ValueError:
        return ""
    return value


def _validate_cli_argument_list(value: object) -> str:
    """沿用 dev 的 | 分段、% 后参数规则；任一段语法错误时整体清空。"""
    if not isinstance(value, str):
        return ""
    try:
        for segment in value.split("|"):
            segment = segment.strip()
            if not segment:
                continue
            param_str = segment.split("%", 1)[-1].strip()
            shlex.split(param_str)
    except ValueError:
        return ""
    return value


# ──────────────────────────── 导出类型 ────────────────────────────

# dev 的纠正包含非字符串回退，须先于 Pydantic 的 str 校验执行。
JsonDictString = Annotated[str, BeforeValidator(_validate_json_dict_string)]
JsonListString = Annotated[str, BeforeValidator(_validate_json_list_string)]
UrlString = Annotated[str, BeforeValidator(_validate_url_string)]
KeyboardKeyString = Annotated[str, BeforeValidator(_validate_keyboard_key)]
WindowsNameString = Annotated[str, BeforeValidator(_validate_windows_name)]
CliArgumentString = Annotated[str, BeforeValidator(_validate_cli_argument)]
CliArgumentListString = Annotated[str, BeforeValidator(_validate_cli_argument_list)]

FilePath = Annotated[
    Path | None,
    path_policy(kind="file", must_exist=True, blocked_dirs=STANDARD_BLOCKED_DIRS),
]
"""已存在文件；统一归一化及标准路径排除，非法/空清空。"""

FolderPath = Annotated[
    Path | None,
    path_policy(kind="folder", must_exist=True, blocked_dirs=STANDARD_BLOCKED_DIRS),
]
"""已存在目录；仅在有对应目录时纠正最后一个后缀。"""

ScriptRootPath = Annotated[
    Path | None,
    path_policy(kind="folder", must_exist=True, blocked_dirs=SYSTEM_BLOCKED_DIRS),
]
"""已存在脚本目录；允许工作目录，其余排除规则与 FolderPath 一致。"""

ExecutablePath = Annotated[
    Path | None,
    path_policy(
        kind="file",
        extensions=("exe", "bat", "cmd", "com"),
        must_exist=True,
        blocked_dirs=STANDARD_BLOCKED_DIRS,
    ),
]
"""已存在可执行文件；保留来源的四种后缀，大小写不敏感。"""

LoosePath = Annotated[Path | None, path_policy(kind="any")]
"""允许不存在的文件或目录，仅归一化，不附加排除规则。"""
