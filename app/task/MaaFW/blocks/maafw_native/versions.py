"""maafw 版本号与 requirement 的规范化（标准库 + ``packaging``）。

运行池（``runtime_pool.binding``）、agent 环境与原生库识别共用这一套解析，两侧算出的
版本才不会岔开。
"""

from __future__ import annotations

import re
from typing import Any

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

REQUIREMENT_NAME_RE = re.compile(
    r"^\s*([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)"
    r"\s*(?:\[[^\]]+\])?\s*(?:===|[<>=!~]=?|@|;|\s|$)"
)


class MaaFWBindingError(RuntimeError):
    """binding / native 目录准备失败。文案面向用户，调用方原样带出。

    版本号、requirement 不合法时（:func:`normalize_version`、:func:`parse_maafw_requirement`）
    也抛它；运行池的 binding 各类失败（``runtime_pool.binding``）都是它的子类。
    """


def normalize_version(value: Any) -> str:
    text = str(value or "").strip()
    try:
        return str(Version(text))
    except InvalidVersion as exc:
        raise MaaFWBindingError(f"maafw 版本不合法: {value!r}") from exc


def parse_maafw_requirement(requirement: str) -> Requirement:
    try:
        parsed = Requirement(str(requirement).strip())
    except InvalidRequirement as exc:
        raise MaaFWBindingError(f"maafw requirement 不合法: {requirement!r}") from exc
    if canonicalize_name(parsed.name) != "maafw":
        raise MaaFWBindingError(f"requirement 必须约束 maafw: {requirement!r}")
    return parsed


def exact_version_of(requirement: str) -> str | None:
    """``maafw==5.13.0`` → ``5.13.0``；范围 / 无约束 → None。"""

    parsed = parse_maafw_requirement(requirement)
    specifiers = list(parsed.specifier)
    if len(specifiers) != 1 or specifiers[0].operator not in {"==", "==="}:
        return None
    value = specifiers[0].version.strip()
    if not value or "*" in value:
        return None
    return normalize_version(value)


def requirement_distribution_name(requirement: str) -> str | None:
    match = REQUIREMENT_NAME_RE.match(requirement)
    if match is None:
        return None
    return re.sub(r"[-_.]+", "-", match.group(1)).lower()


def normalize_maafw_requirement(
    value: str,
    *,
    allow_unconstrained: bool = False,
) -> str:
    raw_value = value.strip()
    if not raw_value:
        raise RuntimeError("MaaFW runtime constraint 不能为空")
    if requirement_distribution_name(raw_value) != "maafw":
        if raw_value[0].isdigit() or raw_value[0] in {"v", "V"}:
            raw_value = f"maafw=={raw_value.lstrip('vV')}"
        elif raw_value[0] in {"<", ">", "=", "!", "~"}:
            raw_value = f"maafw{raw_value}"
        else:
            raise RuntimeError(f"无效的 MaaFW runtime constraint: {value}")
    try:
        requirement = Requirement(raw_value)
    except InvalidRequirement as exc:
        raise RuntimeError(f"无效的 MaaFW runtime constraint: {value}") from exc
    if canonicalize_name(requirement.name) != "maafw":
        raise RuntimeError(f"runtime constraint 必须约束 maafw: {value}")
    if (
        not allow_unconstrained
        and not requirement.url
        and not list(requirement.specifier)
    ):
        raise RuntimeError(
            "MaaFW runtime requirement 不能是未约束的 'maafw'；请显式声明版本或版本范围"
        )
    return str(requirement)


__all__ = [
    "REQUIREMENT_NAME_RE",
    "MaaFWBindingError",
    "exact_version_of",
    "normalize_maafw_requirement",
    "normalize_version",
    "parse_maafw_requirement",
    "requirement_distribution_name",
]
