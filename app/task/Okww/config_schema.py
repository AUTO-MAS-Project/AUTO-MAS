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

"""
OK-WW 配置文件 Schema 定义

定义 configs/ 目录下各 JSON 配置文件的字段类型、选项和默认值，
用于前端表单化渲染。
"""

from __future__ import annotations
from typing import Any, Literal

# 字段类型枚举
# bool    — 开关 (a-switch)
# int     — 整数 (a-input-number)
# float   — 浮点数 (a-input-number, step=0.1)
# string  — 文本 (a-input)
# select  — 下拉选择 (a-select)
# list    — 列表 (a-select mode="multiple")
# hotkey  — 快捷键 (a-input，展示用)

FieldSchema = dict[str, Any]


def _field(
    type: str,
    label: str = "",
    description: str = "",
    **kwargs: Any,
) -> FieldSchema:
    """构建字段 schema"""
    schema: FieldSchema = {"type": type, "label": label, "description": description}
    schema.update(kwargs)
    return schema


# 选项值的中文翻译映射（key=英文原值, value=中文显示）
OPTION_LABELS: dict[str, str] = {
    # 通用
    "Yes": "是",
    "No": "否",
    "Auto": "自动",
    # DailyTask - Which to Farm
    "Forgery Challenge": "凝素领域",
    "Tacet Suppression": "无音区",
    "Simulation": "模拟领域",
    # DailyTask / SimulationTask - Material Selection
    "Weapon EXP": "武器经验",
    "Shell Credit": "贝币",
    "Character EXP": "角色经验",
    # FarmEchoTask - Echo Pickup Method
    "Yolo": "自动拾取",
    "Click": "点击拾取",
    # FarmEchoTask - Boss
    "Other": "其他",
    # NightmareNestTask - Which to Farm
    "Nightmare Purification": "梦魇祓除",
    "Tacet Discord Nest": "残像聚落",
    # Basic Options - Blur Algorithm
    "Blur": "模糊",
    "Inpaint": "内容填充",
    # Use DirectML
    "None": "无",
}


# ─── 任务配置 Schema ──────────────────────────────────────────────────────────

DAILY_TASK_SCHEMA: dict[str, FieldSchema] = {
    "Which to Farm": _field(
        "select",
        label="刷取目标",
        description="选择要刷取的副本类型",
        options=[
            "Forgery Challenge",
            "Tacet Suppression",
            "Simulation",
        ],
    ),
    "Which Tacet Suppression to Farm": _field(
        "int",
        label="无音区序号",
        description="选择要刷取的无音区（从 1 开始）",
        min=1,
        max=20,
    ),
    "Which Forgery Challenge to Farm": _field(
        "int",
        label="凝素领域序号",
        description="选择要刷取的凝素领域（从 1 开始）",
        min=1,
        max=20,
    ),
    "Material Selection": _field(
        "select",
        label="材料选择",
        description="选择要刷取的材料",
        options=[
            "Weapon EXP",
            "Shell Credit",
            "Character EXP",
        ],
    ),
    "Auto Farm all Nightmare Nest": _field(
        "bool",
        label="自动刷取所有梦魇巢穴",
        description="开启后将自动刷取所有梦魇巢穴",
    ),
    "Farm Nightmare Nest for Daily Echo": _field(
        "bool",
        label="梦魇巢穴刷取声骸",
        description="开启后在梦魇巢穴中刷取声骸",
    ),
    "Exit After Task": _field(
        "bool",
        label="任务完成后退出",
        description="任务完成后是否退出游戏",
    ),
}

MULTI_ACCOUNT_DAILY_TASK_SCHEMA: dict[str, FieldSchema] = {
    "Exit After Task": _field(
        "bool",
        label="任务完成后退出",
        description="任务完成后是否退出游戏",
    ),
}

