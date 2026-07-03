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


from .interface_loader import MaaFWInterfaceLoadError, load_interface_model
from .interface_models import MaaFWInterface
from .manager import MaaFWManager
from .runner import MaaFWDeviceConfig, MaaFWRunner, MaaFWRunResult
from .run_plan import MaaFWRunPlanError, build_maafw_run_plan

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
