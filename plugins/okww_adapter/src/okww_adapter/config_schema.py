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

"""OK-WW 配置 Schema：全部从 ok-ww 安装目录动态解析，不含静态字段白名单。

数据来源（见 :mod:`okww_adapter.ast_config`）：
- 任务注册表 / ``-t`` 序号 ← ``repo/config.py`` 的 onetime_tasks + global_configs
- 下拉 / 多选候选项 ← ``repo/src/task/*.py`` 的 config_type（含引用变量的列表字面量）
- 字段中文标签 ← ok-ww 内置 i18n（.mo/.po/.ts）
- 字段说明 ← config_description + i18n

选项随 ok-ww 版本演进，因此按 ``config.py`` 顶层 version 缓存整份 schema：
版本不变直接命中缓存，避免每次 list 都重解析源码。仅在 repo 源码不可读时，
build_fields_for_config 退化为纯 JSON 值类型推断（无下拉、无翻译）。
"""

from __future__ import annotations

import gettext
import re
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from .ast_config import (
    find_repo_root,
    parse_project_version,
    parse_task_metadata,
    parse_task_registry,
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
            # ponytail: 依赖 GNUTranslations 私有 _catalog，已过滤空 msgid 元数据头。
            #   公开 API 需预先枚举全部 key，此处无 key 集合，务实取用。
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


# ─── 排除：不暴露给 MAS 用户编辑的配置文件 / 字段 ─────────────────────────
#
# 动态注册以 config.py 的 onetime_tasks + global_configs 为准，此处仅剔除
# 注册表里存在、但对代理配置无意义的项（空文件、纯调试项）。

_EXCLUDED_FILES: frozenset[str] = frozenset({
    "GardenTask.json",  # 无可配置字段，暴露仅增噪音
})


def _is_internal_field(name: str) -> bool:
    """ok-ww 框架内部字段（_enabled 等），不暴露给 MAS 用户编辑。"""
    return name.startswith("_")


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


# ─── 动态 schema：解析结果按 (root, version) 缓存 ─────────────────────────

# {resolved_root: (version, registry, {filename: {field: field_meta_dict}})}
_SCHEMA_CACHE: dict[str, tuple[str, list[dict[str, Any]], dict[str, dict[str, Any]]]] = {}


def _resolve_root(root_path: Path | str) -> Path:
    return Path(root_path).resolve()


def _build_schema(repo_root: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """解析源码，构建 (文件注册表, {filename: {field: {type,options,description}}})。"""

    registry: list[dict[str, Any]] = []
    field_specs: dict[str, dict[str, Any]] = {}
    for task in parse_task_registry(repo_root):
        if task.filename in _EXCLUDED_FILES:
            continue
        task_name, fields = parse_task_metadata(repo_root, task.class_name)
        registry.append(
            {
                "filename": task.filename,
                "className": task.class_name,
                "group": task.group,
                "taskIndex": task.task_index,
                # task 的 self.name（英文/中文），供一级菜单显示名翻译；全局配置无 class 时为空。
                "taskName": task_name,
            }
        )
        field_specs[task.filename] = {
            name: {
                "type": meta.type,
                "options": meta.options,
                "description": meta.description,
            }
            for name, meta in fields.items()
        }
    return registry, field_specs


def _get_schema(
    root_path: Path | str,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]] | None:
    """取 (注册表, 字段规格)，按 config.py version 缓存；源码不可读返回 None。"""

    resolved = _resolve_root(root_path)
    repo_root = find_repo_root(resolved)
    if repo_root is None:
        return None
    version = parse_project_version(repo_root)

    cached = _SCHEMA_CACHE.get(str(resolved))
    if cached is not None and cached[0] == version:
        return cached[1], cached[2]

    registry, field_specs = _build_schema(repo_root)
    _SCHEMA_CACHE[str(resolved)] = (version, registry, field_specs)
    return registry, field_specs


def _display_name(item: dict[str, Any], option_labels: dict[str, str]) -> str:
    """一级菜单显示名：翻译(self.name) > 翻译(文件名stem) > stem。

    任务文件用 self.name（Daily Task→日常一条龙），部分 self.name 本就是中文；
    全局配置无 class，回退用文件名 stem 翻译（Game Hotkey→游戏快捷键）。
    """
    stem = item["filename"].removesuffix(".json")
    task_name = item.get("taskName") or ""
    if task_name:
        return _translate(task_name, option_labels)
    return _translate(stem, option_labels)


def get_all_config_info(
    root_path: Path | str | None = None,
    option_labels: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """获取所有可编辑配置文件的元信息（动态注册；无源码时返回空）。

    option_labels 提供时用于翻译一级菜单显示名；缺省则按 root 加载。
    """

    if root_path is None:
        return []
    schema = _get_schema(root_path)
    if schema is None:
        return []
    registry, _ = schema
    labels = option_labels if option_labels is not None else load_okww_option_labels(root_path)
    return [
        {
            "filename": item["filename"],
            "displayName": _display_name(item, labels),
            "group": item["group"],
            "taskIndex": item["taskIndex"],
        }
        for item in registry
    ]


def get_field_specs(root_path: Path | str) -> dict[str, dict[str, Any]]:
    """获取 {filename: {field: {type,options,description}}}（无源码时为空）。"""

    schema = _get_schema(root_path)
    return schema[1] if schema is not None else {}


def build_fields_for_config(
    filename: str,
    json_data: dict[str, Any],
    option_labels: dict[str, str],
    field_specs: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """构建单个配置文件的前端字段列表。

    - field_specs 提供源码解析出的 type/options/description（下拉候选项来源）。
    - JSON 中的字段按值推断类型；源码声明为 drop_down/multi_selection 的覆盖为
      select/list 并附候选项。
    - 源码声明但 JSON 缺失的字段（ok-ww 新增项）也补入，值为 None。
    """

    specs = (field_specs or {}).get(filename, {})
    seen: set[str] = set()

    def make_field(name: str, raw_value: Any) -> dict[str, Any]:
        seen.add(name)
        spec = specs.get(name, {})
        options = spec.get("options") or None
        spec_type = spec.get("type") or ""

        if spec_type in ("drop_down", "multi_selection"):
            field_type = "list" if (
                spec_type == "multi_selection" or isinstance(raw_value, list)
            ) else "select"
        else:
            field_type = _infer_field_type(raw_value)

        return {
            "name": name,
            "type": field_type,
            "label": _translate(name, option_labels),
            "description": _translate(spec["description"], option_labels)
            if spec.get("description")
            else "",
            "value": raw_value,
            # options 保持源码原始英文值：它是写回 ok-ww 的存储值，
            # 前端用 optionLabels 映射显示中文，切勿在此预翻译。
            "options": list(options) if options else None,
            "min": None,
            "max": None,
            "step": None,
        }

    fields = [
        make_field(name, value)
        for name, value in json_data.items()
        if not _is_internal_field(name)
    ]

    # 源码声明但当前 JSON 未落地的字段（ok-ww 新增配置项）。
    for name in specs:
        if name not in seen and not _is_internal_field(name):
            fields.append(make_field(name, None))

    return fields

