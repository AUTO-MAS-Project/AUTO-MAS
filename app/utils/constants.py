#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 ClozyA
#   Copyright © 2025 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


from datetime import datetime

RESOURCE_STAGE_INFO = [
    {"value": "-", "text": "当前/上次", "days": [1, 2, 3, 4, 5, 6, 7]},
    {"value": "1-7", "text": "1-7", "days": [1, 2, 3, 4, 5, 6, 7]},
    {"value": "R8-11", "text": "R8-11", "days": [1, 2, 3, 4, 5, 6, 7]},
    {"value": "12-17-HARD", "text": "12-17-HARD", "days": [1, 2, 3, 4, 5, 6, 7]},
    {"value": "LS-6", "text": "经验-6/5", "days": [1, 2, 3, 4, 5, 6, 7]},
    {"value": "CE-6", "text": "龙门币-6/5", "days": [2, 4, 6, 7]},
    {"value": "AP-5", "text": "红票-5", "days": [1, 4, 6, 7]},
    {"value": "CA-5", "text": "技能-5", "days": [2, 3, 5, 7]},
    {"value": "SK-5", "text": "碳-5", "days": [1, 3, 5, 6]},
    {"value": "PR-A-1", "text": "奶/盾芯片", "days": [1, 4, 5, 7]},
    {"value": "PR-A-2", "text": "奶/盾芯片组", "days": [1, 4, 5, 7]},
    {"value": "PR-B-1", "text": "术/狙芯片", "days": [1, 2, 5, 6]},
    {"value": "PR-B-2", "text": "术/狙芯片组", "days": [1, 2, 5, 6]},
    {"value": "PR-C-1", "text": "先/辅芯片", "days": [3, 4, 6, 7]},
    {"value": "PR-C-2", "text": "先/辅芯片组", "days": [3, 4, 6, 7]},
    {"value": "PR-D-1", "text": "近/特芯片", "days": [2, 3, 6, 7]},
    {"value": "PR-D-2", "text": "近/特芯片组", "days": [2, 3, 6, 7]},
]
"""常规资源关信息"""


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
    "4001": "龙门币",
    "4006": "采购凭证",
    "2004": "高级作战记录",
    "2003": "中级作战记录",
    "2002": "初级作战记录",
    "2001": "基础作战记录",
    "3303": "技巧概要·卷3",
    "3302": "技巧概要·卷2",
    "3301": "技巧概要·卷1",
    "30165": "重相位对映体",
    "30155": "烧结核凝晶",
    "30145": "晶体电子单元",
    "30135": "D32钢",
    "30125": "双极纳米片",
    "30115": "聚合剂",
    "31094": "手性屈光体",
    "31093": "类凝结核",
    "31084": "环烃预制体",
    "31083": "环烃聚质",
    "31074": "固化纤维板",
    "31073": "褐素纤维",
    "31064": "转质盐聚块",
    "31063": "转质盐组",
    "31054": "切削原液",
    "31053": "化合切削液",
    "31044": "精炼溶剂",
    "31043": "半自然溶剂",
    "31034": "晶体电路",
    "31033": "晶体元件",
    "31024": "炽合金块",
    "31023": "炽合金",
    "31014": "聚合凝胶",
    "31013": "凝胶",
    "30074": "白马醇",
    "30073": "扭转醇",
    "30084": "三水锰矿",
    "30083": "轻锰矿",
    "30094": "五水研磨石",
    "30093": "研磨石",
    "30104": "RMA70-24",
    "30103": "RMA70-12",
    "30014": "提纯源岩",
    "30013": "固源岩组",
    "30012": "固源岩",
    "30011": "源岩",
    "30064": "改量装置",
    "30063": "全新装置",
    "30062": "装置",
    "30061": "破损装置",
    "30034": "聚酸酯块",
    "30033": "聚酸酯组",
    "30032": "聚酸酯",
    "30031": "酯原料",
    "30024": "糖聚块",
    "30023": "糖组",
    "30022": "糖",
    "30021": "代糖",
    "30044": "异铁块",
    "30043": "异铁组",
    "30042": "异铁",
    "30041": "异铁碎片",
    "30054": "酮阵列",
    "30053": "酮凝集组",
    "30052": "酮凝集",
    "30051": "双酮",
    "3114": "碳素组",
    "3113": "碳素",
    "3112": "碳",
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

POWER_SIGN_MAP = {
    "NoAction": "无动作",
    "Shutdown": "关机",
    "ShutdownForce": "强制关机",
    "Hibernate": "休眠",
    "Sleep": "睡眠",
    "KillSelf": "退出程序",
}
"""电源操作类型索引表"""

RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}
"""Windows保留名称列表"""

ILLEGAL_CHARS = set('<>:"/\\|?*')
"""文件名非法字符集合"""

MIRROR_ERROR_INFO = {
    1001: "获取版本信息的URL参数不正确",
    7001: "填入的 CDK 已过期",
    7002: "填入的 CDK 错误",
    7003: "填入的 CDK 今日下载次数已达上限",
    7004: "填入的 CDK 类型和待下载的资源不匹配",
    7005: "填入的 CDK 已被封禁",
    8001: "对应架构和系统下的资源不存在",
    8002: "错误的系统参数",
    8003: "错误的架构参数",
    8004: "错误的更新通道参数",
    1: "未知错误类型",
}
"""MirrorChyan错误代码映射表"""

DEFAULT_DATETIME = datetime.strptime("2000-01-01 00:00:00", "%Y-%m-%d %H:%M:%S")
"""默认日期时间"""