FARM_ECHO_TASK_SCHEMA: dict[str, FieldSchema] = {
    "Teleport to Boss": _field(
        "select",
        label="传送到Boss",
        description="选择是否传送到Boss",
        options=["No", "Yes"],
    ),
    "Boss Level": _field(
        "select",
        label="Boss等级",
        description="选择Boss等级",
        options=["60", "70", "80", "90"],
    ),
    "Boss": _field(
        "string",
        label="Boss名称",
        description="指定要刷的Boss名称，填 Other 使用默认",
    ),
    "Repeat Farm Count": _field(
        "int",
        label="重复刷取次数",
        description="重复刷取的次数上限",
        min=1,
        max=99999,
    ),
    "Combat Wait Time": _field(
        "int",
        label="战斗等待时间（秒）",
        description="战斗结束后等待的时间",
        min=0,
        max=60,
    ),
    "Echo Pickup Method": _field(
        "select",
        label="声骸拾取方式",
        description="选择声骸拾取方式",
        options=["Yolo", "Click"],
    ),
    "Use Liberation": _field(
        "bool",
        label="使用解放技能",
        description="是否在战斗中使用解放技能",
    ),
    "Switch to Healer after Combat": _field(
        "bool",
        label="战斗后切换治疗角色",
        description="战斗结束后是否切换到治疗角色",
    ),
    "Which Weekly Boss to Teleport": _field(
        "int",
        label="周本Boss序号",
        description="选择要传送的周本Boss（从 1 开始）",
        min=1,
        max=10,
    ),
    "Which Boss Challenge to Teleport": _field(
        "int",
        label="Boss挑战序号",
        description="选择要传送的Boss挑战（从 1 开始）",
        min=1,
        max=10,
    ),
    "Exit After Task": _field(
        "bool",
        label="任务完成后退出",
        description="任务完成后是否退出游戏",
    ),
}

AUTO_ROGUE_TASK_SCHEMA: dict[str, FieldSchema] = {
    "_enabled": _field(
        "bool",
        label="启用",
        description="是否启用半自动肉鸽任务",
    ),
    "Stop When Treasure Found": _field(
        "bool",
        label="发现宝藏时停止",
        description="发现宝藏后是否停止任务",
    ),
}

FORGERY_TASK_SCHEMA: dict[str, FieldSchema] = {
    "Which Forgery Challenge to Farm": _field(
        "int",
        label="凝素领域序号",
        description="选择要刷取的凝素领域（从 1 开始）",
        min=1,
        max=20,
    ),
}

NIGHTMARE_NEST_TASK_SCHEMA: dict[str, FieldSchema] = {
    "_enabled": _field(
        "bool",
        label="启用",
        description="是否启用梦魇巢穴任务",
    ),
    "Which to Farm": _field(
        "list",
        label="刷取目标",
        description="选择要刷取的梦魇巢穴类型",
        options=[
            "Nightmare Purification",
            "Tacet Discord Nest",
        ],
    ),
}

SIMULATION_TASK_SCHEMA: dict[str, FieldSchema] = {
    "Material Selection": _field(
        "select",
        label="材料选择",
        description="选择要刷取的材料",
        options=[
            "Shell Credit",
            "Character EXP",
            "Weapon EXP",
        ],
    ),
}

TACET_TASK_SCHEMA: dict[str, FieldSchema] = {
    "Which Tacet Suppression to Farm": _field(
        "int",
        label="无音区序号",
        description="选择要刷取的无音区（从 1 开始）",
        min=1,
        max=20,
    ),
}

# ─── 任务子配置 Schema ──────────────────────────────────────────────────────

