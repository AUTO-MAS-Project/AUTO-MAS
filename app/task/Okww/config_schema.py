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

半自动模式：
- 字段名 / 类型从 JSON 配置文件值自动推断
- 中文标签从 ok-ww 安装目录的 .po / .mo / .ts 自动加载
- 仅下拉 / 多选的可选项列表需在此手工维护
"""

from __future__ import annotations
from typing import Any
from pathlib import Path
import re
import struct
from xml.etree import ElementTree


# ─── OK-WW 翻译文件自动加载 ─────────────────────────────────────────────────

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
            if msgid and msgstr:
                labels[msgid] = msgstr
    except Exception:
        pass
    return labels


def _parse_mo_file(mo_path: Path) -> dict[str, str]:
    """解析 .mo 编译翻译文件，返回 {msgid: msgstr} 映射。"""
    labels: dict[str, str] = {}
    try:
        data = mo_path.read_bytes()
        if len(data) < 20:
            return labels

        magic, _rev, n_strings, orig_off, trans_off = struct.unpack_from(
            "<IIIII", data, 0
        )

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
            if orig and trans:
                labels[orig] = trans
    except Exception:
        pass
    return labels


def _parse_ts_file(ts_path: Path) -> dict[str, str]:
    """解析 Qt .ts 翻译文件（ok-script 框架级翻译）。"""
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

    搜索优先级：ok.mo > ok.po，同时补充 ok-script 框架的 zh_CN.ts。
    """
    root = Path(root_path)
    labels: dict[str, str] = {}

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
                break

        po_file = i18n_dir / "zh_CN" / "LC_MESSAGES" / "ok.po"
        if po_file.is_file():
            loaded = _parse_po_file(po_file)
            if loaded:
                labels.update(loaded)
                break

    ts_candidates = [
        root / "ok" / "gui" / "i18n" / "zh_CN.ts",
        root / "_internal" / "ok" / "gui" / "i18n" / "zh_CN.ts",
        root / "data" / "apps" / "ok-ww" / "repo" / "ok" / "gui" / "i18n" / "zh_CN.ts",
    ]
    for ts_file in ts_candidates:
        if ts_file.is_file():
            loaded = _parse_ts_file(ts_file)
            if loaded:
                labels.update(loaded)
                break

    return labels


# ─── 通用兜底标签（JSON 中不出现但前端需要） ─────────────────────────────

_FALLBACK_LABELS: dict[str, str] = {
    "Yes": "是",
    "No": "否",
    "Auto": "自动",
    "None": "无",
}


# ─── 手工维护：下拉 / 多选的可选项列表 ───────────────────────────────────
#
# ok-ww 打包后源码不可读，JSON 配置文件只存当前值不存侯选列表，
# 因此下拉 / 多选字段的选项必须在这里声明。
# 布尔、整数、文本字段无需声明——自动从 JSON 值推断类型。

SELECT_OPTIONS: dict[str, dict[str, list[str]]] = {
    # ── 任务配置 ──
    "DailyTask.json": {
        "Which to Farm": [
            "Tacet Suppression", "Forgery Challenge", "Simulation Challenge",
        ],
        "Material Selection": [
            "Resonator EXP", "Weapon EXP", "Shell Credit",
        ],
    },
    "FarmEchoTask.json": {
        "Teleport to Boss": [
            "No", "Weekly Challenge", "Boss Challenge",
        ],
        "Boss": [
            "Other", "Hyvatia", "Fallacy of No Return", "Sentry Construct",
            "Lorelei", "Lioness of Glory", "Nightmare: Hecate",
            "Fenrico", "Nameless Explorer",
        ],
        "Boss Level": ["50", "60", "70", "80"],
        "Echo Pickup Method": ["Yolo", "Run in Circle", "Walk"],
    },
    "NightmareNestTask.json": {
        "Which to Farm": ["Nightmare Purification", "Tacet Discord Nest"],
    },
    "SimulationTask.json": {
        "Material Selection": [
            "Resonator EXP", "Weapon EXP", "Shell Credit",
        ],
    },
    # ── 任务子配置 ──
    "EnhanceEchoTask.json": {
        "有效词条": [
            "暴击伤害", "暴击", "攻击百分比",
            "生命百分比", "防御百分比",
            "攻击", "生命", "防御",
            "共鸣效率", "普攻伤害加成",
            "重击伤害加成", "共鸣解放伤害加成", "共鸣技能伤害加成",
        ],
    },
    "AutoPickTask.json": {
        "Pick Up White List": ["吸收", "Absorb", "拾取", "Pick Up"],
        "Pick Up Black List": ["开始合成", "领取奖励", "Claim", "合成台"],
    },
    # ── 全局配置 ──
    "Basic Options.json": {
        "Use DirectML": ["Auto", "Yes", "No"],
        "Start/Stop": ["None", "F9", "F10", "F11", "F12"],
        "Blur Algorithm": ["Blur", "Inpaint"],
    },
}


