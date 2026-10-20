#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 ClozyA
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

"""MAA 专项运行、游戏更新与关卡展示常量。"""

MAA_RUN_MOOD_BOOK = {
    "GreenTicketStore": "绿票商店",
    "Annihilation": "剿灭",
    "Routine": "日常",
}
"""MAA运行模式映射表"""

MAA_MODE_TIME_LIMIT_BOOK = {
    "GreenTicketStore": "RoutineTimeLimit",
    "Annihilation": "AnnihilationTimeLimit",
    "Routine": "RoutineTimeLimit",
}
"""MAA运行模式对应的超时配置项：绿票商店只买一次商店，复用日常时限"""

MAA_EMULATOR_CONNECT_CONFIG_BOOK = {
    "mumu": "MuMuEmulator12",
    "ldplayer": "LDPlayer",
    "general": "General",
}
"""MAS 模拟器类型到 MAA 连接预设名的映射

MAA 的连接预设决定 MaaCore 走哪套截图 / 触控通道。MAS 运行前已经确定设备，
按真实模拟器类型写入，避免 MAA 自动检测弹出选择框。
"""

MAA_TASKS = [
    "StartUp",
    "DepotMaintain",
    "Fight",
    "Infrast",
    "Recruit",
    "Mall",
    "Award",
    "SwitchTheme",
]
"""MAS 托管的 MAA 任务类型

只列 MAS 会接管开关与配置的任务。上游还有的类型（自动肉鸽、生息演算、自定义
任务等）对 MAS 是未知任务：队列里遇到就原样透传，不合成、不接管、不判定。
"""

MAA_TASKS_ZH = [
    "开始唤醒",
    "库存保持与干员养成",
    "理智任务",
    "基建换班",
    "自动公招",
    "信用收支",
    "领取奖励",
    "更换主题",
]
"""MAA_TASKS 对应的中文任务名（与 MAA_TASKS 逐位对齐）"""

MAA_DEPOT_EXCLUDED_ITEM_IDS = {
    "3213",
    "3223",
    "3233",
    "3243",
    "3253",
    "3263",
    "3273",
    "3283",
    "7001",
    "7002",
    "7003",
    "7004",
    "4004",
    "4005",
    "3105",
    "3131",
    "3132",
    "3133",
    "6001",
    "3141",
    "4002",
    "32001",
    "30115",
    "30125",
    "30135",
    "30145",
    "30155",
    "30165",
    # 无对应可刷关卡：家具零件（基建产出）、合成玉（源石兑换）、声望（战斗经验）
    "3401",
    "4003",
    "5001",
}
"""MAA 库存保持不可刷取物品 ID"""

ARKNIGHTS_PACKAGE_NAME = {
    "Official": "com.hypergryph.arknights",
    "Bilibili": "com.hypergryph.arknights.bilibili",
    "YoStarEN": "com.YoStarEN.Arknights",
    "YoStarJP": "com.YoStarJP.Arknights",
    "YoStarKR": "com.YoStarKR.Arknights",
    "txwy": "tw.txwy.and.arknights",
}
"""明日方舟包名映射表"""

ARKNIGHTS_VERSION_API_SERVER = {
    "Official": "official",
    "Bilibili": "b",
}
"""明日方舟版本接口服务器标识映射表

仅收录已实测可用的服务器；外服与台服未找到稳定的公开版本接口，
不在此表中的服务器会跳过客户端版本检查。
"""

ARKNIGHTS_OFFICIAL_APK_URL = "https://ak.hypergryph.com/downloads/android_lastest"
"""明日方舟官服安卓包下载入口（302 跳转至启动器再跳至 CDN 实际包地址）"""

RESOURCE_STAGE_DATE_TEXT = {
    "LS-6": "经验-6/5 | 常驻开放",
    "CE-6": "龙门币-6/5 | 二四六日开放",
    "AP-5": "红票-5 | 一四六日开放",
    "CA-5": "技能-5 | 二三五日开放",
    "SK-5": "碳-5 | 一三五六开放",
    "PR-A-1": "奶/盾芯片 | 一四五日开放",
    "PR-A-2": "奶/盾芯片组 | 一四五日开放",
    "PR-B-1": "术/狙芯片 | 一二五六日开放",
    "PR-B-2": "术/狙芯片组 | 一二五六日开放",
    "PR-C-1": "先/辅芯片 | 三四六日开放",
    "PR-C-2": "先/辅芯片组 | 三四六日开放",
    "PR-D-1": "近/特芯片 | 二三六日开放",
    "PR-D-2": "近/特芯片组 | 二三六日开放",
}
"""常规资源关开放日文本映射"""


RESOURCE_STAGE_DROP_INFO = {
    "CE-6": {
        "Display": "CE-6",
        "Value": "CE-6",
        "Drop": "4001",
        "DropName": "龙门币",
        "Activity": {"Tip": "二四六日", "StageName": "资源关卡"},
    },
    "AP-5": {
        "Display": "AP-5",
        "Value": "AP-5",
        "Drop": "4006",
        "DropName": "采购凭证",
        "Activity": {"Tip": "一四六日", "StageName": "资源关卡"},
    },
    "CA-5": {
        "Display": "CA-5",
        "Value": "CA-5",
        "Drop": "3303",
        "DropName": "技巧概要",
        "Activity": {"Tip": "二三五日", "StageName": "资源关卡"},
    },
    "LS-6": {
        "Display": "LS-6",
        "Value": "LS-6",
        "Drop": "2004",
        "DropName": "作战记录",
        "Activity": {"Tip": "常驻开放", "StageName": "资源关卡"},
    },
    "SK-5": {
        "Display": "SK-5",
        "Value": "SK-5",
        "Drop": "3114",
        "DropName": "碳素组",
        "Activity": {"Tip": "一三五六", "StageName": "资源关卡"},
    },
    "PR-A-1": {
        "Display": "PR-A",
        "Value": "PR-A",
        "Drop": "PR-A",
        "DropName": "奶/盾芯片",
        "Activity": {"Tip": "一四五日", "StageName": "资源关卡"},
    },
    "PR-B-1": {
        "Display": "PR-B",
        "Value": "PR-B",
        "Drop": "PR-B",
        "DropName": "术/狙芯片",
        "Activity": {"Tip": "一二五六", "StageName": "资源关卡"},
    },
    "PR-C-1": {
        "Display": "PR-C",
        "Value": "PR-C",
        "Drop": "PR-C",
        "DropName": "先/辅芯片",
        "Activity": {"Tip": "三四六日", "StageName": "资源关卡"},
    },
    "PR-D-1": {
        "Display": "PR-D",
        "Value": "PR-D",
        "Drop": "PR-D",
        "DropName": "近/特芯片",
        "Activity": {"Tip": "二三六日", "StageName": "资源关卡"},
    },
}
"""常规资源关掉落信息"""
