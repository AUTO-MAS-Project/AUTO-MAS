"""按 ProjectInterface 白名单把一个 MaaFW 发行包投影成只含内置运行所需文件的树。

内置运行从不启动项目自带的界面程序（MFW.exe / MFAAvalonia / MXU），MaaFramework 与
Python 由运行池和隔离 venv 提供。所以一份发行包里真正需要落盘的只有：
interface.json 及其 ``import``、resource 声明的目录、controller 的附加资源、languages
文件、agent 与 pretask 引用的文件所在目录、依赖清单（requirements.txt 之类）。其余
一律不要——不是"删掉外壳"，而是"只拿声明了的"。分类表只在两处起作用：白名单目标
内部（比如 agent 目录里的 ``__pycache__``），以及保守模式下的整棵根。

三条与旧 Project Store 投影不同的取舍：

- **不改写 interface JSON。** 文件逐字节照抄，差量包里的哈希才对得上；assets 布局
  里声明路径逃出 ``assets/`` 的直接拒绝，不做路径重写。
- **不带 ABI / requirements 闸门。** 缺自带 Python 由 ``agent_env/planner.py`` 落到
  隔离 venv，这里只把"自带解释器被投影掉了"记进警告。
- **差量包用叠加视图算白名单。** 包里有 interface 就用包里的，没有就用项目现有的；
  引用的文件先在包里找、再在项目里找；不查存在性——新版本新增的目录在包里就是新的。
"""

from __future__ import annotations

import fnmatch
import json
import os
import shutil
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

import json5

MAX_REPORT_ITEMS = 128

EXCLUDED_DIRECTORY_REASONS: dict[str, str] = {
    ".git": "source-control",
    ".github": "source-control",
    ".idea": "editor-state",
    ".vscode": "editor-state",
    "ui": "ui-shell",
    "gui": "ui-shell",
    "frontend": "ui-shell",
    "web": "ui-shell",
    "webui": "ui-shell",
    "electron": "ui-shell",
    "mfaavalonia": "ui-shell",
    "mxu": "ui-shell",
    "mfw": "ui-shell",
    "maapicli": "ui-shell",
    "node_modules": "ui-runtime",
    "runtime": "embedded-runtime",
    "runtimes": "embedded-runtime",
    "python": "embedded-python",
    "python-runtime": "embedded-python",
    "python_runtime": "embedded-python",
    "python-embed": "embedded-python",
    "python_embed": "embedded-python",
    ".venv": "embedded-python",
    "venv": "embedded-python",
    "__pycache__": "cache",
    ".cache": "cache",
    "cache": "cache",
    ".pytest_cache": "cache",
    ".mypy_cache": "cache",
    ".ruff_cache": "cache",
    ".tox": "cache",
    ".nox": "cache",
    ".mas-update": "updater-shell",
    ".mas-update-cache": "updater-shell",
    "update": "updater-shell",
    "updates": "updater-shell",
    "updater": "updater-shell",
    "temp": "temporary",
    "tmp": "temporary",
    ".tmp": "temporary",
    "backup": "temporary",
    "backups": "temporary",
    "build": "build-output",
    "dist": "build-output",
}
EXCLUDED_FILE_SUFFIXES = {".pyc", ".pyo", ".tmp", ".temp", ".log"}
KNOWN_RUNTIME_FILE_NAMES = {
    "maaframework.dll",
    "maaframework.so",
    "maaframework.dylib",
    "maapicli",
    "maapicli.exe",
    "maatoolkit.dll",
    "python.exe",
    "pythonw.exe",
}
KNOWN_RUNTIME_STEMS = {"maaframework", "maatoolkit", "maaadbcontrolunit", "maahttp"}
KNOWN_UI_SHELL_STEMS = {"mfaavalonia", "mxu", "mfw", "maapicli"}
SHELL_SUFFIXES = {".bat", ".cmd", ".exe", ".ps1", ".sh"}
DEPENDENCY_DIR_NAMES = {"agent", "agents", "lock", "locks", "plugins", "requirements"}
DEPENDENCY_FILE_PATTERNS = (
    "requirements*.txt",
    "constraints*.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "uv.lock",
    "poetry.lock",
    "Pipfile",
    "Pipfile.lock",
    "environment.yml",
    "environment.yaml",
    "conda-lock.yml",
    "conda-lock.yaml",
    "*.lock",
)
PYTHON_INTERPRETER_NAMES = {
    "python",
    "python.exe",
    "python3",
    "python3.exe",
    "pythonw",
    "pythonw.exe",
    "py",
    "py.exe",
}
# 与 ``detect_maafw_project_shell_hint`` 同一套家族名，报告里直接回填。
SHELL_FAMILY_NAMES = {
    "mfaavalonia": "MFAAvalonia",
    "mxu": "MXU",
    "cfa": "CFA",
    "mfw": "MFW",
    "maapicli": "MaaPiCli",
}
SHELL_REASONS = {
    "ui-shell",
    "ui-runtime",
    "embedded-runtime",
    "embedded-python",
    "updater-shell",
}

