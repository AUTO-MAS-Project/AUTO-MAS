#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""MAA 原生任务模板与任务切换映射。"""

MAA_TASK_TRANSITION_METHOD_BOOK = {
    "NoAction": "8",
    "ExitGame": "9",
    "ExitEmulator": "9",
}
"""MAA任务切换方式映射表"""

MAA_ANNIHILATION_FIGHT_BASE = {
    "$type": "FightTask",
    "Name": "剿灭作战",
    "IsEnable": True,
    "TaskType": "Fight",
    "StagePlan": ["Annihilation"],
    "Series": 0,
    "IsStageManually": False,
    "UseMedicine": False,
    "MedicineCount": 0,
    "EnableTimesLimit": False,
    "TimesLimit": 999,
    "UseCustomAnnihilation": True,
    "AnnihilationStage": "Annihilation",
}
"""MAA剿灭作战托管补丁

**出现在这里的键即 MAS 声明接管，未出现的一律由 MAA 原生配置透传**——
用户在上游界面里设的临期药、源石、博朗台、周计划、指定材料/次数、隐藏项等
高级设置原样生效，MAS 不经手。反过来说：只要 MAS 不消费某个字段，就不得写进
本表，写了既会覆盖用户在原生界面里的选择，又会在上游新增字段时静默失效。
"""

MAA_GREEN_TICKET_STORE_TASK = {
    "$type": "CustomTask",
    "Name": "绿票商店",
    "IsEnable": True,
    "TaskType": "Custom",
    "CustomTaskName": "GreenTicket@Store@Begin",
}
"""MAA绿票商店任务配置：牛杂「绿票商店」的任务链，需 MAA v6.3.0 及以上"""
