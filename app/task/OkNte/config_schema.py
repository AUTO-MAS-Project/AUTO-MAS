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

import json
import re
import struct
from copy import deepcopy
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock
from time import sleep
from typing import Any
from xml.etree import ElementTree

# ─── OK-NTE 翻译文件自动加载 ─────────────────────────────────────────────────

_OKNTE_CONFIG_WRITE_LOCK = Lock()

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
                length, offset = struct.unpack_from(fmt, data, table_offset + i * 8)
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
    "Routine Items": "日常任务流程",
    "daily_anomaly": "异象界域",
    "daily_anomaly_hunter": "异象追猎",
    "coffee": "一咖舍",
    "daily_claim": "日常领取",
    "cinema_date": "影院约会",
    "fountain": "喷泉签到",
    "furniture": "异象家具",
    "gift": "羁遇赠礼",
}


# ─── 新版 DailyRoutine 默认值与旧版 DailyTask 迁移 ────────────────────────

DAILY_ROUTINE_TASK_FILE = "DailyRoutineTask.json"
DAILY_ROUTINE_CONFIGS_FILE = "DailyRoutineTaskConfigs.json"
LEGACY_DAILY_TASK_FILE = "DailyTask.json"

DAILY_ROUTINE_ITEMS: list[dict[str, Any]] = [
    {
        "id": "daily_anomaly",
        "label": "异象界域",
        "enabled": True,
        "exclusiveGroup": "daily_anomaly",
    },
    {
        "id": "daily_anomaly_hunter",
        "label": "异象追猎",
        "enabled": False,
        "exclusiveGroup": "daily_anomaly",
    },
    {"id": "coffee", "label": "一咖舍", "enabled": False, "exclusiveGroup": None},
    {"id": "daily_claim", "label": "日常领取", "enabled": True, "exclusiveGroup": None},
    {
        "id": "cinema_date",
        "label": "影院约会",
        "enabled": False,
        "exclusiveGroup": None,
    },
    {"id": "fountain", "label": "喷泉签到", "enabled": False, "exclusiveGroup": None},
    {"id": "furniture", "label": "异象家具", "enabled": False, "exclusiveGroup": None},
    {"id": "gift", "label": "羁遇赠礼", "enabled": False, "exclusiveGroup": None},
]

DAILY_ROUTINE_ITEM_DEFINITIONS: list[dict[str, Any]] = [
    {
        "id": item["id"],
        "label": item["label"],
        "exclusiveGroup": item["exclusiveGroup"],
        "defaultEnabled": item["enabled"],
    }
    for item in DAILY_ROUTINE_ITEMS
]

DEFAULT_CONFIG_DATA: dict[str, dict[str, Any]] = {
    DAILY_ROUTINE_TASK_FILE: {
        "Routine Items": [
            {"id": item["id"], "enabled": item["enabled"]}
            for item in DAILY_ROUTINE_ITEMS
        ],
        "Exit After Task": True,
    },
    DAILY_ROUTINE_CONFIGS_FILE: {
        "daily_anomaly": {
            "目标消耗体力": 180,
            "任务类型": "经验与甲硬币",
            "具体奖励目标": "角色经验",
            "异能材料序号": 1,
            "弧盘材料序号": 1,
            "空幕序号": 1,
            "循环模式": "停用",
            "循环序列": [],
        },
        "daily_anomaly_hunter": {
            "目标消耗体力": 180,
            "追猎目标": "音霸魔王",
        },
        "coffee": {
            "模式": "领取/补货",
            "领取收益": True,
            "补货货物": True,
            "购买货物送货上门": True,
            "优化商品": False,
            "补货时长": "auto",
            "商品位数量": "auto",
            "价格表": "auto",
        },
        "daily_claim": {
            "邮件": True,
            "活跃度奖励": True,
            "环期任务奖励": True,
        },
        "cinema_date": {
            "约会目标": "",
        },
        "fountain": {
            "签到方式": "签到",
        },
        "furniture": {},
        "gift": {},
    },
    "CoffeeTask.json": {
        "模式": "领取/补货",
        "领取收益": True,
        "补货货物": True,
        "购买货物送货上门": True,
        "优化商品": False,
        "补货时长": "auto",
        "商品位数量": "auto",
        "价格表": "auto",
    },
}


