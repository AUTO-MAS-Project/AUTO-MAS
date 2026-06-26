#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.


import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import maa
from maa.controller import MaaAdbInputMethodEnum, MaaAdbScreencapMethodEnum


@dataclass(frozen=True)
class MaaFWAdbEmulatorExtraCapability:
    """MaaFW ADB EmulatorExtras capability for one emulator family."""

    screencap: bool
    input: bool


_WIN_RUNTIME_DIRS = (
    ("runtimes", "win-x64"),
    ("maafw",),
    ("libs",),
    ("deps",),
    (),
)

_MAA_PACKAGE_RUNTIME_DIR = Path(maa.__file__).parent / "bin"

_EMULATOR_EXTRA_RELATION = {
    "mumu": MaaFWAdbEmulatorExtraCapability(screencap=True, input=True),
    "ldplayer": MaaFWAdbEmulatorExtraCapability(screencap=True, input=False),
}

_RUNTIME_LIBRARY_CACHE: dict[str, bool] = {}


@lru_cache(maxsize=1)
def _get_static_capability_flags() -> tuple[bool, bool]:
    adb_runtime_available = _maafw_has_runtime_library("MaaAdbControlUnit.dll")
    screencap_extra_available = (
        os.name == "nt"
        and adb_runtime_available
        and _enum_has_member(MaaAdbScreencapMethodEnum, "EmulatorExtras")
    )
    input_extra_available = (
        os.name == "nt"
        and adb_runtime_available
        and _enum_has_member(MaaAdbInputMethodEnum, "EmulatorExtras")
    )
    return screencap_extra_available, input_extra_available


def build_adb_emulator_extra_capabilities(
    project_path: str | Path,
) -> dict[str, MaaFWAdbEmulatorExtraCapability]:
    screencap_extra_available, input_extra_available = _get_static_capability_flags()

    project_extra_screencap = False
    project_extra_input = False
    root_path = Path(project_path)
    if _project_has_runtime_library(root_path, "MaaAdbControlUnit.dll"):
        project_extra_screencap = screencap_extra_available
        project_extra_input = input_extra_available

    return {
        emulator_type: MaaFWAdbEmulatorExtraCapability(
            screencap=(screencap_extra_available or project_extra_screencap) and relation.screencap,
            input=(input_extra_available or project_extra_input) and relation.input,
        )
        for emulator_type, relation in _EMULATOR_EXTRA_RELATION.items()
    }


def get_adb_emulator_extra_capability(
    project_path: str | Path,
    emulator_type: str | None,
) -> MaaFWAdbEmulatorExtraCapability:
    if not emulator_type:
        return MaaFWAdbEmulatorExtraCapability(screencap=False, input=False)
    return build_adb_emulator_extra_capabilities(project_path).get(
        emulator_type,
        MaaFWAdbEmulatorExtraCapability(screencap=False, input=False),
    )


def _maafw_has_runtime_library(library_name: str) -> bool:
    cache_key = f"maa:{library_name}"
    if cache_key in _RUNTIME_LIBRARY_CACHE:
        return _RUNTIME_LIBRARY_CACHE[cache_key]
    result = (_MAA_PACKAGE_RUNTIME_DIR / library_name).is_file()
    _RUNTIME_LIBRARY_CACHE[cache_key] = result
    return result


def _project_has_runtime_library(root_path: Path, library_name: str) -> bool:
    cache_key = f"proj:{str(root_path)}:{library_name}"
    if cache_key in _RUNTIME_LIBRARY_CACHE:
        return _RUNTIME_LIBRARY_CACHE[cache_key]
    for parts in _WIN_RUNTIME_DIRS:
        if (root_path.joinpath(*parts) / library_name).is_file():
            _RUNTIME_LIBRARY_CACHE[cache_key] = True
            return True
    _RUNTIME_LIBRARY_CACHE[cache_key] = False
    return False


def _enum_has_member(enum_class: type, member_name: str) -> bool:
    return member_name in getattr(enum_class, "__members__", {})
