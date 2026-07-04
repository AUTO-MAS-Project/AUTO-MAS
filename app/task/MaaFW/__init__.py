#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.


__all__ = [
    "MaaFWDeviceConfig",
    "MaaFWInterface",
    "MaaFWInterfaceLoadError",
    "MaaFWManager",
    "MaaFWRunResult",
    "MaaFWRunner",
    "MaaFWRunPlanError",
    "build_maafw_run_plan",
    "load_interface_model",
]


def __getattr__(name: str):
    if name == "MaaFWDeviceConfig":
        from .runner import MaaFWDeviceConfig

        return MaaFWDeviceConfig
    if name == "MaaFWInterface":
        from .interface_models import MaaFWInterface

        return MaaFWInterface
    if name == "MaaFWInterfaceLoadError":
        from .interface_loader import MaaFWInterfaceLoadError

        return MaaFWInterfaceLoadError
    if name == "MaaFWManager":
        from .manager import MaaFWManager

        return MaaFWManager
    if name == "MaaFWRunResult":
        from .runner import MaaFWRunResult

        return MaaFWRunResult
    if name == "MaaFWRunner":
        from .runner import MaaFWRunner

        return MaaFWRunner
    if name == "MaaFWRunPlanError":
        from .run_plan import MaaFWRunPlanError

        return MaaFWRunPlanError
    if name == "build_maafw_run_plan":
        from .run_plan import build_maafw_run_plan

        return build_maafw_run_plan
    if name == "load_interface_model":
        from .interface_loader import load_interface_model

        return load_interface_model
    raise AttributeError(name)