def _get_select_options(filename: str, field_name: str) -> list[str] | None:
    """获取指定字段的下拉 / 多选选项列表。"""
    return SELECT_OPTIONS.get(filename, {}).get(field_name)


# ─── 文件注册表 ───────────────────────────────────────────────────────────

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


# ─── JSON 字段自动发现 ────────────────────────────────────────────────────

def _infer_field_type(value: Any) -> str:
    """从 JSON 值推断前端字段类型。"""
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, list):
        return "list"
    return "string"


def _translate(key: str, labels: dict[str, str]) -> str:
    """查找翻译：ok-ww 标签 > 兜底标签 > 原始 key。"""
    if key in labels:
        return labels[key]
    if key in _FALLBACK_LABELS:
        return _FALLBACK_LABELS[key]
    return key


def build_fields_for_config(
    filename: str,
    json_data: dict[str, Any],
    option_labels: dict[str, str],
) -> list[dict[str, Any]]:
    """从 JSON 数据 + 选项映射 + 翻译标签构建前端字段列表。

    逻辑：
    1. 遍历 JSON 中的字段 → 根据值推断类型
    2. 若字段在 SELECT_OPTIONS 中有定义 → 设为 select / list 并附选项
    3. 若字段在翻译中有映射 → 用翻译作为 label
    4. SELECT_OPTIONS 中定义但 JSON 中没有的字段 → 也加入（新字段，值为 None）
    """
    seen: set[str] = set()

    def make_field(name: str, raw_value: Any) -> dict[str, Any]:
        seen.add(name)
        opts = _get_select_options(filename, name)

        if opts is not None:
            # 下拉或多选
            field_type = "list" if isinstance(raw_value, list) else "select"
            return {
                "name": name,
                "type": field_type,
                "label": _translate(name, option_labels),
                "description": "",
                "value": raw_value,
                "options": opts,
                "min": None,
                "max": None,
                "step": None,
            }

        # 普通字段：从 JSON 值推断类型
        field_type = _infer_field_type(raw_value)
        return {
            "name": name,
            "type": field_type,
            "label": _translate(name, option_labels),
            "description": "",
            "value": raw_value,
            "options": None,
            "min": None,
            "max": None,
            "step": None,
        }

    fields = [make_field(k, v) for k, v in json_data.items()]

    # 补充：SELECT_OPTIONS 中有定义但 JSON 中没有的字段（ok-ww 新增配置项）
    known_options = SELECT_OPTIONS.get(filename, {})
    for name in known_options:
        if name not in seen:
            fields.append(make_field(name, None))

    return fields


# ─── API 辅助函数 ─────────────────────────────────────────────────────────

def get_all_config_info() -> list[dict[str, Any]]:
    """获取所有配置文件的元信息（用于前端列表展示）。"""
    result = []
    for group_name, filenames in CONFIG_GROUPS.items():
        for filename in filenames:
            # 字段数量 = JSON 中已有的 + SELECT_OPTIONS 中新增的
            field_count = len(SELECT_OPTIONS.get(filename, {}))
            result.append({
                "filename": filename,
                "displayName": CONFIG_DISPLAY_NAMES.get(filename, filename),
                "group": group_name,
                "taskIndex": TASK_INDEX_MAP.get(filename),
                "fieldCount": max(field_count, 1),  # 至少 1，避免显示 0
            })
    return result