ROOT = Path(".")


class ProjectionError(RuntimeError):
    """投影无法进行：发行包不合规，或声明的路径不存在。原因原样给用户看。"""


@dataclass(frozen=True)
class TargetMode:
    """一个白名单目标的口径。

    ``complete``：整棵子树都要（resource 目录）；否则只是"保留根"，里面按分类表剔除。
    ``allow_excluded_root``：目标本身的名字可以撞上分类表（resource 目录真有叫
    ``runtime`` 的），只豁免这个前缀，里面照常剔除。
    """

    complete: bool
    allow_excluded_root: bool


@dataclass(frozen=True)
class RequiredPath:
    path: Path
    label: str
    is_directory: bool
    python_interpreter: bool = False
    missing: bool = False


@dataclass
class ProjectionRules:
    """白名单目标 + 分类表 = "某个相对路径要不要"。

    ``source_root`` 是用户指向的目录，``interface_base`` 是 interface.json 所在目录
    （release 布局二者相同，assets 布局后者是 ``source_root/assets``）。输出路径一律
    相对 ``interface_base``，这就是 assets 布局的"提升"。
    """

    source_root: Path
    interface_base: Path
    targets: dict[Path, TargetMode]
    required: list[RequiredPath]
    agents: list[dict[str, Any]]
    conservative: bool
    warnings: list[str] = field(default_factory=list)

    @property
    def base_relative(self) -> Path:
        relative = self.interface_base.relative_to(self.source_root)
        return relative if relative.parts else ROOT

    def output_path(self, relative: Path) -> Path:
        """源相对路径 → 副本相对路径。assets 布局把 ``assets/x`` 提升为 ``x``。"""

        base = self.base_relative
        if base == ROOT:
            return relative
        try:
            promoted = relative.relative_to(base)
        except ValueError as exc:
            raise ProjectionError(
                f"路径逃出 interface 所在目录，无法提升：{relative.as_posix()}"
            ) from exc
        return promoted if promoted.parts else ROOT

    def keeps(self, relative: Path, *, is_directory: bool = False) -> bool:
        """这个源相对路径要不要进副本。"""

        for target, mode in self.targets.items():
            if not _is_relative_to(relative, target):
                continue
            target_is_directory = target == ROOT or (relative != target or is_directory)
            if (
                target_exclusion_reason(
                    relative,
                    target=target,
                    mode=mode,
                    target_is_directory=target_is_directory,
                    is_directory=is_directory,
                )
                is None
            ):
                return True
        return False


@dataclass
class ProjectionPlan:
    rules: ProjectionRules
    copied_files: set[Path]
    copied_directories: set[Path]
    excluded_reasons: dict[str, str]
    source_tree_bytes: int
    projected_bytes: int

    def report(self) -> dict[str, Any]:
        """给界面看的精简报告。数字在这里算好，前端不重算。"""

        saved = max(0, self.source_tree_bytes - self.projected_bytes)
        percent = (
            round(saved * 100 / self.source_tree_bytes, 2)
            if self.source_tree_bytes
            else 0.0
        )
        families: set[str] = set()
        reason_counts: dict[str, int] = {}
        for path, reason in self.excluded_reasons.items():
            if reason in SHELL_REASONS:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
                for part in Path(path).parts:
                    family = SHELL_FAMILY_NAMES.get(part.casefold().split(".", 1)[0])
                    if family:
                        families.add(family)
        excluded_items = sorted(self.excluded_reasons.items())
        return {
            "sourceSizeBytes": self.source_tree_bytes,
            "payloadSizeBytes": self.projected_bytes,
            "savedBytes": saved,
            "savedPercent": percent,
            "copiedFileCount": len(self.copied_files),
            "excludedCount": len(self.excluded_reasons),
            "excludedReasons": dict(excluded_items[:MAX_REPORT_ITEMS]),
            "excludedTruncated": len(excluded_items) > MAX_REPORT_ITEMS,
            "shellFamilies": sorted(families),
            "shellReasonCounts": dict(sorted(reason_counts.items())),
            "conservative": self.rules.conservative,
            "interfaceBase": self.rules.base_relative.as_posix(),
            "agents": [dict(agent) for agent in self.rules.agents],
            "warnings": list(self.rules.warnings),
        }


# --------------------------------------------------------------------------
# 分类表
# --------------------------------------------------------------------------


