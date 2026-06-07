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
from pathlib import Path
import re
import struct
from xml.etree import ElementTree

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


# ─── OK-WW 翻译文件自动加载 ─────────────────────────────────────────────────

# .po 文件解析正则
_PO_ENTRY_RE = re.compile(
    r'^msgid\s+"((?:[^"\\]|\\.)*)"\s*\nmsgstr\s+"((?:[^"\\]|\\.)*)"',
    re.MULTILINE,
)


def _parse_po_file(po_path: Path) -> dict[str, str]:
    """解析 .po 翻译文件，返回 {msgid: msgstr} 映射。"""
    labels: dict[str, str] = {}
    try:
        text = po_path.read_text(encoding="utf-8")
        for match in _PO_ENTRY_RE.finditer(text):
            msgid = match.group(1)
            msgstr = match.group(2)
            if msgid and msgstr:  # 跳过空 msgid（PO 头部元数据）
                labels[msgid] = msgstr
    except Exception:
        pass
    return labels


def _parse_mo_file(mo_path: Path) -> dict[str, str]:
    """解析 .mo 编译翻译文件，返回 {msgid: msgstr} 映射。

    .mo 二进制格式（小端）：
        magic: u32 = 0x950412de
        revision: u32 (通常为 0)
        n_strings: u32
        orig_table_offset: u32
        trans_table_offset: u32
        ...
    每个字符串表条目：length: u32, offset: u32
    """
    labels: dict[str, str] = {}
    try:
        data = mo_path.read_bytes()
        if len(data) < 20:
            return labels

        magic, _rev, n_strings, orig_off, trans_off = struct.unpack_from(
            "<IIIII", data, 0
        )

        # 验证魔数（同时支持大小端）
        if magic not in (0x950412DE, 0xDE120495):
            return labels

        le = magic == 0x950412DE
        fmt = "<II" if le else ">II"

        def read_strings(table_offset: int) -> list[str]:
            strings: list[str] = []
            for i in range(n_strings):
                length, offset = struct.unpack_from(
                    fmt, data, table_offset + i * 8
                )
                if length > 0:
                    s = data[offset : offset + length]
                    strings.append(s.decode("utf-8", errors="replace"))
                else:
                    strings.append("")
            return strings

        orig_strings = read_strings(orig_off)
        trans_strings = read_strings(trans_off)

        for orig, trans in zip(orig_strings, trans_strings):
            if orig and trans:  # 跳过空 msgid（头部）
                labels[orig] = trans
    except Exception:
        pass
    return labels


def _parse_ts_file(ts_path: Path) -> dict[str, str]:
    """解析 Qt .ts 翻译文件（ok-script 框架级翻译），返回 {source: translation} 映射。"""
    labels: dict[str, str] = {}
    try:
        root = ElementTree.parse(str(ts_path)).getroot()
        for message in root.iter("message"):
            source = message.find("source")
            translation = message.find("translation")
            if (
                source is not None
                and translation is not None
                and source.text
                and translation.text
                and translation.attrib.get("type") != "unfinished"
            ):
                labels[source.text] = translation.text
    except Exception:
        pass
    return labels


def load_okww_option_labels(root_path: Path | str) -> dict[str, str]:
    """从 ok-ww 安装目录自动加载选项的英文→中文翻译映射。

    搜索优先级：ok.mo（编译） > ok.po（源文件），
    同时加载 ok-script 框架的 zh_CN.ts 翻译。
    返回与 OPTION_LABELS 相同格式的 {English: 中文} 字典，
    调用方应合并到硬编码 OPTION_LABELS 之上。
    """
    root = Path(root_path)
    labels: dict[str, str] = {}

    # 可能的 i18n 目录位置（覆盖不同打包方式）
    i18n_candidates = [
        root / "i18n",
        root / "_internal" / "i18n",
        root / "data" / "apps" / "ok-ww" / "repo" / "i18n",
        root / "data" / "apps" / "ok-ww" / "working" / "i18n",
    ]

    for i18n_dir in i18n_candidates:
        mo_file = i18n_dir / "zh_CN" / "LC_MESSAGES" / "ok.mo"
        if mo_file.is_file():
            loaded = _parse_mo_file(mo_file)
            if loaded:
                labels.update(loaded)
                break  # .mo 优先，找到即停止

        po_file = i18n_dir / "zh_CN" / "LC_MESSAGES" / "ok.po"
        if po_file.is_file():
            loaded = _parse_po_file(po_file)
            if loaded:
                labels.update(loaded)
                break  # .po 次选，找到即停止

    # 额外加载 ok-script 框架翻译（zh_CN.ts），覆盖 Basic Options 等框架级标签
    ts_candidates = [
        root / "ok" / "gui" / "i18n" / "zh_CN.ts",
        root / "_internal" / "ok" / "gui" / "i18n" / "zh_CN.ts",
        root / "data" / "apps" / "ok-ww" / "repo" / "ok" / "gui" / "i18n" / "zh_CN.ts",
    ]
    for ts_file in ts_candidates:
        if ts_file.is_file():
            loaded = _parse_ts_file(ts_file)
            if loaded:
                labels.update(loaded)  # .ts 补充框架标签（不覆盖 .po 已有）
                break

    return labels


