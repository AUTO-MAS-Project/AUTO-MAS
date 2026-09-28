"""已登记的载荷按哪一版投影规则建的：旧版规则的复刻，只用来算「当前规则比旧规则多留了什么」。

``projection.PROJECTION_REVISION`` 每加一，就在这里留一份上一版规则的判定（不跟着当前规则
改），``projection_heal`` 用它找出旧载荷漏装的文件：**当前规则保留、载荷那一版规则剔掉**。
只比两版规则之差，所以没被误伤的项目一个文件都不会补，白名单之外的取舍（顶层大目录）
也不会被当成缺文件。白名单目标（``ProjectionRules.targets``）两边用同一组，按当前规则算。

- 版本 0（v5.6.0）：分类表的目录名在任何深度都算，完整目标（resource 目录）里也按整张表剔。
"""

from __future__ import annotations

from pathlib import Path

from .projection import (
    EXCLUDED_DIRECTORY_REASONS,
    KNOWN_RUNTIME_STEMS,
    KNOWN_UI_SHELL_STEMS,
    PROJECTION_REVISION,
    ROOT,
    ProjectionRules,
    TargetMode,
    exclusion_reason,
    target_exclusion_reason,
)


def _exclusion_reason_v0(path: Path, *, is_directory: bool = False) -> str | None:
    """v5.6.0 的 ``exclusion_reason``：目录名在任何深度都按分类表判，文件名规则不变。"""

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
    return exclusion_reason(Path(path.name))


def _target_exclusion_reason_v0(
    path: Path, *, target: Path, mode: TargetMode, target_is_directory: bool
) -> str | None:
    """v5.6.0 的 ``target_exclusion_reason``：完整目标里照样按整张分类表剔，原样带走的
    运行时目录新旧同一口径。"""

    if not mode.complete or not mode.allow_excluded_root or target == ROOT:
        return _exclusion_reason_v0(path)
    if mode.verbatim_runtime:
        return target_exclusion_reason(
            path,
            target=target,
            mode=mode,
            target_is_directory=target_is_directory,
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
    return target_exclusion_reason(
        path,
        target=target,
        mode=mode,
        target_is_directory=target_is_directory,
        base=rules.base_relative,
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