def exclusion_reason(path: Path, *, is_directory: bool = False) -> str | None:
    """按分类表判断一个相对路径为什么不该进副本；None 表示没有理由。"""

    parts = path.parts if is_directory else path.parts[:-1]
    for part in parts:
        normalized = part.casefold()
        reason = EXCLUDED_DIRECTORY_REASONS.get(normalized)
        if reason:
            return reason
        family = normalized.split(".", 1)[0]
        if family in KNOWN_UI_SHELL_STEMS:
            return "ui-shell"
        if family in KNOWN_RUNTIME_STEMS:
            return "embedded-runtime"
    if is_directory:
        return None
    name = path.name.casefold()
    suffix = path.suffix.casefold()
    family = name.split(".", 1)[0]
    if family in KNOWN_UI_SHELL_STEMS:
        return "ui-shell"
    if family in KNOWN_RUNTIME_STEMS:
        return "embedded-runtime"
    if suffix in EXCLUDED_FILE_SUFFIXES:
        return "cache-or-temporary"
    if name in KNOWN_RUNTIME_FILE_NAMES or (
        name.startswith("python") and suffix in {".dll", ".exe", ".so", ".dylib"}
    ):
        return "embedded-runtime"
    stem = path.stem.casefold()
    if suffix in SHELL_SUFFIXES and (
        "update" in stem
        or "updater" in stem
        or stem.endswith(("gui", "ui", "launcher"))
    ):
        return "ui-or-updater-shell"
    return None


def target_exclusion_reason(
    path: Path,
    *,
    target: Path,
    mode: TargetMode,
    target_is_directory: bool,
    is_directory: bool = False,
) -> str | None:
    """在某个白名单目标之下判断 ``path``。

    显式声明的完整目标（resource 目录）可以叫 ``runtime`` / ``python`` 这种在发行包
    顶层视为外壳的名字——声明比猜测更可信，只豁免目标前缀本身，里面照常剔除。
    """

    if not mode.complete or not mode.allow_excluded_root or target == ROOT:
        return exclusion_reason(path, is_directory=is_directory)
    if target_is_directory:
        return exclusion_reason(path.relative_to(target), is_directory=is_directory)
    return exclusion_reason(Path(path.name), is_directory=is_directory)


# --------------------------------------------------------------------------
# 文件视图：单目录（导入）或叠加（差量包在前、项目在后）
# --------------------------------------------------------------------------


class _FileView:
    def __init__(self, roots: tuple[Path, ...]) -> None:
        self.roots = roots

    def locate(self, relative: Path) -> Path | None:
        for root in self.roots:
            candidate = root / relative
            if candidate.exists():
                return candidate
        return None

    def exists(self, relative: Path) -> bool:
        return self.locate(relative) is not None

    def is_file(self, relative: Path) -> bool:
        located = self.locate(relative)
        return located is not None and located.is_file()

    def is_dir(self, relative: Path) -> bool:
        located = self.locate(relative)
        return located is not None and located.is_dir()

    def read_json(self, relative: Path, label: str) -> dict[str, Any]:
        located = self.locate(relative)
        if located is None or not located.is_file():
            raise ProjectionError(f"{label} 不存在：{relative.as_posix()}")
        return read_json_object(located, label)

    def iter_entries(self, relative: Path) -> list[Path]:
        """列出叠加视图里某目录下的直接条目（相对根路径），不重复。"""

        seen: dict[str, Path] = {}
        for root in self.roots:
            directory = root / relative
            if not directory.is_dir():
                continue
            for entry in directory.iterdir():
                seen.setdefault(entry.name, relative / entry.name)
        return list(seen.values())


def read_json_object(path: Path, label: str) -> dict[str, Any]:
    """interface 文件：先 json，失败再退 json5——带注释的 JSONC 也能读。"""

    text = path.read_text(encoding="utf-8-sig")
    try:
        payload = json.loads(text)
    except ValueError:
        try:
            payload = json5.loads(text)
        except Exception as exc:  # noqa: BLE001 - 解析器异常类型不统一
            raise ProjectionError(f"{label} 不是合法 JSON：{path}（{exc}）") from exc
    if not isinstance(payload, dict):
        raise ProjectionError(f"{label} 顶层必须是 JSON object：{path}")
    return payload


# --------------------------------------------------------------------------
# interface 发现与路径解析
# --------------------------------------------------------------------------


def discover_project_interface(source_root: Path) -> tuple[Path, Path]:
    """返回 ``(interface_base, interface_path)``；先看根，再看 ``assets/``。"""

    root = source_root.resolve()
    for base, name in (
        (root, "interface.json"),
        (root, "interface.jsonc"),
        (root / "assets", "interface.json"),
        (root / "assets", "interface.jsonc"),
    ):
        candidate = base / name
        if candidate.is_file():
            return base, candidate
    raise ProjectionError("目录里没有 interface.json（根目录或 assets/ 下都没有）")


