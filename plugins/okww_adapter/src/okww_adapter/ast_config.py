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

"""静态解析 ok-ww 源码，动态提取任务注册表与配置项元数据。

数据源全部来自 ok-ww 安装目录内的 repo 源码，不 import 项目模块：

- ``repo/config.py`` 的 ``onetime_tasks`` → 任务文件注册表与 ``-t`` 序号
- ``repo/config.py`` 的 ``global_configs`` → 全局配置文件（ConfigOption 首参即文件名）
- ``repo/src/task/*.py`` 的 ``config_type`` → 下拉 / 多选候选项与类型
- ``repo/src/task/*.py`` 的 ``config_description`` → 字段英文说明

纯 AST 解析拿不到运行期变量（如 ``self.boss_list``）赋值的 options，
这类字段回退到 :data:`okww_adapter.config_schema.DYNAMIC_OPTION_FALLBACK`。
源码不存在（纯安装态无 repo）时所有函数返回空，调用方据此判定不可用。
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# repo 相对 ok-ww 根目录的候选位置（源码态 / 打包态）。
_REPO_CANDIDATES = (
    "data/apps/ok-ww/repo",
    "repo",
    ".",
)


@dataclass(frozen=True)
class OkwwTaskFile:
    """一个可展示配置文件的静态描述。"""

    filename: str
    class_name: str
    group: str
    task_index: int | None


@dataclass
class OkwwFieldMeta:
    """单个配置字段的静态元数据。"""

    type: str = ""  # drop_down / multi_selection（空表示未声明）
    options: list[str] = field(default_factory=list)
    description: str = ""
    dynamic_options: bool = False  # options 引用运行期变量，静态读不到
    option_ref: str = ""  # options 引用的变量名（尾段），二次解析用


def find_repo_root(root_path: Path | str) -> Path | None:
    """在 ok-ww 安装目录内定位含 config.py 的 repo 源码根。"""

    root = Path(root_path)
    for candidate in _REPO_CANDIDATES:
        repo = (root / candidate).resolve()
        if (repo / "config.py").is_file() and (repo / "src" / "task").is_dir():
            return repo
    return None


def _literal_or_none(node: ast.AST | None) -> Any:
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError):
        return None


def parse_project_version(repo_root: Path) -> str:
    """提取 config.py 顶层 ``version = "vX.Y.Z"``，作为选项缓存的失效键。"""

    config_py = repo_root / "config.py"
    try:
        tree = ast.parse(config_py.read_text(encoding="utf-8-sig"))
    except (OSError, SyntaxError):
        return ""
    for node in getattr(tree, "body", []):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "version" for t in node.targets):
            continue
        value = _literal_or_none(node.value)
        if isinstance(value, str):
            return value
    return ""



def _find_config_dict(tree: ast.AST) -> ast.Dict | None:
    """config.py 顶层 ``config = {...}`` 的字典节点。"""

    for node in getattr(tree, "body", []):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(t, ast.Name) and t.id == "config" for t in node.targets
        ):
            continue
        if isinstance(node.value, ast.Dict):
            return node.value
    return None


def _dict_get(node: ast.Dict, key: str) -> ast.AST | None:
    for k, v in zip(node.keys, node.values):
        if isinstance(k, ast.Constant) and k.value == key:
            return v
    return None


def _parse_task_list(node: ast.AST | None) -> list[str]:
    """解析 ``[["src.task.X", "X"], ...]`` → 类名列表。"""

    if not isinstance(node, (ast.List, ast.Tuple)):
        return []
    names: list[str] = []
    for item in node.elts:
        value = _literal_or_none(item)
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            names.append(str(value[1]))
    return names


def _global_config_filenames(config_py: Path, config_dict: ast.Dict) -> list[str]:
    """global_configs 引用的 ConfigOption 变量 → 其首个字符串参数（文件名）。"""

    ref = _dict_get(config_dict, "global_configs")
    if not isinstance(ref, (ast.List, ast.Tuple)):
        return []
    wanted = {elt.id for elt in ref.elts if isinstance(elt, ast.Name)}
    if not wanted:
        return []

    tree = ast.parse(config_py.read_text(encoding="utf-8-sig"))
    resolved: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        target = node.targets[0] if len(node.targets) == 1 else None
        if not isinstance(target, ast.Name) or target.id not in wanted:
            continue
        call = node.value
        if isinstance(call, ast.Call) and call.args:
            name = _literal_or_none(call.args[0])
            if isinstance(name, str) and name:
                resolved[target.id] = name
    # 保持 global_configs 声明顺序
    return [resolved[e.id] for e in ref.elts if isinstance(e, ast.Name) and e.id in resolved]


def parse_task_registry(repo_root: Path) -> list[OkwwTaskFile]:
    """从 config.py 构建任务文件注册表（onetime_tasks + global_configs）。"""

    config_py = repo_root / "config.py"
    try:
        tree = ast.parse(config_py.read_text(encoding="utf-8-sig"))
    except (OSError, SyntaxError):
        return []

    config_dict = _find_config_dict(tree)
    if config_dict is None:
        return []

    files: list[OkwwTaskFile] = []
    onetime = _parse_task_list(_dict_get(config_dict, "onetime_tasks"))
    for index, class_name in enumerate(onetime, start=1):
        files.append(
            OkwwTaskFile(
                filename=f"{class_name}.json",
                class_name=class_name,
                group="任务配置",
                task_index=index,
            )
        )

    for filename in _global_config_filenames(config_py, config_dict):
        files.append(
            OkwwTaskFile(
                filename=f"{filename}.json",
                class_name="",
                group="全局配置",
                task_index=None,
            )
        )
    return files


class _TaskConfigVisitor(ast.NodeVisitor):
    """收集单个 task 模块里 self.name / config_type / config_description。"""

    def __init__(self) -> None:
        self.name = ""
        self.fields: dict[str, OkwwFieldMeta] = {}
        # 收集 `self.X = [字面量]` / `X = [字面量]`，供 options 引用变量回填。
        self.list_vars: dict[str, list[str]] = {}

    def _meta(self, key: str) -> OkwwFieldMeta:
        return self.fields.setdefault(key, OkwwFieldMeta())

    def visit_Assign(self, node: ast.Assign) -> None:
        target = node.targets[0] if len(node.targets) == 1 else None

        # self.name = "Daily Task"
        if (
            isinstance(target, ast.Attribute)
            and target.attr == "name"
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
            and not self.name
        ):
            value = _literal_or_none(node.value)
            if isinstance(value, str):
                self.name = value

        # 列表字面量变量：self.boss_list = [...] / material_option_list = [...]
        var_name = self._assign_target_name(target)
        if var_name and isinstance(node.value, (ast.List, ast.Tuple)):
            literal = _literal_or_none(node.value)
            if isinstance(literal, (list, tuple)):
                self.list_vars[var_name] = [str(item) for item in literal]

        # self.config_type['X'] = {'type':..., 'options':[...]}
        if (
            isinstance(target, ast.Subscript)
            and isinstance(target.value, ast.Attribute)
            and target.value.attr == "config_type"
        ):
            key = _literal_or_none(target.slice)
            if isinstance(key, str) and isinstance(node.value, ast.Dict):
                self._apply_config_type(key, node.value)

        # self.config_type = {'X': {...}, 'Y': {...}}（整体赋值）
        if (
            isinstance(target, ast.Attribute)
            and target.attr == "config_type"
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
            and isinstance(node.value, ast.Dict)
        ):
            self._apply_config_type_map(node.value)

        self.generic_visit(node)

    def _apply_config_type_map(self, mapping: ast.Dict) -> None:
        for k, v in zip(mapping.keys, mapping.values):
            key = _literal_or_none(k)
            if isinstance(key, str) and isinstance(v, ast.Dict):
                self._apply_config_type(key, v)

    def _apply_config_type(self, key: str, spec: ast.Dict) -> None:
        meta = self._meta(key)
        for k, v in zip(spec.keys, spec.values):
            field_key = _literal_or_none(k)
            if field_key == "type":
                type_value = _literal_or_none(v)
                if isinstance(type_value, str):
                    meta.type = type_value
            elif field_key == "options":
                options = _literal_or_none(v)
                if isinstance(options, list):
                    meta.options = [str(item) for item in options]
                elif isinstance(v, ast.Attribute):
                    meta.option_ref = v.attr  # self.boss_list → 'boss_list'
                    meta.dynamic_options = True
                elif isinstance(v, ast.Name):
                    meta.option_ref = v.id  # material_option_list
                    meta.dynamic_options = True
                else:
                    meta.dynamic_options = True

    @staticmethod
    def _assign_target_name(target: ast.expr | None) -> str:
        """取赋值左值的变量名：self.X → 'X'，X → 'X'，其它 → ''。"""

        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
            return target.attr if target.value.id == "self" else ""
        if isinstance(target, ast.Name):
            return target.id
        return ""

    def resolve_option_refs(self) -> None:
        """用收集到的列表字面量变量回填 options 引用变量的字段。"""

        for meta in self.fields.values():
            if meta.option_ref and meta.option_ref in self.list_vars:
                meta.options = list(self.list_vars[meta.option_ref])
                meta.dynamic_options = False

    def visit_Call(self, node: ast.Call) -> None:
        # self.config_description.update({...})
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "update"
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == "config_description"
            and node.args
            and isinstance(node.args[0], ast.Dict)
        ):
            for k, v in zip(node.args[0].keys, node.args[0].values):
                key = _literal_or_none(k)
                desc = _literal_or_none(v)
                if isinstance(key, str) and isinstance(desc, str):
                    self._meta(key).description = desc
        self.generic_visit(node)


def parse_task_metadata(repo_root: Path, class_name: str) -> tuple[str, dict[str, OkwwFieldMeta]]:
    """解析 repo/src/task/<class>.py，返回 (英文任务名, 字段元数据)。"""

    if not class_name:
        return "", {}
    task_py = repo_root / "src" / "task" / f"{class_name}.py"
    try:
        tree = ast.parse(task_py.read_text(encoding="utf-8-sig"))
    except (OSError, SyntaxError):
        return "", {}
    visitor = _TaskConfigVisitor()
    visitor.visit(tree)
    visitor.resolve_option_refs()
    return visitor.name, visitor.fields
