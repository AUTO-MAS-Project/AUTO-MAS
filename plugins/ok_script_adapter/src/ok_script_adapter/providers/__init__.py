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
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""ok-script 项目 provider 集合。"""

import importlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ..common.provider import (
    OkScriptProvider,
    normalize_ok_script_resource_name,
    read_app_json_resource_name,
    read_pyappify_resource_name,
)

OK_SCRIPT_PROVIDER_PROFILE_ABI_VERSION = 1
"""Internal ABI expected from each built-in provider profile module."""

ProviderProfileState = Literal["pending", "available", "disabled"]


@dataclass(frozen=True, slots=True)
class ProviderProfileSpec:
    """Static metadata required to load one built-in provider on demand."""

    resource_name: str
    module_name: str
    provider_attribute: str
    abi_version: int = OK_SCRIPT_PROVIDER_PROFILE_ABI_VERSION


@dataclass(frozen=True, slots=True)
class ProviderProfileStatus:
    """Diagnostic state for one built-in provider profile."""

    resource_name: str
    module_name: str
    abi_version: int
    state: ProviderProfileState
    detail: str = ""

    @property
    def available(self) -> bool:
        """Whether this profile loaded and passed its internal ABI check."""

        return self.state == "available"


OK_SCRIPT_PROVIDER_PROFILES: tuple[ProviderProfileSpec, ...] = (
    ProviderProfileSpec(
        resource_name="ok-ef",
        module_name="ok_script_adapter.providers.okef",
        provider_attribute="OKEF_PROVIDER",
    ),
    ProviderProfileSpec(
        resource_name="ok-ww",
        module_name="ok_script_adapter.providers.okww",
        provider_attribute="OKWW_PROVIDER",
    ),
    ProviderProfileSpec(
        resource_name="ok-nte",
        module_name="ok_script_adapter.providers.oknte",
        provider_attribute="OKNTE_PROVIDER",
    ),
)

_PROFILE_SPECS = {
    profile.resource_name: profile for profile in OK_SCRIPT_PROVIDER_PROFILES
}
_PROFILE_CACHE: dict[str, OkScriptProvider | None] = {}
_PROFILE_STATUS: dict[str, ProviderProfileStatus] = {}


def _profile_status(
    profile: ProviderProfileSpec,
    *,
    state: ProviderProfileState,
    detail: str = "",
) -> ProviderProfileStatus:
    return ProviderProfileStatus(
        resource_name=profile.resource_name,
        module_name=profile.module_name,
        abi_version=profile.abi_version,
        state=state,
        detail=detail,
    )


def get_ok_script_provider_profile_status(
    resource_name: object,
) -> ProviderProfileStatus | None:
    """Return cached diagnostic state without loading a provider profile."""

    normalized = normalize_ok_script_resource_name(resource_name)
    profile = _PROFILE_SPECS.get(normalized)
    if profile is None:
        return None
    return _PROFILE_STATUS.get(
        normalized,
        _profile_status(profile, state="pending"),
    )


def list_ok_script_provider_profile_statuses() -> tuple[ProviderProfileStatus, ...]:
    """Return all built-in profile states without eagerly importing them."""

    statuses: list[ProviderProfileStatus] = []
    for profile in OK_SCRIPT_PROVIDER_PROFILES:
        status = get_ok_script_provider_profile_status(profile.resource_name)
        if status is not None:
            statuses.append(status)
    return tuple(statuses)


def clear_ok_script_provider_cache(resource_name: object | None = None) -> None:
    """Forget provider load results so a later plugin lifecycle can retry them."""

    if resource_name is None:
        _PROFILE_CACHE.clear()
        _PROFILE_STATUS.clear()
        return

    normalized = normalize_ok_script_resource_name(resource_name)
    if normalized not in _PROFILE_SPECS:
        return
    _PROFILE_CACHE.pop(normalized, None)
    _PROFILE_STATUS.pop(normalized, None)


def _disable_profile(
    profile: ProviderProfileSpec,
    detail: str,
) -> None:
    _PROFILE_CACHE[profile.resource_name] = None
    _PROFILE_STATUS[profile.resource_name] = _profile_status(
        profile,
        state="disabled",
        detail=detail,
    )


def _load_ok_script_provider_profile(
    profile: ProviderProfileSpec,
) -> OkScriptProvider | None:
    if profile.resource_name in _PROFILE_CACHE:
        return _PROFILE_CACHE[profile.resource_name]

    try:
        module = importlib.import_module(profile.module_name)
        actual_abi_version = getattr(
            module,
            "OK_SCRIPT_PROVIDER_PROFILE_ABI_VERSION",
            None,
        )
        if actual_abi_version != profile.abi_version:
            raise RuntimeError(
                "provider profile ABI mismatch: "
                f"expected {profile.abi_version}, got {actual_abi_version!r}"
            )

        provider = getattr(module, profile.provider_attribute)
        if not isinstance(provider, OkScriptProvider):
            raise TypeError(
                f"{profile.provider_attribute} is not an OkScriptProvider"
            )
        if (
            normalize_ok_script_resource_name(provider.resource_name)
            != profile.resource_name
        ):
            raise ValueError(
                "provider resource name mismatch: "
                f"expected {profile.resource_name}, got {provider.resource_name!r}"
            )
    except Exception as exc:
        _disable_profile(profile, f"{type(exc).__name__}: {exc}")
        return None

    _PROFILE_CACHE[profile.resource_name] = provider
    _PROFILE_STATUS[profile.resource_name] = _profile_status(
        profile,
        state="available",
    )
    return provider


def _iter_ok_script_providers() -> Iterator[OkScriptProvider]:
    for profile in OK_SCRIPT_PROVIDER_PROFILES:
        provider = _load_ok_script_provider_profile(profile)
        if provider is not None:
            yield provider


def get_ok_script_provider(resource_name: object) -> OkScriptProvider | None:
    """按 ok-script 资源名获取当前宿主内置 provider。"""

    normalized = normalize_ok_script_resource_name(resource_name)
    if not normalized:
        return None
    profile = _PROFILE_SPECS.get(normalized)
    if profile is None:
        return None
    return _load_ok_script_provider_profile(profile)


def detect_ok_script_provider(
    root_path: str | Path,
    resource_name: object = "",
) -> OkScriptProvider | None:
    """按已保存资源名或项目根目录识别 ok-script provider。"""

    root = Path(root_path)
    if not root.is_dir():
        return None

    # 根目录是当前运行的事实来源，避免切换项目目录后仍使用旧 ResourceName。
    pyappify_resource_name = read_pyappify_resource_name(root)
    if pyappify_resource_name:
        return get_ok_script_provider(pyappify_resource_name)

    for candidate in _iter_ok_script_providers():
        app_json_resource_name = read_app_json_resource_name(
            candidate.app_json_path(root)
        )
        if app_json_resource_name:
            return get_ok_script_provider(app_json_resource_name)

    for candidate in _iter_ok_script_providers():
        if candidate.exe_path(root).is_file() and candidate.config_path(root).is_dir():
            return candidate

    return get_ok_script_provider(resource_name)