ENHANCE_ECHO_TASK_SCHEMA: dict[str, FieldSchema] = {
    "必须有双爆": _field(
        "bool",
        label="必须有双爆",
        description="声骸必须同时有暴击率和暴击伤害",
    ),
    "双爆出现之前必须全有效词条": _field(
        "bool",
        label="双爆前全有效词条",
        description="在双爆出现之前必须全部为有效词条",
    ),
    "双爆总计>=": _field(
        "float",
        label="双爆总计≥",
        description="双爆总计最低要求",
        min=0,
        max=100,
        step=0.1,
    ),
    "首条双爆>=": _field(
        "float",
        label="首条双爆≥",
        description="第一条双爆的最低要求",
        min=0,
        max=100,
        step=0.1,
    ),
    "有效词条>=": _field(
        "int",
        label="有效词条≥",
        description="有效词条的最低数量",
        min=0,
        max=10,
    ),
    "第一条必须为有效词条": _field(
        "bool",
        label="首条必须有效",
        description="第一条词条必须为有效词条",
    ),
    "有效词条": _field(
        "list",
        label="有效词条列表",
        description="选择视为有效的词条",
        options=[
            "暴击伤害",
            "暴击",
            "攻击百分比",
            "共鸣效率",
            "共鸣解放伤害加成",
            "普攻伤害加成",
            "重击伤害加成",
            "共鸣技能伤害加成",
            "攻击",
            "生命百分比",
            "防御百分比",
        ],
    ),
    "Pause after Success": _field(
        "bool",
        label="成功后暂停",
        description="声骸强化成功后暂停任务",
    ),
}

AUTO_COMBAT_TASK_SCHEMA: dict[str, FieldSchema] = {
    "_enabled": _field(
        "bool",
        label="启用",
        description="是否启用自动战斗",
    ),
    "Auto Target": _field(
        "bool",
        label="自动锁定目标",
        description="是否自动锁定敌人",
    ),
    "Use Liberation": _field(
        "bool",
        label="使用解放技能",
        description="是否使用解放技能",
    ),
    "Check Levitator": _field(
        "bool",
        label="检测悬浮道具",
        description="是否检测悬浮道具",
    ),
}

AUTO_PICK_TASK_SCHEMA: dict[str, FieldSchema] = {
    "_enabled": _field(
        "bool",
        label="启用",
        description="是否启用自动拾取",
    ),
    "Pick Up White List": _field(
        "list",
        label="拾取白名单",
        description="自动拾取的物品关键词",
        options=[
            "吸收",
            "Absorb",
            "拾取",
            "Pick Up",
        ],
    ),
    "Pick Up Black List": _field(
        "list",
        label="拾取黑名单",
        description="不自动拾取的物品关键词",
        options=[
            "开始合成",
            "领取奖励",
            "Claim",
            "合成台",
        ],
    ),
}

AUTO_DIALOG_TASK_SCHEMA: dict[str, FieldSchema] = {
    "_enabled": _field(
        "bool",
        label="启用",
        description="是否启用自动对话",
    ),
}

CHANGE_ECHO_TASK_SCHEMA: dict[str, FieldSchema] = {
    "Use OCR": _field(
        "bool",
        label="使用OCR",
        description="是否使用OCR识别",
    ),
}

# ─── 全局配置 Schema ────────────────────────────────────────────────────────

GAME_HOTKEY_SCHEMA: dict[str, FieldSchema] = {
    "Echo Key": _field(
        "hotkey",
        label="声骸按键",
        description="声骸技能快捷键（默认 Q）",
    ),
    "Liberation Key": _field(
        "hotkey",
        label="共鸣解放快捷键",
        description="共鸣解放快捷键（默认 R）",
    ),
    "Resonance Key": _field(
        "hotkey",
        label="共鸣技能快捷键",
        description="共鸣技能快捷键（默认 E）",
    ),
    "Tool Key": _field(
        "hotkey",
        label="探索工具快捷键",
        description="探索工具快捷键（默认 T）",
    ),
    "Jump Key": _field(
        "hotkey",
        label="跳跃键",
        description="跳跃键（默认 Space）",
    ),
    "Dodge Key": _field(
        "hotkey",
        label="闪避键",
        description="闪避键（默认 LShift）",
    ),
    "Wheel Key": _field(
        "hotkey",
        label="轮盘键",
        description="轮盘键（默认 Tab）",
    ),
}

