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

#   Contact: DLmaster_361@163.com


from app.utils.constants import PLAN_CONSUMER_VALUES

from .emulator import *
from .plan import *
from .queue import *
from .script import *
from .setting import *
from .shared import *
from .shared import (
    _normalize_maaend_sanity_task_type as _normalize_maaend_sanity_task_type,
)
from .tools import *

CLASS_BOOK = {
    "MAA": MaaConfig,
    "MaaEnd": MaaEndConfig,
    "SRC": SrcConfig,
    "M9A": M9AConfig,
    "MaaFW": MaaFWConfig,
    "General": GeneralConfig,
    "Okww": OkwwConfig,
    "OkNte": OkNteConfig,
    "HSR": HSRConfig,
    "BetterGI": BetterGIConfig,
    "ZzzOd": ZzzOdConfig,
    "BAAH": BAAHConfig,
    "Whimbox": WhimboxConfig,
    "MSS": MSSConfig,
}

PLAN_BOOK = {
    "MaaPlanConfig": {
        "create_type": "MaaPlan",
        "config_class": MaaPlanConfig,
        "consumer": PLAN_CONSUMER_VALUES[0],
        "script_class": MaaConfig,
        "field_group": "Stage",
        "field_name": "StageMode",
    },
    "MaaEndPlanConfig": {
        "create_type": "MaaEndPlan",
        "config_class": MaaEndPlanConfig,
        "consumer": PLAN_CONSUMER_VALUES[1],
        "script_class": MaaEndConfig,
        "field_group": "Info",
        "field_name": "SanityMode",
    },
    "BAAHPlanConfig": {
        "create_type": "BAAHPlan",
        "config_class": BAAHPlanConfig,
        "consumer": PLAN_CONSUMER_VALUES[2],
        "script_class": BAAHConfig,
        "field_group": "Info",
        "field_name": "StageMode",
    },
    "MSSPlanConfig": {
        "create_type": "MSSPlan",
        "config_class": MSSPlanConfig,
        # MSS 排在 baah 之后，位置索引跟着往后挪一位
        "consumer": PLAN_CONSUMER_VALUES[3],
        "script_class": MSSConfig,
        "field_group": "Info",
        "field_name": "PlanMode",
    },
}
