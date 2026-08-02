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

import gettext
import re
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree

from ..common.config_schema import (
    CONFIDENCE_DECLARED,
    SOURCE_PROVIDER,
    FieldChoice,
    FieldDeclaration,
    FieldSchema,
    materialize_field_schemas,
    render_legacy_fields,
)


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


def _translate(key: str, labels: dict[str, str]) -> str:
    """查找翻译：ok-ww 标签 > 兜底标签 > 原始 key。"""
    if key in labels:
        return labels[key]
    if key in _FALLBACK_LABELS:
        return _FALLBACK_LABELS[key]
    return key


def _is_internal_field(name: str) -> bool:
    return name.startswith("_")


def _provider_declarations_for_config(
    filename: str,
    json_data: dict[str, Any],
    option_labels: dict[str, str],
) -> tuple[FieldDeclaration, ...]:
    names = list(json_data)
    names.extend(
        name
        for name in SELECT_OPTIONS.get(filename, {})
        if name not in json_data
    )

    declarations: list[FieldDeclaration] = []
    for name in names:
        if _is_internal_field(name):
            continue
        options = _get_select_options(filename, name)
        label = _translate(name, option_labels)
        if options is None and label == name:
            continue
        declarations.append(
            FieldDeclaration(
                path=name,
                label=label,
                choices=tuple(
                    FieldChoice(
                        value=value,
                        label=_translate(value, option_labels),
                    )
                    for value in options or ()
                ),
                source=SOURCE_PROVIDER,
                confidence=CONFIDENCE_DECLARED,
            )
        )
    return tuple(declarations)


def build_field_schemas_for_config(
    filename: str,
    json_data: dict[str, Any],
    option_labels: dict[str, str],
    *,
    upstream: Iterable[FieldDeclaration] = (),
) -> tuple[FieldSchema, ...]:
    """用公共 FieldSchema 物化 OK-WW 配置字段。"""

    visible_data = {
        name: value
        for name, value in json_data.items()
        if not _is_internal_field(name)
    }
    visible_upstream = tuple(
        declaration
        for declaration in upstream
        if not _is_internal_field(declaration.path)
    )
    return materialize_field_schemas(
        visible_data,
        upstream=visible_upstream,
        provider=_provider_declarations_for_config(
            filename,
            visible_data,
            option_labels,
        ),
    )


def build_fields_for_config(
    filename: str,
    json_data: dict[str, Any],
    option_labels: dict[str, str],
    *,
    upstream: Iterable[FieldDeclaration] = (),
) -> list[dict[str, Any]]:
    """投影为当前宿主编辑器消费的兼容字段。"""

    schemas = build_field_schemas_for_config(
        filename,
        json_data,
        option_labels,
        upstream=upstream,
    )
    return render_legacy_fields(schemas, json_data)


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
