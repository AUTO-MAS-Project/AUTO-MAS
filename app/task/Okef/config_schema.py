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

"""OK-EF 配置文件 Schema 定义。

OK-EF 属于 ok-script 线，配置编辑器直接读写 `working/configs` 下的 JSON。
本模块只负责把现有 JSON 转成 MAS 前端可渲染的字段描述，不启动 OK-EF 原生 UI。
"""

from __future__ import annotations

import gettext
import re
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


_PO_ENTRY_RE = re.compile(
    r'^msgid\s+"((?:[^"\\]|\\.)*)"\s*\nmsgstr\s+"((?:[^"\\]|\\.)*)"',
    re.MULTILINE,
)

_SKIP_CONFIG_FILES = {
    "devices.json",
    "main_window.json",
    "template_tab.json",
}

_ACCOUNT_FIELD_NAMES = {"多账户模式", "多账户独立配置", "账号列表"}

_TASK_INDEX_MAP: dict[str, int] = {
    "DailyTask.json": 1,
    "TakeDeliveryTask.json": 2,
    "WarehouseTransferTask.json": 3,
    "DeliveryTask.json": 4,
    "BattleTask.json": 5,
    "DemoDrawTask.json": 6,
    "Test.json": 7,
    "YingTuoTask.json": 8,
    "TestStartGame.json": 9,
    "RealtimeDetectTask.json": 10,
    "DiagnosisTask.json": 11,
}

_DISPLAY_NAMES: dict[str, str] = {
    "DailyTask.json": "日常任务",
    "TakeDeliveryTask.json": "收取派送",
    "WarehouseTransferTask.json": "仓库转运",
    "DeliveryTask.json": "派送任务",
    "BattleTask.json": "战斗任务",
    "DemoDrawTask.json": "抽卡演示",
    "Test.json": "测试任务",
    "YingTuoTask.json": "莺鸵任务",
    "TestStartGame.json": "启动游戏测试",
    "RealtimeDetectTask.json": "实时识别",
    "DiagnosisTask.json": "诊断任务",
    "AutoCombatTask.json": "自动战斗",
    "AutoInteractionTask.json": "自动交互",
    "AutoLoginTask.json": "自动登录",
    "AutoPickTask.json": "自动拾取",
    "ItemNavigatorTask.json": "物品导航",
    "Basic Options.json": "基础选项",
    "Battle Config.json": "战斗配置",
    "Game Hotkey Config.json": "游戏热键",
    "Ensure Main Once Action Sleep.json": "主界面等待",
}

_FALLBACK_LABELS: dict[str, str] = {
    "Yes": "是",
    "No": "否",
    "Auto": "自动",
    "None": "无",
}