def _normalize_declared_path(raw: str, base_relative: Path, label: str) -> Path:
    """把 interface 里写的路径归一成相对 ``source_root`` 的纯路径，不许逃出去。"""

    value = str(raw).strip().strip('"').strip("'").replace("\\", "/")
    value = value.replace("${PROJECT_DIR}", "{PROJECT_DIR}")
    if value.startswith("{PROJECT_DIR}"):
        value = value[len("{PROJECT_DIR}") :].lstrip("/")
    pure = PurePosixPath(value or ".")
    if pure.is_absolute() or (len(value) > 1 and value[1] == ":"):
        raise ProjectionError(f"{label} 必须是项目内的相对路径：{raw}")
    parts: list[str] = list(base_relative.parts)
    for part in pure.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                raise ProjectionError(f"{label} 逃出了项目目录：{raw}")
            parts.pop()
            continue
        parts.append(part)
    return Path(*parts) if parts else ROOT


def looks_like_local_path(value: str) -> bool:
    normalized = value.strip().strip('"').strip("'")
    if not normalized or normalized.startswith(("-", "http://", "https://")):
        return False
    if normalized.startswith(
        ("{PROJECT_DIR}", "${PROJECT_DIR}", "./", "../", ".\\", "..\\")
    ):
        return True
    if "/" in normalized or "\\" in normalized:
        return True
    return Path(normalized).suffix.casefold() in {
        ".py",
        ".pyw",
        ".js",
        ".mjs",
        ".cjs",
        ".exe",
        ".cmd",
        ".bat",
        ".ps1",
        ".sh",
    }


def is_python_interpreter_path(path: Path) -> bool:
    return path.name.casefold() in PYTHON_INTERPRETER_NAMES


def classify_agent(
    declared_type: str, child_exec: str, child_args: list[str]
) -> tuple[str, bool]:
    """返回 ``(classification, opaque)``。opaque 为真时投影退回保守模式。"""

    kind = declared_type.casefold()
    executable = Path(child_exec.replace("\\", "/")).name.casefold()
    suffixes = {Path(item.replace("\\", "/")).suffix.casefold() for item in child_args}
    if kind in {"custom", "command", "shell", "opaque"}:
        return kind or "opaque", True
    if (
        is_python_interpreter_path(Path(executable))
        or ".py" in suffixes
        or ".pyw" in suffixes
    ):
        return "python", False
    if executable in {"node", "node.exe", "deno", "deno.exe", "bun", "bun.exe"} or (
        ".js" in suffixes or ".mjs" in suffixes
    ):
        return "javascript", False
    if executable in {
        "cmd",
        "cmd.exe",
        "powershell",
        "powershell.exe",
        "pwsh",
        "pwsh.exe",
        "sh",
        "bash",
    }:
        return "command", True
    if child_exec and (
        "/" in child_exec or "\\" in child_exec or Path(child_exec).suffix
    ):
        return "native", False
    if child_exec:
        return "external", True
    return "opaque", True


def _retention_root(relative: Path, view: _FileView) -> Path:
    """agent / pretask 引用的文件所在目录整个保留（按分类表剔除）。"""

    if view.is_dir(relative):
        return relative
    parent = relative.parent
    return parent if parent != ROOT else relative


# --------------------------------------------------------------------------
# 白名单目标收集
# --------------------------------------------------------------------------


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def _text(value: Any) -> str:
    return str(value).strip() if isinstance(value, str) else ""


