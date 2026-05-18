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


MAAEND_DEFAULT_CONTROLLER = "Win32-Window"
MAAEND_FRONT_CONTROLLER = "Win32-Front"

MAAEND_RUN_INSTANCE_NAME_MAP = {
    MAAEND_DEFAULT_CONTROLLER: "电脑端-默认",
    MAAEND_FRONT_CONTROLLER: "电脑端-前台",
}

MAAEND_TASK_NAME_MAP = {
    "VisitFriends": "🤝拜访好友",
    "DijiangRewards": "🎁基建任务",
    "CreditShoppingN2": "🛍️信用点购物",
    "DeliveryJobs": "🚚转交委托",
    "SellProduct": "🛒售卖产品",
    "AutoStockpile": "📦自动囤货",
    "AutoStockStaple": "🏪购买稳定物资",
    "AutoSell": "💰售卖弹性物资",
    "EnvironmentMonitoring": "🌿环境监测",
    "DailyRewards": "📅日常奖励领取",
    "SeizeEntrustTask": "🌆抢委托",
    "AutoCollect": "🧺自动采集",
    "AutoUseSpMedication": "💊应急理智加强剂",
    "ResourceRecycleStation": "🦉资源回收站",
    "AutoEcoFarm": "🌾生态农场",
    "ProtocolSpace": "协议空间",
    "AutoEssence": "基质刷取",
}

MAAEND_PRESET_TASK_SWITCHES = [
    "VisitFriends",
    "DijiangRewards",
    "CreditShoppingN2",
    "DeliveryJobs",
    "SellProduct",
    "AutoStockpile",
    "AutoStockStaple",
    "AutoSell",
    "EnvironmentMonitoring",
    "DailyRewards",
    "SeizeEntrustTask",
    "AutoCollect",
    "AutoUseSpMedication",
    "ResourceRecycleStation",
    "AutoEcoFarm",
]

MAAEND_PRESET_TASK_CONFIG = {
    task_name: {"enabled": f"If{task_name}"}
    for task_name in MAAEND_PRESET_TASK_SWITCHES
}
MAAEND_PRESET_TASK_CONFIG["ProtocolSpace"] = {
    "enabled": "IfSanity",
    "core_options": [
        "SanityTaskType",
        "OperatorProgression",
        "WeaponProgression",
        "CrisisDrills",
        "RewardsSetOption",
    ],
}
MAAEND_PRESET_TASK_CONFIG["AutoEssence"] = {
    "enabled": "IfSanity",
    "core_options": ["AutoEssenceSpecifiedLocation"],
}

MAAEND_CORE_OPTION_FIELD_BOOK = {
    "SanityTaskType": "ProtocolSpaceTab",
}

MAAEND_CORE_OPTION_FIELD_REVERSE_BOOK = {
    value: key for key, value in MAAEND_CORE_OPTION_FIELD_BOOK.items()
}


def get_maaend_run_instance_name(controller_type: str) -> str:
    """按控制器类型获取 MXU 启动实例名"""

    return MAAEND_RUN_INSTANCE_NAME_MAP.get(
        controller_type, MAAEND_RUN_INSTANCE_NAME_MAP[MAAEND_DEFAULT_CONTROLLER]
    )


def is_maaend_front_controller(controller_type: str) -> bool:
    """判断是否为前台控制器"""

    return controller_type == MAAEND_FRONT_CONTROLLER
