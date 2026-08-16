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
OK-NTE 配置文件 Schema 定义

半自动模式：
- 字段名 / 类型从 JSON 配置文件值自动推断
- 中文标签从 OK-NTE 安装目录的 .po / .mo / .ts 自动加载
- 仅下拉 / 多选的可选项列表需在此手工维护
"""

from __future__ import annotations
from typing import Any
from pathlib import Path
import re
import struct
from xml.etree import ElementTree


# ─── OK-NTE 翻译文件自动加载 ─────────────────────────────────────────────────

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


def load_oknte_option_labels(root_path: Path | str) -> dict[str, str]:
    """从 OK-NTE 安装目录自动加载选项的英文→中文翻译映射。

    搜索优先级：ok.mo > ok.po，同时补充 ok-script 框架的 zh_CN.ts。
    """
    root = Path(root_path)
    labels: dict[str, str] = {}

    i18n_candidates = [
        root / "i18n",
        root / "_internal" / "i18n",
        root / "data" / "apps" / "ok-nte" / "repo" / "i18n",
        root / "data" / "apps" / "ok-nte" / "working" / "i18n",
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
        root / "data" / "apps" / "ok-nte" / "repo" / "ok" / "gui" / "i18n" / "zh_CN.ts",
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
# OK-NTE 打包后源码不可读，JSON 配置文件只存当前值不存侯选列表，
# 因此下拉 / 多选字段的选项必须在这里声明。
# 布尔、整数、文本字段无需声明——自动从 JSON 值推断类型。

SELECT_OPTIONS: dict[str, dict[str, list[str]]] = {
    # ── 任务配置 ──
    "DailyTask.json": {
        "任务类型": ["经验与甲硬币", "异能升级材料", "弧盘突破材料", "空幕"],
        "具体奖励目标": ["角色经验", "弧盘经验", "甲硬币"],
        "一咖舍任务": ["不执行", "领取/补货一咖舍", "运行一咖舍自动化"],
    },
    "AnomalyTask.json": {
        "任务类型": ["经验与甲硬币", "异能升级材料", "弧盘突破材料", "空幕"],
        "具体奖励目标": ["角色经验", "弧盘经验", "甲硬币"],
    },
    "CoffeeTask.json": {
        "补货时长": ["auto", "2小时", "4小时", "8小时", "24小时"],
        "商品位数量": ["auto", "1", "2", "3", "4", "5"],
        "价格表": ["auto", "disabled"],
    },
    "FishingTask.json": {
        "控条模式": ["长按", "点按"],
    },
    "AutoHeistTask.json": {
        "路径": [
            "路径1(路线参考自B站UP: 早柚大魔王丶)",
            "路径2(在路径1基础上优化了大厅到办公层的路线)",
        ],
        "战斗角色": ["1", "2", "3", "4"],
        "跑图角色": ["1", "2", "3", "4"],
        "避战角色": ["1", "2", "3", "4"],
        "避战方法": ["长按shift", "长按攻击"],
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
        "LauncherTask.json",
        "DailyTask.json",
        "CoffeeTask.json",
        "FishingTask.json",
        "AnomalyTask.json",
        "RhythmTask.json",
        "OwnerSelectionTask.json",
        "AutoHeistTask.json",
        "DarkTask.json",
        "DiagnosisTask.json",
    ],
    "触发配置": [
        "AutoCombatTask.json",
        "AutoLoginTask.json",
        "FastTravelTask.json",
        "HeistTask.json",
        "SkipDialogTask.json",
        "SoundTriggerTask.json",
    ],
    "全局配置": [
        "Game Hotkey Config.json",
        "Monthly Card Config.json",
        "Sound Trigger Config.json",
        "Basic Options.json",
    ],
}

CONFIG_DISPLAY_NAMES: dict[str, str] = {
    "LauncherTask.json": "启动游戏",
    "DailyTask.json": "日常任务",
    "CoffeeTask.json": "一咖舍自动化",
    "FishingTask.json": "自动钓鱼",
    "AnomalyTask.json": "异象界域",
    "RhythmTask.json": "自动音游",
    "OwnerSelectionTask.json": "业主选拔",
    "AutoHeistTask.json": "自动粉爪大劫案",
    "DarkTask.json": "暗域任务",
    "DiagnosisTask.json": "诊断",
    "AutoCombatTask.json": "自动战斗触发",
    "AutoLoginTask.json": "自动登录触发",
    "FastTravelTask.json": "快速传送触发",
    "HeistTask.json": "粉爪大劫案触发",
    "SkipDialogTask.json": "跳过对话触发",
    "SoundTriggerTask.json": "声音触发",
    "Game Hotkey Config.json": "游戏快捷键",
    "Monthly Card Config.json": "小月卡设置",
    "Sound Trigger Config.json": "声音触发设置",
    "Basic Options.json": "基本设置",
}

TASK_INDEX_MAP: dict[str, int] = {
    "LauncherTask.json": 1,
    "DailyTask.json": 2,
    "CoffeeTask.json": 3,
    "FishingTask.json": 4,
    "AnomalyTask.json": 5,
    "RhythmTask.json": 6,
    "OwnerSelectionTask.json": 7,
    "AutoHeistTask.json": 8,
    "DarkTask.json": 9,
    "DiagnosisTask.json": 11,
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
    """查找翻译：OK-NTE 标签 > 兜底标签 > 原始 key。"""
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

    def _is_internal(name: str) -> bool:
        """OK-NTE 框架内部字段（_enabled 等），不暴露给 MAS 用户编辑。"""
        return name.startswith("_")

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

    fields = [
        make_field(k, v)
        for k, v in json_data.items()
        if not _is_internal(k)  # 屏蔽 _enabled 等 OK-NTE 框架内部字段
    ]

    # 补充：SELECT_OPTIONS 中有定义但 JSON 中没有的字段（OK-NTE 新增配置项）
    known_options = SELECT_OPTIONS.get(filename, {})
    for name in known_options:
        if name not in seen and not _is_internal(name):
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