def build_projection_rules(
    source_root: Path,
    *,
    strict: bool = True,
    overlay_root: Path | None = None,
) -> ProjectionRules:
    """从 interface 声明算出白名单。

    ``strict``：导入时为真——声明的路径必须存在，缺了就是发行包不合规。差量落地时
    为假——新版本新增的目录本来就还不在项目里。
    ``overlay_root``：差量包的 payload 根，排在项目目录前面参与查找。
    """

    source_root = source_root.resolve()
    roots: tuple[Path, ...] = (
        (overlay_root.resolve(), source_root)
        if overlay_root is not None
        else (source_root,)
    )
    view = _FileView(roots)
    # interface 在哪一层？叠加视图里以包内的为准，包里没有再看项目。
    interface_base: Path | None = None
    interface_relative: Path | None = None
    for root in roots:
        try:
            base, path = discover_project_interface(root)
        except ProjectionError:
            continue
        interface_base = base.relative_to(root)
        interface_relative = path.relative_to(root)
        break
    if interface_base is None or interface_relative is None:
        raise ProjectionError("目录里没有 interface.json（根目录或 assets/ 下都没有）")
    base_relative = interface_base if interface_base.parts else ROOT

    targets: dict[Path, TargetMode] = {}
    required: list[RequiredPath] = []
    warnings: list[str] = []
    agents: list[dict[str, Any]] = []
    opaque_found = False

    def add_target(
        relative: Path,
        *,
        complete: bool,
        required_label: str | None,
        allow_excluded_root: bool = False,
        required_path: Path | None = None,
        python_interpreter: bool = False,
    ) -> None:
        exists = view.exists(relative)
        if not exists:
            if python_interpreter:
                # 自带解释器不在了（本来就没发，或已被上一次投影去掉）：planner 会
                # 落到隔离 venv，这不是错误，记一笔就行。
                required.append(
                    RequiredPath(
                        path=required_path or relative,
                        label=required_label or "agent interpreter",
                        is_directory=False,
                        python_interpreter=True,
                        missing=True,
                    )
                )
                return
            if required_label and strict:
                raise ProjectionError(
                    f"{required_label} 声明的路径不存在：{relative.as_posix()}"
                )
            if required_label:
                warnings.append(
                    f"{required_label} 声明的路径当前不存在：{relative.as_posix()}"
                )
            else:
                warnings.append(f"可选路径不存在，未保留：{relative.as_posix()}")
            if not strict:
                # 差量落地：目标还没到，但白名单要先立起来，包里带来的文件才能进。
                previous = targets.get(relative, TargetMode(False, False))
                targets[relative] = TargetMode(
                    previous.complete or complete,
                    previous.allow_excluded_root or allow_excluded_root,
                )
            return
        previous = targets.get(relative, TargetMode(False, False))
        targets[relative] = TargetMode(
            previous.complete or complete,
            previous.allow_excluded_root or allow_excluded_root,
        )
        if required_label:
            exact = required_path or relative
            required.append(
                RequiredPath(
                    path=exact,
                    label=required_label,
                    is_directory=view.is_dir(exact),
                    python_interpreter=python_interpreter,
                )
            )

    def declare(raw: str, label: str, *, must_exist: bool) -> Path | None:
        relative = _normalize_declared_path(raw, base_relative, label)
        if must_exist and strict and not view.exists(relative):
            raise ProjectionError(f"{label} 声明的路径不存在：{raw}")
        return relative

    def declare_executable(raw: str, label: str) -> Path:
        relative = _normalize_declared_path(raw, base_relative, label)
        if view.exists(relative):
            return relative
        if not relative.suffix:
            with_exe = relative.with_name(relative.name + ".exe")
            if view.is_file(with_exe):
                return with_exe
        return relative

    visited: set[Path] = set()

    def visit_interface(relative: Path, scope: str) -> None:
        nonlocal opaque_found
        if relative in visited:
            return
        visited.add(relative)
        data = view.read_json(relative, "ProjectInterface")
        add_target(relative, complete=True, required_label="ProjectInterface")

        raw_imports = data.get("import")
        if raw_imports is not None:
            if not isinstance(raw_imports, list) or not all(
                isinstance(item, str) and item.strip() for item in raw_imports
            ):
                raise ProjectionError("ProjectInterface 的 import 必须是字符串数组")
            for raw_import in raw_imports:
                imported = declare(
                    raw_import, "ProjectInterface import", must_exist=True
                )
                if imported is None:
                    continue
                if strict and not view.is_file(imported):
                    raise ProjectionError(
                        f"ProjectInterface import 不是文件：{raw_import}"
                    )
                if view.is_file(imported):
                    visit_interface(imported, imported.as_posix())
                else:
                    add_target(
                        imported,
                        complete=True,
                        required_label="ProjectInterface import",
                    )

        for index, resource in enumerate(_as_list(data.get("resource"))):
            if not isinstance(resource, dict):
                continue
            name = _text(resource.get("name")) or f"resource[{index}]"
            raw_paths = resource.get("path")
            values = (
                [raw_paths] if isinstance(raw_paths, str) else list(raw_paths or [])
            )
            for raw_path in values:
                if not isinstance(raw_path, str):
                    raise ProjectionError(f"resource {name} 的 path 必须是字符串")
                relative_path = declare(raw_path, f"resource {name}", must_exist=True)
                if relative_path is not None:
                    add_target(
                        relative_path,
                        complete=True,
                        required_label=f"resource {name}",
                        allow_excluded_root=True,
                    )

        for index, controller in enumerate(_as_list(data.get("controller"))):
            if not isinstance(controller, dict):
                continue
            key = (
                "attach_resource_path"
                if "attach_resource_path" in controller
                else "attachResourcePath"
            )
            raw_value = controller.get(key)
            if raw_value is None:
                continue
            values = (
                [raw_value] if isinstance(raw_value, str) else list(raw_value or [])
            )
            for raw_path in values:
                if not isinstance(raw_path, str):
                    raise ProjectionError(
                        f"controller[{index}].{key} 必须是字符串或字符串数组"
                    )
                relative_path = declare(
                    raw_path, f"controller[{index}].{key}", must_exist=True
                )
                if relative_path is not None:
                    add_target(
                        relative_path,
                        complete=True,
                        required_label=f"controller[{index}].{key}",
                        allow_excluded_root=True,
                    )

        languages = data.get("languages")
        if isinstance(languages, dict):
            for language, raw_path in languages.items():
                if not isinstance(raw_path, str):
                    raise ProjectionError(f"languages.{language} 必须是字符串路径")
                relative_path = declare(
                    raw_path, f"languages.{language}", must_exist=True
                )
                if relative_path is not None:
                    add_target(
                        relative_path,
                        complete=True,
                        required_label=f"languages.{language}",
                    )

        for index, agent in enumerate(_as_list(data.get("agent"))):
            if not isinstance(agent, dict):
                continue
            child_exec = _text(agent.get("child_exec")) or _text(agent.get("childExec"))
            raw_args = agent.get("child_args")
            if raw_args is None:
                raw_args = agent.get("childArgs")
            child_args = (
                [item for item in raw_args if isinstance(item, str)]
                if isinstance(raw_args, list)
                else []
            )
            declared_type = _text(agent.get("type")) or _text(agent.get("kind"))
            classification, opaque = classify_agent(
                declared_type, child_exec, child_args
            )
            opaque_found = opaque_found or opaque
            discovered: list[str] = []
            if child_exec and looks_like_local_path(child_exec):
                label = f"agent[{index}].child_exec"
                exec_relative = declare_executable(child_exec, label)
                interpreter = classification == "python" and is_python_interpreter_path(
                    exec_relative
                )
                if view.exists(exec_relative):
                    discovered.append(exec_relative.as_posix())
                    add_target(
                        _retention_root(exec_relative, view),
                        complete=False,
                        required_label=label,
                        required_path=exec_relative,
                        python_interpreter=interpreter,
                    )
                    _add_root_python_siblings(
                        exec_relative, view, targets, base_relative
                    )
                elif interpreter:
                    add_target(
                        exec_relative,
                        complete=False,
                        required_label=label,
                        python_interpreter=True,
                    )
                elif strict:
                    raise ProjectionError(f"{label} 声明的路径不存在：{child_exec}")
                else:
                    warnings.append(f"{label} 声明的路径当前不存在：{child_exec}")
            for arg_index, raw_arg in enumerate(child_args):
                if not looks_like_local_path(raw_arg):
                    continue
                label = f"agent[{index}].child_args[{arg_index}]"
                arg_relative = declare(raw_arg, label, must_exist=True)
                if arg_relative is None:
                    continue
                if view.exists(arg_relative):
                    discovered.append(arg_relative.as_posix())
                    add_target(
                        _retention_root(arg_relative, view),
                        complete=False,
                        required_label=label,
                        required_path=arg_relative,
                    )
                    _add_root_python_siblings(
                        arg_relative, view, targets, base_relative
                    )
                else:
                    warnings.append(f"{label} 声明的路径当前不存在：{raw_arg}")
            agents.append(
                {
                    "index": index,
                    "scope": scope,
                    "declaredType": declared_type or None,
                    "childExec": child_exec or None,
                    "classification": classification,
                    "opaque": opaque,
                    "projectPaths": discovered,
                }
            )

        for index, pretask in enumerate(_as_list(data.get("pretask"))):
            if not isinstance(pretask, dict):
                continue
            raw_exec = pretask.get("exec")
            if not isinstance(raw_exec, str) or not looks_like_local_path(raw_exec):
                continue
            label = f"pretask[{index}].exec"
            exec_relative = declare_executable(raw_exec, label)
            if view.exists(exec_relative):
                add_target(
                    _retention_root(exec_relative, view),
                    complete=False,
                    required_label=label,
                    required_path=exec_relative,
                )
            elif strict:
                raise ProjectionError(f"{label} 声明的路径不存在：{raw_exec}")
            else:
                warnings.append(f"{label} 声明的路径当前不存在：{raw_exec}")

    visit_interface(interface_relative, interface_relative.as_posix())

    # 依赖清单：根目录与 interface 所在目录都看一眼。
    for base in {ROOT, base_relative}:
        for entry in view.iter_entries(base):
            name = entry.name
            if name.casefold() in DEPENDENCY_DIR_NAMES and view.is_dir(entry):
                add_target(entry, complete=False, required_label=None)
            elif view.is_file(entry) and any(
                fnmatch.fnmatchcase(name, pattern)
                for pattern in DEPENDENCY_FILE_PATTERNS
            ):
                add_target(entry, complete=False, required_label=None)

    conservative = opaque_found
    if conservative:
        targets[ROOT] = TargetMode(complete=False, allow_excluded_root=False)
        warnings.append(
            "agent 是 custom / command / 不透明形态，投影退回保守模式：保留整棵目录，只去掉分类表命中的外壳与缓存。"
        )

    # 声明路径逃出 interface 所在目录的，assets 布局提升后会指向不存在的位置。
    if base_relative != ROOT:
        for target in targets:
            if target != ROOT and not _is_relative_to(target, base_relative):
                raise ProjectionError(
                    f"interface 在 {base_relative.as_posix()}/ 下，但声明的路径 "
                    f"{target.as_posix()} 在它之外；这种布局无法提升为内嵌副本"
                )

    rules = ProjectionRules(
        source_root=source_root,
        interface_base=source_root / base_relative,
        targets=targets,
        required=required,
        agents=agents,
        conservative=conservative,
        warnings=warnings,
    )
    return rules


