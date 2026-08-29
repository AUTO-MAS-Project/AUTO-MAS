from __future__ import annotations

import hashlib
import json
import platform as platform_module
import re
import sys
import sysconfig
from collections.abc import Iterable, Mapping
from typing import Any

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name


IDENTITY_SCHEMA_VERSION = 1
RUNTIME_ID_PREFIX = "maafw-runtime-"
FALLBACK_REQUIREMENT_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


class MaaFWRuntimeIdentityError(ValueError):
    """Raised when requirements cannot form a stable runtime selector."""


def canonicalize_requirements(requirements: Iterable[str]) -> tuple[str, ...]:
    """Return an order-independent canonical PEP 508 requirement set."""

    canonical: set[str] = set()
    for raw_value in requirements:
        if not isinstance(raw_value, str):
            raise MaaFWRuntimeIdentityError("runtime requirements must be strings")
        value = raw_value.strip()
        if not value or value.startswith("#"):
            continue
        if _looks_like_local_requirement(value):
            raise MaaFWRuntimeIdentityError(
                "shared runtime requirements cannot contain local/editable/"
                f"included paths: {value}"
            )
        canonical.add(_canonicalize_requirement(value))
    if not canonical:
        raise MaaFWRuntimeIdentityError("runtime requirement set cannot be empty")
    return tuple(sorted(canonical, key=str.casefold))


def build_runtime_identity(
    requirements: Iterable[str],
    *,
    python_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    canonical = canonicalize_requirements(requirements)
    if python_identity is None:
        # The host interpreter participates with the same full physical
        # identity as an explicitly selected interpreter.  This lets a native
        # Agent project and a Python Agent project reuse one environment when
        # their requirement selector and actual interpreter are identical,
        # while a host patch upgrade correctly selects a new runtime.
        implementation = getattr(sys.implementation, "name", "python")
        cache_tag = getattr(sys.implementation, "cache_tag", None) or "unknown"
        soabi = str(sysconfig.get_config_var("SOABI") or "unknown")
        python_version = platform_module.python_version()
        target_platform = sysconfig.get_platform() or sys.platform
        architecture = platform_module.machine() or "unknown"
    else:
        implementation = _required_python_identity_value(
            python_identity,
            "implementation",
        )
        cache_tag = _required_python_identity_value(
            python_identity,
            "cacheTag",
        )
        soabi = _required_python_identity_value(python_identity, "soabi")
        # Explicit multi-ABI routes are based on a probed interpreter.  Keep
        # its full patch version in the selector so an exact request such as
        # ``==3.13.14`` can never collide with, or reuse, a 3.13.13 runtime.
        python_version = _required_python_identity_value(
            python_identity,
            "version",
            fallback_key="pythonVersion",
        )
        target_platform = _required_python_identity_value(
            python_identity,
            "platform",
        )
        architecture = _required_python_identity_value(
            python_identity,
            "architecture",
        )
    python_abi = f"{implementation}:{cache_tag}:{soabi}"
    return {
        "schemaVersion": IDENTITY_SCHEMA_VERSION,
        "requirements": list(canonical),
        "pythonAbi": python_abi,
        "pythonVersion": python_version,
        "platform": target_platform,
        "architecture": architecture,
    }


def runtime_id_for_identity(identity: dict[str, Any]) -> str:
    payload = json.dumps(
        identity,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"{RUNTIME_ID_PREFIX}{hashlib.sha256(payload).hexdigest()[:24]}"


def build_runtime_id(
    requirements: Iterable[str],
    *,
    python_identity: Mapping[str, Any] | None = None,
) -> str:
    return runtime_id_for_identity(
        build_runtime_identity(requirements, python_identity=python_identity)
    )


def _required_python_identity_value(
    identity: Mapping[str, Any],
    key: str,
    *,
    fallback_key: str | None = None,
) -> str:
    value = identity.get(key)
    if (value is None or not str(value).strip()) and fallback_key is not None:
        value = identity.get(fallback_key)
    normalized = str(value or "").strip()
    if not normalized:
        raise MaaFWRuntimeIdentityError(
            f"probed python identity is missing {key}"
        )
    return normalized


def requirement_distribution_name(requirement: str) -> str | None:
    try:
        return canonicalize_name(Requirement(requirement).name)
    except InvalidRequirement:
        match = FALLBACK_REQUIREMENT_NAME_RE.match(requirement)
        return canonicalize_name(match.group(1)) if match is not None else None


def find_maafw_requirement(requirements: Iterable[str]) -> str | None:
    return next(
        (
            requirement
            for requirement in canonicalize_requirements(requirements)
            if requirement_distribution_name(requirement) == "maafw"
        ),
        None,
    )


def infer_exact_maafw_version(requirement: str | None) -> str | None:
    if not requirement:
        return None
    try:
        parsed = Requirement(requirement)
    except InvalidRequirement:
        return None
    if canonicalize_name(parsed.name) != "maafw":
        return None
    specifiers = list(parsed.specifier)
    if len(specifiers) != 1 or specifiers[0].operator not in {"==", "==="}:
        return None
    value = specifiers[0].version.strip()
    return None if not value or "*" in value else value


def _canonicalize_requirement(value: str) -> str:
    try:
        parsed = Requirement(value)
    except InvalidRequirement:
        # Preserve pip-compatible non-PEP-508 inputs in a stable textual form.
        # The caller remains responsible for making local paths portable.
        return " ".join(value.replace("\\", "/").split())

    name = canonicalize_name(parsed.name)
    extras = sorted(canonicalize_name(extra) for extra in parsed.extras)
    if extras:
        name = f"{name}[{','.join(extras)}]"

    if parsed.url:
        result = f"{name} @ {parsed.url.strip()}"
    else:
        specifiers = sorted(str(item) for item in parsed.specifier)
        result = f"{name}{','.join(specifiers)}"
    if parsed.marker is not None:
        result = f"{result}; {parsed.marker}"
    return result


def _looks_like_local_requirement(value: str) -> bool:
    normalized = value.strip().replace("\\", "/")
    lowered = normalized.casefold()
    if lowered.startswith("-"):
        return True
    if lowered.startswith(("./", "../", "/", "~/", "file:")):
        return True
    if re.match(r"^[a-zA-Z]:/", normalized):
        return True
    if " @ file:" in lowered or lowered.endswith((".whl", ".zip", ".tar.gz")):
        return True
    try:
        parsed = Requirement(value)
    except InvalidRequirement:
        return "/" in normalized
    if not parsed.url:
        return False
    normalized_url = parsed.url.casefold()
    return normalized_url.startswith("file:") or "+file:" in normalized_url