_STAGE_OPTIONS = [
    "干员经验",
    "干员进阶",
    "钱币收集",
    "技能提升",
    "武器经验",
    "武器进阶",
    "罗丹",
    "三位一体",
    "白垩界卫",
    "阮一",
    "聂菲斯",
    "D96钢",
    "超距辉映管",
    "快子遴捡晶格",
    "象限拟合液",
    "三相纳米片",
    "枢纽区",
    "源石研究园",
    "试验园区",
    "矿脉源区",
    "供能高地",
    "武陵城",
    "清波寨",
    "首墩",
    "藏剑谷",
]
_REWARD_TIER_OPTIONS = ["保持当前", "低阶", "高阶"]
_TIER_STAGE_OPTIONS = {"干员经验", "干员进阶", "技能提升", "武器进阶"}
_STAGE_SEQUENCE_OPTIONS = [
    item
    for stage in _STAGE_OPTIONS
    for item in (
        [stage, f"{stage}低阶", f"{stage}高阶"]
        if stage in _TIER_STAGE_OPTIONS
        else [stage]
    )
]
_TEAM_OPTIONS = ["不换队伍", "1", "2", "3", "4", "5"]
_CONFIG_PROFILE_OPTIONS = ["隐藏", "⭐⭐⭐ 默认"]
_BOAT_OPTIONS = ["收集线索", "制造舱", "培养舱"]
_ACTIVITY_REWARD_OPTIONS = ["周常奖励", "理智补给"]
_TRADE_GOODS_OPTIONS = [
    "精选荞愈胶囊",
    "高容谷地电池",
    "精选柑实罐头",
    "中容谷地电池",
    "优质荞愈胶囊",
    "优质柑实罐头",
    "荞愈胶囊",
    "柑实罐头",
    "晶体外壳",
    "息壤玉葫芦",
    "息壤葫芦",
    "中容武陵电池",
    "优质芽针针剂",
    "优质锦草软饮",
    "低容武陵电池",
    "芽针针剂",
    "锦草软饮",
    "重息壤",
    "赫铜零件",
]
_DELIVERY_TARGET_TICKET_OPTIONS = ["119000", "79800", "73100"]
_DELIVERY_AREA_OPTIONS = ["武陵"]
_DELIVERY_TEST_TARGET_OPTIONS = [
    "无",
    "通向送货点",
    "通向送货点试验园区",
    "常沄",
    "资源",
    "彦宁",
    "齐纶",
    "于施",
    "苏白易",
    "普里莫",
    "赵昭",
    "裴令容",
    "阿禾",
    "完整循环测试",
]
_DELIVERY_FULL_CYCLE_LOCATION_OPTIONS = ["武陵城", "试验园区"]
_WAREHOUSE_OPTIONS = ["valley4", "wuling"]
_WAREHOUSE_ITEM_OPTIONS = ["蓝铁矿", "高容谷地电池", "源矿", "致密源石粉末"]
_EXTERNAL_COMMAND_TIMING_OPTIONS = ["任务最开始", "任务最后"]

_SELECT_OPTIONS: dict[str, dict[str, list[str]]] = {
    "Basic Options.json": {
        "Use DirectML": ["Auto", "Yes", "No"],
        "Start/Stop": ["None", "F9", "F10", "F11", "F12"],
    },
    "DeliveryTask.json": {
        "目标券数": _DELIVERY_TARGET_TICKET_OPTIONS,
        "地区切换": _DELIVERY_AREA_OPTIONS,
        "选择测试对象": _DELIVERY_TEST_TARGET_OPTIONS,
        "完整循环测试区域": _DELIVERY_FULL_CYCLE_LOCATION_OPTIONS,
    },
    "WarehouseTransferTask.json": {
        "发货仓库": _WAREHOUSE_OPTIONS,
        "收货仓库": _WAREHOUSE_OPTIONS,
        "物品": _WAREHOUSE_ITEM_OPTIONS,
    },
    "RealtimeDetectTask.json": {
        "YOLO模型": ["battle_end_default"],
        "检测目标": ["battle_end"],
    },
}

_GLOBAL_SELECT_OPTIONS: dict[str, list[str]] = {
    "体力本": _STAGE_OPTIONS,
    "体力本奖励档位": _REWARD_TIER_OPTIONS,
    "刷本序列": _STAGE_SEQUENCE_OPTIONS,
    "指定的队伍编号": _TEAM_OPTIONS,
    "配置选择": _CONFIG_PROFILE_OPTIONS,
    "交易货品优先序列": _TRADE_GOODS_OPTIONS,
    "帝江号收菜操作": _BOAT_OPTIONS,
    "活动奖励": _ACTIVITY_REWARD_OPTIONS,
    "外部命令执行时机": _EXTERNAL_COMMAND_TIMING_OPTIONS,
}


def _parse_po_file(po_path: Path) -> dict[str, str]:
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
    try:
        with mo_path.open("rb") as fp:
            catalog = gettext.GNUTranslations(fp)._catalog
        return {
            msgid: msgstr
            for msgid, msgstr in catalog.items()
            if isinstance(msgid, str)
            and msgid
            and isinstance(msgstr, str)
            and msgstr
        }
    except Exception:
        return {}


def _parse_ts_file(ts_path: Path) -> dict[str, str]:
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