def _add_root_python_siblings(
    relative: Path,
    view: _FileView,
    targets: dict[Path, TargetMode],
    base_relative: Path,
) -> None:
    """根目录直接放 ``main.py`` 的项目，把同级 ``*.py`` 与惯例目录一并保留。"""

    if relative.parent != base_relative and relative.parent != ROOT:
        return
    if relative.suffix.casefold() not in {".py", ".pyw"}:
        return
    for entry in view.iter_entries(relative.parent):
        if view.is_file(entry) and entry.suffix.casefold() in {".py", ".pyw"}:
            targets.setdefault(entry, TargetMode(False, False))
    for folder_name in ("src", "lib", "modules", relative.stem):
        folder = relative.parent / folder_name
        if view.is_dir(folder):
            targets.setdefault(folder, TargetMode(False, False))


# --------------------------------------------------------------------------
# 完整投影（导入）与复制
# --------------------------------------------------------------------------


def _scan_tree(root: Path) -> tuple[set[Path], set[Path], dict[Path, int]]:
    directories: set[Path] = {ROOT}
    files: set[Path] = set()
    sizes: dict[Path, int] = {}
    for current_raw, directory_names, file_names in os.walk(
        root, topdown=True, followlinks=False
    ):
        current = Path(current_raw)
        if current.is_symlink():
            raise ProjectionError(f"目录里有符号链接，拒绝投影：{current}")
        for directory_name in list(directory_names):
            directory = current / directory_name
            if directory.is_symlink():
                raise ProjectionError(f"目录里有符号链接，拒绝投影：{directory}")
            directories.add(directory.relative_to(root))
        for file_name in file_names:
            file_path = current / file_name
            if file_path.is_symlink():
                raise ProjectionError(f"目录里有符号链接，拒绝投影：{file_path}")
            if not file_path.is_file():
                continue
            relative = file_path.relative_to(root)
            files.add(relative)
            sizes[relative] = file_path.stat().st_size
    return directories, files, sizes