CHARACTER_CONFIG_SCHEMA: dict[str, FieldSchema] = {
    "Iuno C6": _field(
        "bool",
        label="尤诺6链",
        description="是否启用尤诺6链配置",
    ),
    "Chisa DPS": _field(
        "bool",
        label="千咲主C",
        description="是否启用千咲主C配置",
    ),
    "Verina C2": _field(
        "bool",
        label="维里奈2链",
        description="是否启用维里奈2链配置",
    ),
}

MONTHLY_CARD_CONFIG_SCHEMA: dict[str, FieldSchema] = {
    "Check Monthly Card": _field(
        "bool",
        label="是否检查月卡",
        description="设置避免小月卡弹窗打断任务",
    ),
    "Monthly Card Time": _field(
        "int",
        label="月卡时间",
        description="几点会弹出月卡提示，本地计算机时间（1-24）",
        min=1,
        max=24,
    ),
}

BASIC_OPTIONS_SCHEMA: dict[str, FieldSchema] = {
    "Auto Start Game When App Starts": _field(
        "bool",
        label="APP启动后自动启动游戏",
        description="程序启动时自动启动游戏",
    ),
    "Minimize Window to System Tray when Closing": _field(
        "bool",
        label="点击关闭按钮时最小化到系统托盘",
        description="关闭窗口时是否最小化到系统托盘",
    ),
    "Mute Game while in Background": _field(
        "bool",
        label="游戏后台时静音",
        description="游戏在后台时是否静音",
    ),
    "Auto Resize Game Window": _field(
        "bool",
        label="自动调整游戏分辨率",
        description="是否自动调整游戏窗口分辨率",
    ),
    "Exit App when Game Exits": _field(
        "bool",
        label="游戏退出时，自动退出应用",
        description="游戏退出后是否自动关闭应用",
    ),
    "Use DirectML": _field(
        "select",
        label="使用DirectML",
        description="使用 GPU 加速改善性能",
        options=["Auto", "Yes", "No"],
    ),
    "Trigger Interval": _field(
        "int",
        label="触发器间隔",
        description="增加触发任务之间的延迟以降低 CPU/GPU 消耗（毫秒）",
        min=1,
        max=60,
    ),
    "Start/Stop": _field(
        "select",
        label="开始/停止",
        description="开始或停止任务的快捷键",
        options=["None", "F9", "F10", "F11", "F12"],
    ),
    "Kill Launcher after Start": _field(
        "bool",
        label="启动后关闭启动器",
        description="游戏启动后是否关闭启动器",
    ),
    "Launch with DX11": _field(
        "bool",
        label="使用DX11启动",
        description="是否使用 DirectX 11 启动游戏",
    ),
    "Enable Blur": _field(
        "bool",
        label="启用模糊遮挡",
        description="模糊游戏 UID 等固定内容以延长 OLED 屏幕寿命",
    ),
    "Blur Algorithm": _field(
        "select",
        label="遮挡算法",
        description="用于遮挡配置区域的处理方式",
        options=["Blur", "Inpaint"],
    ),
    "Blur Interval": _field(
        "int",
        label="遮挡检查间隔",
        description="处理后遮挡层的更新间隔（秒）",
        min=0,
        max=10,
    ),
}

# ─── 配置文件注册表 ─────────────────────────────────────────────────────────

# 分组定义：前端按分组展示
CONFIG_GROUPS = {
    "任务配置": [
        "DailyTask.json",
        "MultiAccountDailyTask.json",
        "FarmEchoTask.json",
        "AutoRogueTask.json",
        "ForgeryTask.json",
        "NightmareNestTask.json",
        "SimulationTask.json",
        "TacetTask.json",
    ],
    "任务子配置": [
        "EnhanceEchoTask.json",
        "AutoCombatTask.json",
        "AutoPickTask.json",
        "AutoDialogTask.json",
        "ChangeEchoTask.json",
    ],
    "全局配置": [
        "Game Hotkey.json",
        "Character Config.json",
        "Monthly Card Config.json",
        "Basic Options.json",
    ],
}