def load_okef_option_labels(root_path: Path | str) -> dict[str, str]:
    """从 OK-EF 安装目录加载英中标签映射。"""

    root = Path(root_path)
    labels: dict[str, str] = {}

    i18n_candidates = [
        root / "i18n",
        root / "_internal" / "i18n",
        root / "data" / "apps" / "ok-ef" / "repo" / "i18n",
        root / "data" / "apps" / "ok-ef" / "working" / "i18n",
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
        root / "data" / "apps" / "ok-ef" / "repo" / "ok" / "gui" / "i18n" / "zh_CN.ts",
        root / "data" / "apps" / "ok-ef" / "working" / "ok" / "gui" / "i18n" / "zh_CN.ts",
    ]
    for ts_file in ts_candidates:
        if ts_file.is_file():
            loaded = _parse_ts_file(ts_file)
            if loaded:
                labels.update(loaded)
                break

    return labels


def _infer_field_type(value: Any) -> str:
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
    if key in labels:
        return labels[key]
    if key in _FALLBACK_LABELS:
        return _FALLBACK_LABELS[key]
    return key


def _is_internal_field(name: str) -> bool:
    return name.startswith("_")


def _is_account_field(name: str) -> bool:
    return name in _ACCOUNT_FIELD_NAMES


def _is_visible_config(filename: str) -> bool:
    return not filename.startswith("_") and filename not in _SKIP_CONFIG_FILES


def _group_for_config(filename: str) -> str:
    if filename in _TASK_INDEX_MAP:
        return "一次性任务配置"
    if filename.endswith("Task.json"):
        return "后台任务配置"
    if "Config" in filename or "Options" in filename or "Hotkey" in filename:
        return "全局配置"
    return "其他配置"


def _sort_key(filename: str) -> tuple[int, int, str]:
    if filename in _TASK_INDEX_MAP:
        return (0, _TASK_INDEX_MAP[filename], filename)
    if filename.endswith("Task.json"):
        return (1, 0, filename)
    return (2, 0, filename)


def _append_current_values(options: list[str], raw_value: Any) -> list[str]:
    current_values = raw_value if isinstance(raw_value, list) else [raw_value]
    result = list(options)
    for value in current_values:
        if value is None:
            continue
        text = str(value)
        if text and text not in result:
            result.append(text)
    return result


def _get_select_options(filename: str, field_name: str, raw_value: Any) -> list[str] | None:
    configured = _SELECT_OPTIONS.get(filename, {}).get(field_name)
    if configured is None:
        configured = _GLOBAL_SELECT_OPTIONS.get(field_name)
    if configured is None:
        return None
    return _append_current_values(configured, raw_value)


def build_fields_for_config(
    filename: str,
    json_data: dict[str, Any],
    option_labels: dict[str, str],
) -> list[dict[str, Any]]:
    """把单个 JSON 配置转换成前端字段列表。"""

    def make_field(name: str, raw_value: Any) -> dict[str, Any]:
        opts = _get_select_options(filename, name, raw_value)
        if opts is not None:
            field_type = "list" if isinstance(raw_value, list) else "select"
        else:
            field_type = _infer_field_type(raw_value)

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

    return [
        make_field(key, value)
        for key, value in json_data.items()
        if not _is_internal_field(key) and not _is_account_field(key)
    ]


def get_config_info_from_dir(config_dir: Path | str) -> list[dict[str, Any]]:
    """按实际配置目录返回可编辑配置文件元信息。"""

    root = Path(config_dir)
    if not root.is_dir():
        return []

    result = []
    for path in sorted(root.glob("*.json"), key=lambda item: _sort_key(item.name)):
        if not _is_visible_config(path.name):
            continue
        result.append(
            {
                "filename": path.name,
                "displayName": _DISPLAY_NAMES.get(path.name, path.stem),
                "group": _group_for_config(path.name),
                "taskIndex": _TASK_INDEX_MAP.get(path.name),
                "fieldCount": 1,
            }
        )
    return result
