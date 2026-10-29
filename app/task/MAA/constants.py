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


MATERIALS_MAP = {
    "3141": "源石碎片",
    "3003": "赤金",
    "4006": "采购凭证",
    "3301": "技巧概要·卷1",
    "3302": "技巧概要·卷2",
    "3303": "技巧概要·卷3",
    "30051": "双酮",
    "30052": "酮凝集",
    "30053": "酮凝集组",
    "30054": "酮阵列",
    "30041": "异铁碎片",
    "30042": "异铁",
    "30043": "异铁组",
    "30044": "异铁块",
    "30021": "代糖",
    "30022": "糖",
    "30023": "糖组",
    "30024": "糖聚块",
    "30031": "酯原料",
    "30032": "聚酸酯",
    "30033": "聚酸酯组",
    "30034": "聚酸酯块",
    "30061": "破损装置",
    "30062": "装置",
    "30063": "全新装置",
    "30064": "改量装置",
    "30011": "源岩",
    "30012": "固源岩",
    "30013": "固源岩组",
    "30014": "提纯源岩",
    "30103": "RMA70-12",
    "30104": "RMA70-24",
    "30093": "研磨石",
    "30094": "五水研磨石",
    "30083": "轻锰矿",
    "30084": "三水锰矿",
    "30073": "扭转醇",
    "30074": "白马醇",
    "31013": "凝胶",
    "31014": "聚合凝胶",
    "31023": "炽合金",
    "31024": "炽合金块",
    "31033": "晶体元件",
    "31034": "晶体电路",
    "31043": "半自然溶剂",
    "31044": "精炼溶剂",
    "31053": "化合切削液",
    "31054": "切削原液",
    "31063": "转质盐组",
    "31064": "转质盐聚块",
    "31073": "褐素纤维",
    "31074": "固化纤维板",
    "31083": "环烃聚质",
    "31084": "环烃预制体",
    "31093": "类凝结核",
    "31094": "手性屈光体",
    "31103": "液化高能气体",
    "31104": "液化醚吸聚体",
    "31113": "电极单元",
    "31114": "聚能动力单元",
    "30115": "聚合剂",
    "30125": "双极纳米片",
    "30135": "D32钢",
    "30145": "晶体电子单元",
    "30155": "烧结核凝晶",
    "30165": "重相位对映体",
    "3105": "龙骨",
    "3401": "家具零件",
    "3131": "基础加固建材",
    "3132": "进阶加固建材",
    "3133": "高级加固建材",
    "3112": "碳",
    "3113": "碳素",
    "3114": "碳素组",
    "32001": "芯片助剂",
    "3213": "先锋双芯片",
    "3223": "近卫双芯片",
    "3233": "重装双芯片",
    "3243": "狙击双芯片",
    "3253": "术师双芯片",
    "3263": "医疗双芯片",
    "3273": "辅助双芯片",
    "3283": "特种双芯片",
    "3212": "先锋芯片组",
    "3222": "近卫芯片组",
    "3232": "重装芯片组",
    "3242": "狙击芯片组",
    "3252": "术师芯片组",
    "3262": "医疗芯片组",
    "3272": "辅助芯片组",
    "3282": "特种芯片组",
    "3211": "先锋芯片",
    "3221": "近卫芯片",
    "3231": "重装芯片",
    "3241": "狙击芯片",
    "3251": "术师芯片",
    "3261": "医疗芯片",
    "3271": "辅助芯片",
    "3281": "特种芯片",
    "PR-A": "医疗/重装芯片",
    "PR-B": "术师/狙击芯片",
    "PR-C": "先锋/辅助芯片",
    "PR-D": "近卫/特种芯片",
}
"""掉落物索引表"""
