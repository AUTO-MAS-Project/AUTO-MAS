"""已登记的载荷按哪一版投影规则建的：旧版规则的复刻，只用来算「当前规则比旧规则多留了什么」。

``projection.PROJECTION_REVISION`` 每加一，就在这里留一份上一版规则的判定（不跟着当前规则
改），``projection_heal`` 用它找出旧载荷漏装的文件：**当前规则保留、载荷那一版规则剔掉**。
只比两版规则之差，所以没被误伤的项目一个文件都不会补，白名单之外的取舍（顶层大目录）
也不会被当成缺文件。白名单目标（``ProjectionRules.targets``）两边用同一组，按当前规则算。

- 版本 0（v5.6.0）：分类表的目录名在任何深度都算，完整目标（resource 目录）里也按整张表剔。
- 版本 1（#1104）：分类表的目录名只在发行包顶层算数，只凭名字猜外壳（``runtime`` /
  ``python`` / ``web`` / ``update`` …），文件名规则（``mfw.py``、嵌套的 ``MaaFramework.dll``、
  ``python*.exe``）任何深度都算。
"""

from __future__ import annotations

from pathlib import Path

from .projection import (
    PROJECTION_REVISION,
    ROOT,
    ProjectionRules,
    TargetMode,
    _is_relative_to,
    target_exclusion_reason,
)