def _deep_merge_config(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """合并配置默认值，保留用户已有字段。"""

    result = deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge_config(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def merge_oknte_config_data(
    existing_data: dict[str, Any],
    update_data: dict[str, Any],
) -> dict[str, Any]:
    """深合并前端提交的 OK-NTE 配置更新。"""

    return _deep_merge_config(existing_data, update_data)


def _normalize_daily_routine_items(raw_items: Any) -> list[dict[str, Any]]:
    """按新版 ok-nte 的日常任务项结构补齐缺失项并处理互斥组。"""

    entries = {item["id"]: item for item in DAILY_ROUTINE_ITEMS}
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()

    if isinstance(raw_items, list):
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            task_id = raw_item.get("id")
            if task_id not in entries or task_id in seen:
                continue
            normalized.append(
                {"id": task_id, "enabled": bool(raw_item.get("enabled", False))}
            )
            seen.add(task_id)

    for item in DAILY_ROUTINE_ITEMS:
        if item["id"] not in seen:
            normalized.append({"id": item["id"], "enabled": bool(item["enabled"])})

    enabled_groups: set[str] = set()
    for item in normalized:
        exclusive_group = entries[item["id"]].get("exclusiveGroup")
        if not exclusive_group or not item["enabled"]:
            continue
        if exclusive_group in enabled_groups:
            item["enabled"] = False
        else:
            enabled_groups.add(exclusive_group)

    return normalized


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"OK-NTE 配置文件必须是 JSON 对象: {path}")
    return data


def _write_oknte_config_data(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp_file:
            tmp_path = Path(tmp_file.name)
            json.dump(data, tmp_file, ensure_ascii=False, indent=4)
        for retry in range(5):
            try:
                tmp_path.replace(path)
                break
            except PermissionError:
                if retry == 4:
                    raise
                sleep(0.02 * (retry + 1))
    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()


def write_oknte_config_data(path: Path, data: dict[str, Any]) -> None:
    """原子写入 OK-NTE JSON 配置。"""

    with _OKNTE_CONFIG_WRITE_LOCK:
        _write_oknte_config_data(path, data)


def update_oknte_config_data(
    path: Path,
    update_data: dict[str, Any],
) -> dict[str, Any]:
    """在同一写锁内读取、深合并并保存 OK-NTE 配置。"""

    with _OKNTE_CONFIG_WRITE_LOCK:
        existing_data = _read_json_object(path)
        merged_data = merge_oknte_config_data(existing_data, update_data)
        _write_oknte_config_data(path, merged_data)
    return merged_data


def _daily_routine_items_from_legacy(legacy: dict[str, Any]) -> list[dict[str, Any]]:
    items = _normalize_daily_routine_items(
        DEFAULT_CONFIG_DATA[DAILY_ROUTINE_TASK_FILE]["Routine Items"]
    )
    item_by_id = {item["id"]: item for item in items}

    if "副本类型" in legacy:
        item_by_id["daily_anomaly"]["enabled"] = legacy["副本类型"] != "不执行"
    elif "完成每日活跃度" in legacy:
        item_by_id["daily_anomaly"]["enabled"] = bool(legacy["完成每日活跃度"])

    claim_keys = ("领取邮件", "领取活跃度奖励", "领取环期任务奖励")
    if any(key in legacy for key in claim_keys):
        item_by_id["daily_claim"]["enabled"] = any(
            bool(legacy.get(key, True)) for key in claim_keys
        )

    coffee_mode = legacy.get("一咖舍任务", "不执行")
    item_by_id["coffee"]["enabled"] = coffee_mode != "不执行"
    item_by_id["cinema_date"]["enabled"] = bool(legacy.get("影院约会", False))
    item_by_id["fountain"]["enabled"] = legacy.get("喷泉签到", "不执行") != "不执行"
    item_by_id["furniture"]["enabled"] = bool(legacy.get("异象家具", False))
    item_by_id["gift"]["enabled"] = bool(legacy.get("羁遇赠礼", False))

    return _normalize_daily_routine_items(items)


def _daily_routine_configs_from_legacy(legacy: dict[str, Any]) -> dict[str, Any]:
    configs = deepcopy(DEFAULT_CONFIG_DATA[DAILY_ROUTINE_CONFIGS_FILE])

    for key in (
        "任务类型",
        "具体奖励目标",
        "异能材料序号",
        "弧盘材料序号",
        "空幕序号",
        "目标消耗体力",
        "循环模式",
        "循环序列",
    ):
        if key in legacy:
            configs["daily_anomaly"][key] = deepcopy(legacy[key])

    if "循环模式" not in legacy and "自动循环项目" in legacy:
        configs["daily_anomaly"]["循环模式"] = (
            "自动循环序号/目标" if legacy["自动循环项目"] else "停用"
        )

    coffee_mode = legacy.get("一咖舍任务")
    if coffee_mode == "运行一咖舍自动化":
        configs["coffee"]["模式"] = "自动化"
    elif coffee_mode == "领取/补货一咖舍":
        configs["coffee"]["模式"] = "领取/补货"

    legacy_claim_map = {
        "邮件": "领取邮件",
        "活跃度奖励": "领取活跃度奖励",
        "环期任务奖励": "领取环期任务奖励",
    }
    for new_key, old_key in legacy_claim_map.items():
        if old_key in legacy:
            configs["daily_claim"][new_key] = bool(legacy[old_key])

    if "约会目标" in legacy:
        configs["cinema_date"]["约会目标"] = legacy["约会目标"]
    fountain_mode = legacy.get("喷泉签到")
    if fountain_mode and fountain_mode != "不执行":
        configs["fountain"]["签到方式"] = fountain_mode

    return configs


def ensure_oknte_daily_routine_configs(config_dir: Path) -> None:
    """补齐新版 ok-nte DailyRoutine 配置，并从旧 DailyTask 配置迁移初值。"""

    legacy_data = _read_json_object(config_dir / LEGACY_DAILY_TASK_FILE)
    routine_path = config_dir / DAILY_ROUTINE_TASK_FILE
    routine_configs_path = config_dir / DAILY_ROUTINE_CONFIGS_FILE

    routine_default = deepcopy(DEFAULT_CONFIG_DATA[DAILY_ROUTINE_TASK_FILE])
    if legacy_data and not routine_path.is_file():
        routine_default["Routine Items"] = _daily_routine_items_from_legacy(legacy_data)
    current_routine_data = _read_json_object(routine_path)
    routine_data = _deep_merge_config(routine_default, current_routine_data)
    routine_data["Routine Items"] = _normalize_daily_routine_items(
        routine_data.get("Routine Items")
    )
    if routine_data != current_routine_data:
        write_oknte_config_data(routine_path, routine_data)

    routine_configs_default = deepcopy(DEFAULT_CONFIG_DATA[DAILY_ROUTINE_CONFIGS_FILE])
    if legacy_data and not routine_configs_path.is_file():
        routine_configs_default = _daily_routine_configs_from_legacy(legacy_data)
    current_routine_configs_data = _read_json_object(routine_configs_path)
    routine_configs_data = _deep_merge_config(
        routine_configs_default,
        current_routine_configs_data,
    )
    if routine_configs_data != current_routine_configs_data:
        write_oknte_config_data(routine_configs_path, routine_configs_data)

    for filename, default_data in DEFAULT_CONFIG_DATA.items():
        if filename in (DAILY_ROUTINE_TASK_FILE, DAILY_ROUTINE_CONFIGS_FILE):
            continue
        path = config_dir / filename
        current_data = _read_json_object(path)
        merged_data = _deep_merge_config(default_data, current_data)
        if merged_data != current_data:
            write_oknte_config_data(path, merged_data)


# ─── 手工维护：下拉 / 多选的可选项列表 ───────────────────────────────────
#
# OK-NTE 打包后源码不可读，JSON 配置文件只存当前值不存侯选列表，
# 因此下拉 / 多选字段的选项必须在这里声明。
# 布尔、整数、文本字段无需声明——自动从 JSON 值推断类型。

SELECT_OPTIONS: dict[str, dict[str, list[str]]] = {
    # ── 任务配置 ──
    DAILY_ROUTINE_CONFIGS_FILE: {
        "任务类型": ["经验与甲硬币", "异能升级材料", "弧盘突破材料", "空幕"],
        "具体奖励目标": ["角色经验", "弧盘经验", "甲硬币"],
        "循环模式": ["停用", "自动循环序号/目标", "自定义循环"],
        "循环序列": [
            "角色经验",
            "弧盘经验",
            "甲硬币",
            "异能升级材料: 1",
            "异能升级材料: 2",
            "异能升级材料: 3",
            "异能升级材料: 4",
            "异能升级材料: 5",
            "弧盘突破材料: 1",
            "弧盘突破材料: 2",
            "弧盘突破材料: 3",
            "弧盘突破材料: 4",
            "弧盘突破材料: 5",
            "空幕: 1",
            "空幕: 2",
            "空幕: 3",
            "空幕: 4",
            "空幕: 5",
            "空幕: 6",
        ],
        "追猎目标": [
            "音霸魔王",
            "无首铁驭",
            "塞润尼缇",
            "黑之书",
            "海囚",
            "围巢鸟",
            "斑蝶",
        ],
        "模式": ["领取/补货", "自动化"],
        "补货时长": ["auto", "2小时", "4小时", "8小时", "24小时"],
        "商品位数量": ["auto", "1", "2", "3", "4", "5"],
        "价格表": ["auto", "disabled"],
        "签到方式": ["签到", "捞币"],
    },
    "DailyTask.json": {
        "任务类型": ["经验与甲硬币", "异能升级材料", "弧盘突破材料", "空幕"],
        "具体奖励目标": ["角色经验", "弧盘经验", "甲硬币"],
        "一咖舍任务": ["不执行", "领取/补货一咖舍", "运行一咖舍自动化"],
        "喷泉签到": ["不执行", "签到", "捞币"],
    },
    "AnomalyTask.json": {
        "任务类型": ["经验与甲硬币", "异能升级材料", "弧盘突破材料", "空幕"],
        "具体奖励目标": ["角色经验", "弧盘经验", "甲硬币"],
    },
    "CoffeeTask.json": {
        "模式": ["领取/补货", "自动化"],
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
        DAILY_ROUTINE_TASK_FILE,
        DAILY_ROUTINE_CONFIGS_FILE,
    ],
    "触发配置": [
        "AutoCombatTask.json",
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
    DAILY_ROUTINE_TASK_FILE: "日常任务流程",
    DAILY_ROUTINE_CONFIGS_FILE: "日常子任务配置",
    LEGACY_DAILY_TASK_FILE: "旧版日常任务",
    "CoffeeTask.json": "一咖舍",
    "FishingTask.json": "自动钓鱼",
    "AnomalyTask.json": "异象界域",
    "AnomalyHunter.json": "异象追猎",
    "RhythmTask.json": "自动音游",
    "OwnerSelectionTask.json": "店长特供",
    "AutoHeistTask.json": "自动粉爪大劫案",
    "BagelAITools.json": "呗果智能体",
    "WhirlwindTask.json": "自动小旋风",
    "DSDFarmTask.json": "九百九十九夜",
    "CombatDetectionTestTask.json": "自动战斗检测诊断",
    "DarkTask.json": "暗域任务",
    "DiagnosisTask.json": "诊断",
    "DailyClaimTask.json": "日常领取",
    "GiftTask.json": "羁遇赠礼",
    "FountainTask.json": "喷泉签到",
    "FurnitureTask.json": "异象家具",
    "CinemaDateTask.json": "影院约会",
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
    DAILY_ROUTINE_TASK_FILE: 2,
    "FishingTask.json": 3,
    "AnomalyTask.json": 4,
    "AnomalyHunter.json": 5,
    "RhythmTask.json": 6,
    "OwnerSelectionTask.json": 7,
    "AutoHeistTask.json": 8,
    "BagelAITools.json": 9,
    "WhirlwindTask.json": 10,
    "DSDFarmTask.json": 11,
    "CombatDetectionTestTask.json": 12,
    "DiagnosisTask.json": 13,
    "DailyClaimTask.json": 14,
    "GiftTask.json": 15,
    "CoffeeTask.json": 16,
    "FountainTask.json": 17,
    "FurnitureTask.json": 18,
    "CinemaDateTask.json": 19,
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
    if isinstance(value, dict):
        return "object"
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
    if filename == DAILY_ROUTINE_CONFIGS_FILE:
        json_data = _deep_merge_config(
            DEFAULT_CONFIG_DATA[DAILY_ROUTINE_CONFIGS_FILE],
            json_data,
        )
        fields: list[dict[str, Any]] = []
        for item in DAILY_ROUTINE_ITEMS:
            task_id = item["id"]
            value = json_data.get(task_id, {})
            child_fields = build_fields_for_config(
                f"{DAILY_ROUTINE_CONFIGS_FILE}::{task_id}",
                value if isinstance(value, dict) else {},
                option_labels,
            )
            if not child_fields:
                continue
            fields.append(
                {
                    "name": task_id,
                    "type": "object",
                    "label": item["label"],
                    "description": "",
                    "value": value,
                    "options": None,
                    "children": child_fields,
                    "itemDefinitions": None,
                    "min": None,
                    "max": None,
                    "step": None,
                }
            )
        return fields

    seen: set[str] = set()
    default_data = DEFAULT_CONFIG_DATA.get(filename, {})

    def _is_internal(name: str) -> bool:
        """OK-NTE 框架内部字段（_enabled 等），不暴露给 MAS 用户编辑。"""
        return name.startswith("_")

    def make_field(name: str, raw_value: Any) -> dict[str, Any]:
        seen.add(name)
        real_filename, _sep, _nested_group = filename.partition("::")
        opts = _get_select_options(real_filename, name)

        if real_filename == DAILY_ROUTINE_TASK_FILE and name == "Routine Items":
            value = _normalize_daily_routine_items(raw_value)
            return {
                "name": name,
                "type": "routine_items",
                "label": _translate(name, option_labels),
                "description": "",
                "value": value,
                "options": None,
                "children": None,
                "itemDefinitions": DAILY_ROUTINE_ITEM_DEFINITIONS,
                "min": None,
                "max": None,
                "step": None,
            }

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
                "children": None,
                "itemDefinitions": None,
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
            "children": None,
            "itemDefinitions": None,
            "min": None,
            "max": None,
            "step": None,
        }

    json_data = _deep_merge_config(default_data, json_data)
    fields = [
        make_field(k, v)
        for k, v in json_data.items()
        if not _is_internal(k)  # 屏蔽 _enabled 等 OK-NTE 框架内部字段
    ]

    # 补充：SELECT_OPTIONS 中有定义但 JSON 中没有的字段（OK-NTE 新增配置项）
    known_options = {} if "::" in filename else SELECT_OPTIONS.get(filename, {})
    for name in known_options:
        if name not in seen and not _is_internal(name):
            fields.append(make_field(name, default_data.get(name)))

    return fields


# ─── API 辅助函数 ─────────────────────────────────────────────────────────


def get_all_config_info() -> list[dict[str, Any]]:
    """获取所有配置文件的元信息（用于前端列表展示）。"""
    result = []
    for group_name, filenames in CONFIG_GROUPS.items():
        for filename in filenames:
            # 字段数量 = JSON 中已有的 + SELECT_OPTIONS 中新增的
            field_count = max(
                len(DEFAULT_CONFIG_DATA.get(filename, {})),
                len(SELECT_OPTIONS.get(filename, {})),
            )
            result.append(
                {
                    "filename": filename,
                    "displayName": CONFIG_DISPLAY_NAMES.get(filename, filename),
                    "group": group_name,
                    "taskIndex": TASK_INDEX_MAP.get(filename),
                    "fieldCount": max(field_count, 1),  # 至少 1，避免显示 0
                }
            )
    return result