def _relative_parents(path: Path) -> set[Path]:
    parents: set[Path] = set()
    current = path.parent
    while current != ROOT:
        parents.add(current)
        current = current.parent
    parents.add(ROOT)
    return parents


def _is_relative_to(path: Path, parent: Path) -> bool:
    if parent == ROOT:
        return True
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def build_projection_plan(source_root: Path) -> ProjectionPlan:
    """导入用：算白名单、扫整棵树、决定每个文件去留。"""

    rules = build_projection_rules(source_root, strict=True)
    root = rules.source_root
    all_directories, all_files, sizes = _scan_tree(root)

    copied_files: set[Path] = set()
    copied_directories: set[Path] = {ROOT}
    for target, mode in rules.targets.items():
        target_absolute = root / target
        if target_absolute.is_file():
            if (
                target_exclusion_reason(
                    target, target=target, mode=mode, target_is_directory=False
                )
                is None
            ):
                copied_files.add(target)
                copied_directories.update(_relative_parents(target))
            continue
        for directory in all_directories:
            if not _is_relative_to(directory, target):
                continue
            if (
                target_exclusion_reason(
                    directory,
                    target=target,
                    mode=mode,
                    target_is_directory=True,
                    is_directory=True,
                )
                is None
            ):
                copied_directories.add(directory)
                copied_directories.update(_relative_parents(directory))
        for file_path in all_files:
            if not _is_relative_to(file_path, target):
                continue
            if (
                target_exclusion_reason(
                    file_path, target=target, mode=mode, target_is_directory=True
                )
                is None
            ):
                copied_files.add(file_path)
                copied_directories.update(_relative_parents(file_path))

    # 声明为必需的路径必须真的留下来；唯一的例外是被投影掉的自带 Python 解释器。
    for requirement in rules.required:
        retained = (
            requirement.path in copied_directories
            if requirement.is_directory
            else requirement.path in copied_files
        )
        if retained:
            continue
        if requirement.python_interpreter:
            rules.warnings.append(
                f"{requirement.label} 的自带 Python 解释器"
                f"{'不存在' if requirement.missing else '已被投影去掉'}"
                f"（{requirement.path.as_posix()}），运行时将使用该项目的隔离 venv。"
            )
            continue
        reason = exclusion_reason(
            requirement.path, is_directory=requirement.is_directory
        )
        raise ProjectionError(
            f"{requirement.label} 是运行必需的，却被投影排除了："
            f"{requirement.path.as_posix()}（{reason or 'not-retained'}）"
        )

    excluded_reasons = {
        path.as_posix(): (
            exclusion_reason(path) or "not-required-by-runtime-projection"
        )
        for path in all_files - copied_files
    }

    # 提升后的输出路径不能撞车（assets/x 与根上的 x 同名）。
    owners: dict[Path, Path] = {}
    for source_relative in copied_files:
        output = rules.output_path(source_relative)
        owner = owners.setdefault(output, source_relative)
        if owner != source_relative:
            raise ProjectionError(
                f"提升 assets/ 后路径撞车：{owner.as_posix()} 与 {source_relative.as_posix()}"
            )

    return ProjectionPlan(
        rules=rules,
        copied_files=copied_files,
        copied_directories=copied_directories,
        excluded_reasons=excluded_reasons,
        source_tree_bytes=sum(sizes.values()),
        projected_bytes=sum(sizes[path] for path in copied_files),
    )