# 选项值的中文翻译映射（key=英文原值, value=中文显示）
# 运行时优先使用 load_okww_option_labels() 从 ok-ww 目录加载的翻译，
# 此处保留为兜底默认值。
OPTION_LABELS: dict[str, str] = {
    # 通用
    "Yes": "是",
    "No": "否",
    "Auto": "自动",
    # DailyTask - Which to Farm
    "Forgery Challenge": "凝素领域",
    "Tacet Suppression": "无音区",
    "Simulation Challenge": "模拟领域",
    # DailyTask / SimulationTask - Material Selection
    "Resonator EXP": "共鸣者经验",
    "Weapon EXP": "武器经验",
    "Shell Credit": "贝币",
    # FarmEchoTask - Teleport to Boss
    "Weekly Challenge": "战歌重奏",
    "Boss Challenge": "讨伐强敌",
    # FarmEchoTask - Echo Pickup Method
    "Yolo": "Yolo模型",
    "Run in Circle": "转圈奔跑",
    "Walk": "后退再前进",
    # FarmEchoTask - Boss
    "Other": "其它",
    "Hyvatia": "海维夏",
    "Fallacy of No Return": "无归的谬误",
    "Sentry Construct": "异构武装",
    "Lorelei": "罗蕾莱",
    "Lioness of Glory": "荣耀狮像",
    "Nightmare: Hecate": "梦魇·赫卡忒",
    "Fenrico": "芬莱克",
    "Nameless Explorer": "无铭探索者",
    # NightmareNestTask - Which to Farm
    "Nightmare Purification": "梦魇祓除",
    "Tacet Discord Nest": "残像聚落",
    # Basic Options - Blur Algorithm
    "Blur": "模糊",
    "Inpaint": "内容填充",
    # Start/Stop
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
            "Simulation Challenge",
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
            "Resonator EXP",
            "Weapon EXP",
            "Shell Credit",
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
        label="传送至Boss",
        description="在F2菜单中传送至Boss",
        options=["No", "Weekly Challenge", "Boss Challenge"],
    ),
    "Boss Level": _field(
        "select",
        label="Boss等级",
        description="选择会掉落声骸的最低等级",
        options=["50", "60", "70", "80"],
    ),
    "Boss": _field(
        "select",
        label="Boss",
        description="选择Boss配置（已包含战斗等待时间）",
        options=[
            "Other",
            "Hyvatia",
            "Fallacy of No Return",
            "Sentry Construct",
            "Lorelei",
            "Lioness of Glory",
            "Nightmare: Hecate",
            "Fenrico",
            "Nameless Explorer",
        ],
    ),
    "Repeat Farm Count": _field(
        "int",
        label="刷多少次",
        description="重复刷取的次数上限",
        min=1,
        max=99999,
    ),
    "Combat Wait Time": _field(
        "int",
        label="战斗开始前等待时间（秒）",
        description="若设定大于0则覆盖Boss配置",
        min=0,
        max=60,
    ),
    "Echo Pickup Method": _field(
        "select",
        label="搜索声骸方法",
        description="选择搜索声骸的方法",
        options=["Yolo", "Run in Circle", "Walk"],
    ),
    "Use Liberation": _field(
        "bool",
        label="使用共鸣解放",
        description="高练度情况下，不使用共鸣解放以节约时间",
    ),
    "Switch to Healer after Combat": _field(
        "bool",
        label="战斗结束后切换到治疗角色",
        description="提高角色生存率",
    ),
    "Which Weekly Boss to Teleport": _field(
        "int",
        label="传送到第几个周常Boss",
        description="例如德尼亚，从上到下，从1开始",
        min=1,
        max=9,
    ),
    "Which Boss Challenge to Teleport": _field(
        "int",
        label="传送到第几个Boss挑战",
        description="例如无铭探索者，从上到下，从1开始",
        min=1,
        max=20,
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
        description="在周常门口或者任务内开始，卡墙时会提示人工接管",
    ),
    "Stop When Treasure Found": _field(
        "bool",
        label="出现声骸奖励时停止运行",
        description="如果选择否，将在体力足够时领取声骸奖励",
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
            "Resonator EXP",
            "Weapon EXP",
            "Shell Credit",
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
            "生命百分比",
            "防御百分比",
            "攻击",
            "生命",
            "防御",
            "共鸣效率",
            "普攻伤害加成",
            "重击伤害加成",
            "共鸣解放伤害加成",
            "共鸣技能伤害加成",
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
        description="在大世界、深渊、无音区等开启自动战斗",
    ),
    "Auto Target": _field(
        "bool",
        label="自动选取敌人",
        description="关闭时仅在手动鼠标中键选取敌人后才会自动战斗",
    ),
    "Use Liberation": _field(
        "bool",
        label="使用共鸣解放",
        description="在大世界中，不使用共鸣解放以节约时间",
    ),
    "Check Levitator": _field(
        "bool",
        label="检查探索工具是否为控物",
        description="在秘境中自动战斗时切换控物以判断角色是否处于空中",
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
        label="使用文字识别(中英文客户端适用)",
        description="高配置CPU请打开，增加拾取声骸准确度",
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
    "DailyTask.json": "日常一条龙",
    "MultiAccountDailyTask.json": "多账号一条龙",
    "FarmEchoTask.json": "刷4C(大世界/副本)",
    "AutoRogueTask.json": "半自动肉鸽(周常)",
    "ForgeryTask.json": "凝素领域",
    "NightmareNestTask.json": "梦魇巢穴",
    "SimulationTask.json": "模拟领域",
    "TacetTask.json": "无音区",
    "EnhanceEchoTask.json": "批量强化声骸",
    "AutoCombatTask.json": "自动战斗",
    "AutoPickTask.json": "自动拾取",
    "AutoDialogTask.json": "任务跳过对话",
    "ChangeEchoTask.json": "批量修改声骸主属性",
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