# 文件名 -> 显示名
CONFIG_DISPLAY_NAMES: dict[str, str] = {
    "DailyTask.json": "日常任务",
    "MultiAccountDailyTask.json": "多账号日常",
    "FarmEchoTask.json": "刷声骸",
    "AutoRogueTask.json": "半自动肉鸽",
    "ForgeryTask.json": "凝素领域",
    "NightmareNestTask.json": "梦魇巢穴",
    "SimulationTask.json": "模拟领域",
    "TacetTask.json": "无音区",
    "EnhanceEchoTask.json": "声骸强化",
    "AutoCombatTask.json": "自动战斗",
    "AutoPickTask.json": "自动拾取",
    "AutoDialogTask.json": "自动对话",
    "ChangeEchoTask.json": "切换声骸",
    "Game Hotkey.json": "游戏快捷键",
    "Character Config.json": "角色设置",
    "Monthly Card Config.json": "小月卡设置",
    "Basic Options.json": "基本设置",
}

# 文件名 -> 任务序号（用于与 TaskIndex 关联）
TASK_INDEX_MAP: dict[str, int] = {
    "DailyTask.json": 1,
    "MultiAccountDailyTask.json": 2,
    "FarmEchoTask.json": 3,
    "AutoRogueTask.json": 4,
    "ForgeryTask.json": 5,
    "NightmareNestTask.json": 6,
    "SimulationTask.json": 7,
    "TacetTask.json": 8,
}

# 文件名 -> Schema
CONFIG_SCHEMA_MAP: dict[str, dict[str, FieldSchema]] = {
    "DailyTask.json": DAILY_TASK_SCHEMA,
    "MultiAccountDailyTask.json": MULTI_ACCOUNT_DAILY_TASK_SCHEMA,
    "FarmEchoTask.json": FARM_ECHO_TASK_SCHEMA,
    "AutoRogueTask.json": AUTO_ROGUE_TASK_SCHEMA,
    "ForgeryTask.json": FORGERY_TASK_SCHEMA,
    "NightmareNestTask.json": NIGHTMARE_NEST_TASK_SCHEMA,
    "SimulationTask.json": SIMULATION_TASK_SCHEMA,
    "TacetTask.json": TACET_TASK_SCHEMA,
    "EnhanceEchoTask.json": ENHANCE_ECHO_TASK_SCHEMA,
    "AutoCombatTask.json": AUTO_COMBAT_TASK_SCHEMA,
    "AutoPickTask.json": AUTO_PICK_TASK_SCHEMA,
    "AutoDialogTask.json": AUTO_DIALOG_TASK_SCHEMA,
    "ChangeEchoTask.json": CHANGE_ECHO_TASK_SCHEMA,
    "Game Hotkey.json": GAME_HOTKEY_SCHEMA,
    "Character Config.json": CHARACTER_CONFIG_SCHEMA,
    "Monthly Card Config.json": MONTHLY_CARD_CONFIG_SCHEMA,
    "Basic Options.json": BASIC_OPTIONS_SCHEMA,
}


def get_config_schema(filename: str) -> dict[str, FieldSchema] | None:
    """获取指定配置文件的 schema"""
    return CONFIG_SCHEMA_MAP.get(filename)


def get_all_config_info() -> list[dict[str, Any]]:
    """获取所有配置文件的元信息（用于前端列表展示）"""
    result = []
    for group_name, filenames in CONFIG_GROUPS.items():
        for filename in filenames:
            schema = CONFIG_SCHEMA_MAP.get(filename, {})
            result.append({
                "filename": filename,
                "displayName": CONFIG_DISPLAY_NAMES.get(filename, filename),
                "group": group_name,
                "taskIndex": TASK_INDEX_MAP.get(filename),
                "fieldCount": len(schema),
            })
    return result