# ---- 版本 1 的分类表（原样冻结，不跟着 projection.py 改）----
_V1_DIRECTORY_REASONS: dict[str, str] = {
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
    "pyside6": "ui-runtime",
    "pyside2": "ui-runtime",
    "pyqt6": "ui-runtime",
    "pyqt5": "ui-runtime",
    "shiboken6": "ui-runtime",
    "shiboken2": "ui-runtime",
    "maafw": "embedded-runtime",
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
    "debug": "cache",
    "logs": "cache",
    "log": "cache",
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
_V1_ANYWHERE_DIRECTORY_NAMES = frozenset(
    {
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".nox",
        ".git",
        ".github",
        ".idea",
        ".vscode",
        ".mas-update",
        ".mas-update-cache",
    }
)
_V1_FILE_SUFFIXES = {".pyc", ".pyo", ".tmp", ".temp", ".log"}
_V1_RUNTIME_FILE_NAMES = {
    "maaframework.dll",
    "maaframework.so",
    "maaframework.dylib",
    "maapicli",
    "maapicli.exe",
    "maatoolkit.dll",
    "python.exe",
    "pythonw.exe",
}
_V1_RUNTIME_STEMS = {"maaframework", "maatoolkit", "maaadbcontrolunit", "maahttp"}
_V1_UI_SHELL_STEMS = {"mfaavalonia", "mxu", "mfw", "maapicli"}
_V1_SHELL_SUFFIXES = {".bat", ".cmd", ".exe", ".ps1", ".sh"}


def _v1_file_reason(path: Path) -> str | None:
    """版本 0 / 1 的文件名规则（两版相同，任何深度都算）。"""

    name = path.name.casefold()
    suffix = path.suffix.casefold()
    family = name.split(".", 1)[0]
    if family in _V1_UI_SHELL_STEMS:
        return "ui-shell"
    if family in _V1_RUNTIME_STEMS:
        return "embedded-runtime"
    if suffix in _V1_FILE_SUFFIXES:
        return "cache-or-temporary"
    if name in _V1_RUNTIME_FILE_NAMES or (
        name.startswith("python") and suffix in {".dll", ".exe", ".so", ".dylib"}
    ):
        return "embedded-runtime"
    stem = path.stem.casefold()
    if suffix in _V1_SHELL_SUFFIXES and (
        "update" in stem
        or "updater" in stem
        or stem.endswith(("gui", "ui", "launcher"))
    ):
        return "ui-or-updater-shell"
    return None


def _v1_top_level_indexes(path: Path, base: Path) -> frozenset[int]:
    if base == ROOT or not _is_relative_to(path, base):
        return frozenset({0})
    return frozenset({0, len(base.parts)})


def _exclusion_reason_v1(
    path: Path, *, is_directory: bool = False, base: Path = ROOT
) -> str | None:
    """版本 1 的 ``exclusion_reason``：目录名只在顶层算数，文件名规则任何深度都算。"""

    parts = path.parts if is_directory else path.parts[:-1]
    top = _v1_top_level_indexes(path, base)
    for index, part in enumerate(parts):
        normalized = part.casefold()
        if normalized in _V1_ANYWHERE_DIRECTORY_NAMES:
            return _V1_DIRECTORY_REASONS.get(normalized, "cache")
        if index not in top:
            continue
        reason = _V1_DIRECTORY_REASONS.get(normalized)
        if reason:
            return reason
        family = normalized.split(".", 1)[0]
        if family in _V1_UI_SHELL_STEMS:
            return "ui-shell"
        if family in _V1_RUNTIME_STEMS:
            return "embedded-runtime"
    if is_directory:
        return None
    return _v1_file_reason(path)


def _cache_exclusion_reason_v1(path: Path) -> str | None:
    for part in path.parts[:-1]:
        normalized = part.casefold()
        if normalized in _V1_ANYWHERE_DIRECTORY_NAMES:
            return _V1_DIRECTORY_REASONS.get(normalized, "cache")
    if path.suffix.casefold() in _V1_FILE_SUFFIXES:
        return "cache-or-temporary"
    return None


def _target_exclusion_reason_v1(
    path: Path,
    *,
    target: Path,
    mode: TargetMode,
    target_is_directory: bool,
    base: Path,
) -> str | None:
    """版本 1 的 ``target_exclusion_reason``（文件）。"""

    if not mode.complete or not mode.allow_excluded_root or target == ROOT:
        return _exclusion_reason_v1(path, base=base)
    inner = path.relative_to(target) if target_is_directory else Path(path.name)
    if mode.verbatim_runtime:
        if any(part.casefold() == "__pycache__" for part in inner.parts[:-1]):
            return "cache"
        return None
    return _cache_exclusion_reason_v1(inner)


def _exclusion_reason_v0(path: Path, *, is_directory: bool = False) -> str | None:
    """v5.6.0 的 ``exclusion_reason``：目录名在任何深度都按分类表判，文件名规则不变。"""

    parts = path.parts if is_directory else path.parts[:-1]
    for part in parts:
        normalized = part.casefold()
        reason = _V1_DIRECTORY_REASONS.get(normalized)
        if reason:
            return reason
        family = normalized.split(".", 1)[0]
        if family in _V1_UI_SHELL_STEMS:
            return "ui-shell"
        if family in _V1_RUNTIME_STEMS:
            return "embedded-runtime"
    if is_directory:
        return None
    return _v1_file_reason(path)


def _target_exclusion_reason_v0(
    path: Path, *, target: Path, mode: TargetMode, target_is_directory: bool
) -> str | None:
    """v5.6.0 的 ``target_exclusion_reason``：完整目标里照样按整张分类表剔，原样带走的
    运行时目录新旧同一口径。"""

    if not mode.complete or not mode.allow_excluded_root or target == ROOT:
        return _exclusion_reason_v0(path)
    if mode.verbatim_runtime:
        return _target_exclusion_reason_v1(
            path,
            target=target,
            mode=mode,
            target_is_directory=target_is_directory,
            base=ROOT,
        )
    inner = path.relative_to(target) if target_is_directory else Path(path.name)
    return _exclusion_reason_v0(inner)


def target_exclusion_reason_at(
    revision: int,
    path: Path,
    *,
    rules: ProjectionRules,
    target: Path,
    mode: TargetMode,
    target_is_directory: bool,
) -> str | None:
    """第 ``revision`` 版规则在白名单目标 ``target`` 下怎么判 ``path``（文件）。"""

    if revision <= 0:
        return _target_exclusion_reason_v0(
            path, target=target, mode=mode, target_is_directory=target_is_directory
        )
    if revision == 1:
        return _target_exclusion_reason_v1(
            path,
            target=target,
            mode=mode,
            target_is_directory=target_is_directory,
            base=rules.base_relative,
        )
    return target_exclusion_reason(
        path,
        target=target,
        mode=mode,
        target_is_directory=target_is_directory,
        base=rules.base_relative,
        confirmed=rules.confirmed_shell,
    )


def keeps_at(rules: ProjectionRules, relative: Path, revision: int) -> bool:
    """第 ``revision`` 版规则留不留这个文件（``rules`` 坐标里的路径）。与
    ``ProjectionRules.keeps`` 同一判定，只是按祖先查目标：``keeps`` 对每个路径把全部目标
    ``relative_to`` 一遍，MaaFgo 六百多个目标 × 一万多个条目要几十秒。"""

    for ancestor in (relative, *relative.parents):
        mode = rules.targets.get(ancestor)
        if mode is None:
            continue
        if (
            target_exclusion_reason_at(
                revision,
                relative,
                rules=rules,
                target=ancestor,
                mode=mode,
                target_is_directory=ancestor == ROOT or relative != ancestor,
            )
            is None
        ):
            return True
    return False


def newly_kept(rules: ProjectionRules, relative: Path, revision: int) -> bool:
    """当前规则保留、第 ``revision`` 版规则剔掉：只有这种文件才可能是那一版载荷漏装的。"""

    if revision >= PROJECTION_REVISION:
        return False
    return keeps_at(rules, relative, PROJECTION_REVISION) and not keeps_at(
        rules, relative, revision
    )


__all__ = ["keeps_at", "newly_kept", "target_exclusion_reason_at"]