def materialize_projection(
    plan: ProjectionPlan,
    target_dir: Path,
    *,
    progress: Callable[[int, int], None] | None = None,
) -> None:
    """把 plan 里要留的文件复制到 ``target_dir``（assets 布局在这里被提升）。"""

    target = target_dir.resolve()
    target.mkdir(parents=True, exist_ok=True)
    rules = plan.rules
    for relative_directory in sorted(
        plan.copied_directories, key=lambda path: (len(path.parts), path.as_posix())
    ):
        if relative_directory == ROOT:
            continue
        try:
            output_directory = rules.output_path(relative_directory)
        except ProjectionError:
            # 提升后的根之外的目录（例如 assets 布局里根上的 README 所在目录）不需要建。
            continue
        if output_directory == ROOT:
            continue
        (target / output_directory).mkdir(parents=True, exist_ok=True)

    ordered = sorted(plan.copied_files, key=lambda path: path.as_posix())
    total = len(ordered)
    for index, relative_file in enumerate(ordered, start=1):
        source = rules.source_root / relative_file
        destination = target / rules.output_path(relative_file)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        if progress is not None:
            progress(index, total)


# --------------------------------------------------------------------------
# 更新落地：给 build_package_plan 用的过滤谓词
# --------------------------------------------------------------------------


def package_projection_rules(payload_root: Path, project_root: Path) -> ProjectionRules:
    """更新包落地时的白名单：包内 interface 优先，其次项目现有的；不查存在性。

    只支持 release 布局的包（interface.json 在包根）：内嵌副本本身就是提升后的
    release 布局，assets 布局的源码 zip 从来不是更新器的输入。
    """

    rules = build_projection_rules(
        project_root, strict=False, overlay_root=payload_root
    )
    if rules.base_relative != ROOT:
        raise ProjectionError(
            "更新包的 interface.json 不在包根（assets 布局），内嵌副本不接受这种更新包"
        )
    return rules


def filter_package_entries(
    rules: ProjectionRules,
    entries: Iterable[str],
) -> tuple[set[str], dict[str, str]]:
    """把包内相对路径分成「要落盘」与「不要（附原因）」两组。"""

    kept: set[str] = set()
    dropped: dict[str, str] = {}
    for entry in entries:
        # 包内条目与白名单目标同一坐标系：都相对根。
        relative = Path(entry)
        if rules.keeps(relative):
            kept.add(entry)
        else:
            dropped[entry] = (
                exclusion_reason(relative) or "not-required-by-runtime-projection"
            )
    return kept, dropped


__all__ = [
    "EXCLUDED_DIRECTORY_REASONS",
    "MAX_REPORT_ITEMS",
    "ProjectionError",
    "ProjectionPlan",
    "ProjectionRules",
    "RequiredPath",
    "TargetMode",
    "build_projection_plan",
    "build_projection_rules",
    "classify_agent",
    "discover_project_interface",
    "exclusion_reason",
    "filter_package_entries",
    "is_python_interpreter_path",
    "looks_like_local_path",
    "materialize_projection",
    "package_projection_rules",
    "read_json_object",
    "target_exclusion_reason",
]
