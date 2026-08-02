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

"""从 ok-script 任务资源中静态提取配置字段声明。"""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..common.config_schema import (
    CONFIDENCE_DECLARED,
    CONTROL_MULTISELECT,
    CONTROL_SELECT,
    CONTROL_SWITCH,
    CONTROL_TEXTAREA,
    SOURCE_UPSTREAM,
    UNSET,
    FieldChoice,
    FieldDeclaration,
)
from .descriptor import OkProjectDescriptor, OkProjectDiagnostic, OkTaskDescriptor


@dataclass(frozen=True, slots=True)
class ConfigResourceDescription:
    """一个任务配置 JSON 的上游静态声明。"""

    filename: str
    display_name: str
    group: str
    task_index: int | None
    source_path: Path
    fields: tuple[FieldDeclaration, ...]


@dataclass(frozen=True, slots=True)
class ProjectConfigDescription:
    """项目内全部可静态证明的配置资源。"""

    resources: tuple[ConfigResourceDescription, ...]
    diagnostics: tuple[OkProjectDiagnostic, ...]
    fingerprint: str

    def get(self, filename: str) -> ConfigResourceDescription | None:
        for resource in self.resources:
            if resource.filename == filename:
                return resource
        return None


class ProjectConfigParser:
    """只解析 descriptor 已确认的任务模块，不导入项目代码。"""

    def __init__(self, descriptor: OkProjectDescriptor) -> None:
        self.descriptor = descriptor

    def parse(self) -> ProjectConfigDescription:
        resources: list[ConfigResourceDescription] = []
        diagnostics: list[OkProjectDiagnostic] = []
        source_hashes: list[tuple[str, str]] = []
        seen: set[tuple[Path, str]] = set()

        for task in self.descriptor.tasks:
            source_path = self._resolve_task_source(task)
            if source_path is None:
                continue
            class_name = task.class_name.rsplit(".", 1)[-1] or task.selector
            source_key = (source_path, class_name)
            if source_key in seen:
                continue
            seen.add(source_key)

            try:
                content = source_path.read_text(encoding="utf-8-sig")
                tree = ast.parse(content, filename=str(source_path))
            except (OSError, UnicodeError, SyntaxError) as exc:
                diagnostics.append(
                    OkProjectDiagnostic(
                        code="CONFIG_RESOURCE_PARSE_ERROR",
                        level="warning",
                        message=f"任务配置资源无法静态解析: {exc}",
                        path=str(source_path),
                    )
                )
                continue

            source_hashes.append(
                (
                    self._relative_source_path(source_path),
                    hashlib.sha256(content.encode("utf-8")).hexdigest(),
                )
            )
            resource = _parse_task_resource(
                tree,
                task=task,
                class_name=class_name,
                source_path=source_path,
            )
            if resource is not None and resource.fields:
                resources.append(resource)

        return ProjectConfigDescription(
            resources=tuple(resources),
            diagnostics=tuple(diagnostics),
            fingerprint=_build_config_fingerprint(
                descriptor_fingerprint=self.descriptor.fingerprint,
                source_hashes=source_hashes,
                resources=resources,
            ),
        )

    def _resolve_task_source(self, task: OkTaskDescriptor) -> Path | None:
        module_name = task.module.strip()
        if not module_name or any(
            part in ("", ".", "..") for part in module_name.split(".")
        ):
            return None
        relative = Path(*module_name.split(".")).with_suffix(".py")
        for base in (self.descriptor.working_dir, self.descriptor.root_path):
            candidate = (base / relative).resolve()
            try:
                candidate.relative_to(base.resolve())
            except ValueError:
                continue
            if candidate.is_file():
                return candidate
        return None

    def _relative_source_path(self, path: Path) -> str:
        for base in (self.descriptor.working_dir, self.descriptor.root_path):
            try:
                return path.relative_to(base).as_posix()
            except ValueError:
                continue
        return path.name


class _TaskConfigCollector:
    def __init__(self, module_values: dict[str, Any]) -> None:
        self.module_values = module_values
        self.instance_values: dict[str, Any] = {}
        self.defaults: dict[str, Any] = {}
        self.descriptions: dict[str, str] = {}
        self.config_types: dict[str, dict[str, Any]] = {}
        self.config_groups: dict[str, list[str]] = {}
        self.display_name = ""

    def collect(self, class_node: ast.ClassDef) -> None:
        class_values = dict(self.module_values)
        for statement in class_node.body:
            if isinstance(statement, (ast.Assign, ast.AnnAssign, ast.Expr)):
                self._process_statement(statement, class_values)
            elif isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                local_values = dict(class_values)
                for child in statement.body:
                    if isinstance(child, (ast.Assign, ast.AnnAssign, ast.Expr)):
                        self._process_statement(child, local_values)

    def declarations(self) -> tuple[FieldDeclaration, ...]:
        sections: dict[str, str] = {}
        for section, names in self.config_groups.items():
            for name in names:
                sections.setdefault(name, section)

        declarations: list[FieldDeclaration] = []
        for priority, (path, default) in enumerate(self.defaults.items()):
            config_type = self.config_types.get(path, {})
            raw_choices = config_type.get("options")
            choices = tuple(
                FieldChoice(value=value, label=str(value))
                for value in raw_choices
            ) if isinstance(raw_choices, list) else ()
            declarations.append(
                FieldDeclaration(
                    path=path,
                    label=path,
                    description=self.descriptions.get(path, ""),
                    control=_control_from_config_type(
                        config_type.get("type"),
                        default=default,
                    ),
                    default=default,
                    choices=choices,
                    source=SOURCE_UPSTREAM,
                    confidence=CONFIDENCE_DECLARED,
                    omit_when_unset=True,
                    section=sections.get(path, "项目配置"),
                    priority=priority,
                )
            )
        return tuple(declarations)

    def _process_statement(
        self,
        statement: ast.Assign | ast.AnnAssign | ast.Expr,
        local_values: dict[str, Any],
    ) -> None:
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
            self._process_update_call(statement.value, local_values)
            return

        if isinstance(statement, ast.Assign):
            targets = statement.targets
            value_node = statement.value
        elif isinstance(statement, ast.AnnAssign):
            targets = [statement.target]
            value_node = statement.value
        else:
            return

        value = _literal_value(value_node, local_values, self.instance_values)
        if value is UNSET:
            return
        for target in targets:
            self._assign_target(target, value, local_values)

    def _assign_target(
        self,
        target: ast.AST,
        value: Any,
        local_values: dict[str, Any],
    ) -> None:
        if isinstance(target, ast.Name):
            local_values[target.id] = value
            return
        instance_name = _self_attribute_name(target)
        if instance_name:
            self.instance_values[instance_name] = value
            if instance_name == "name" and isinstance(value, str):
                self.display_name = value.strip()
            elif instance_name == "default_config" and isinstance(value, dict):
                self.defaults = dict(value)
            elif instance_name == "config_description" and isinstance(value, dict):
                self.descriptions = _string_mapping(value)
            elif instance_name == "config_type" and isinstance(value, dict):
                self.config_types = _dict_mapping(value)
            elif instance_name == "default_config_group" and isinstance(value, dict):
                self.config_groups = _string_list_mapping(value)
            return

        collection_name, key = _self_subscript_target(target)
        if not collection_name or not key:
            return
        if collection_name == "default_config":
            self.defaults[key] = value
        elif collection_name == "config_description" and isinstance(value, str):
            self.descriptions[key] = value
        elif collection_name == "config_type" and isinstance(value, dict):
            self.config_types[key] = value

    def _process_update_call(
        self,
        call: ast.Call,
        local_values: dict[str, Any],
    ) -> None:
        if not isinstance(call.func, ast.Attribute) or call.func.attr != "update":
            return
        collection_name = _self_attribute_name(call.func.value)
        if collection_name not in {
            "default_config",
            "config_description",
            "config_type",
            "default_config_group",
        }:
            return
        if not call.args:
            return
        value = _literal_value(call.args[0], local_values, self.instance_values)
        if not isinstance(value, dict):
            return
        if collection_name == "default_config":
            self.defaults.update(value)
        elif collection_name == "config_description":
            self.descriptions.update(_string_mapping(value))
        elif collection_name == "config_type":
            self.config_types.update(_dict_mapping(value))
        else:
            self.config_groups.update(_string_list_mapping(value))


def _parse_task_resource(
    tree: ast.Module,
    *,
    task: OkTaskDescriptor,
    class_name: str,
    source_path: Path,
) -> ConfigResourceDescription | None:
    module_values = _module_literal_values(tree)
    class_node = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == class_name
        ),
        None,
    )
    if class_node is None:
        return None

    collector = _TaskConfigCollector(module_values)
    collector.collect(class_node)
    declarations = collector.declarations()
    selector = task.selector.strip()
    if not selector or not selector.isidentifier():
        return None
    return ConfigResourceDescription(
        filename=f"{selector}.json",
        display_name=collector.display_name or task.label or selector,
        group="项目配置",
        task_index=task.index,
        source_path=source_path,
        fields=declarations,
    )


def _module_literal_values(tree: ast.Module) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for statement in tree.body:
        if isinstance(statement, ast.Assign):
            value = _literal_value(statement.value, values, {})
            if value is UNSET:
                continue
            for target in statement.targets:
                if isinstance(target, ast.Name):
                    values[target.id] = value
        elif isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            value = _literal_value(statement.value, values, {})
            if value is not UNSET:
                values[statement.target.id] = value
    return values


def _literal_value(
    node: ast.AST | None,
    local_values: dict[str, Any],
    instance_values: dict[str, Any],
    *,
    depth: int = 0,
) -> Any:
    if node is None or depth > 12:
        return UNSET
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, (type(None), bool, int, float, str)) else UNSET
    if isinstance(node, ast.Name):
        return local_values.get(node.id, UNSET)
    instance_name = _self_attribute_name(node)
    if instance_name:
        return instance_values.get(instance_name, UNSET)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        values: list[Any] = []
        for child in node.elts:
            value = _literal_value(
                child,
                local_values,
                instance_values,
                depth=depth + 1,
            )
            if value is UNSET:
                continue
            values.append(value)
        return values
    if isinstance(node, ast.Dict):
        result: dict[str, Any] = {}
        for key_node, value_node in zip(node.keys, node.values):
            if key_node is None:
                unpacked = _literal_value(
                    value_node,
                    local_values,
                    instance_values,
                    depth=depth + 1,
                )
                if isinstance(unpacked, dict):
                    result.update(unpacked)
                continue
            key = _literal_value(
                key_node,
                local_values,
                instance_values,
                depth=depth + 1,
            )
            value = _literal_value(
                value_node,
                local_values,
                instance_values,
                depth=depth + 1,
            )
            if isinstance(key, str) and value is not UNSET:
                result[key] = value
        return result
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        value = _literal_value(
            node.operand,
            local_values,
            instance_values,
            depth=depth + 1,
        )
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return -value if isinstance(node.op, ast.USub) else value
        return UNSET
    if isinstance(node, ast.BinOp):
        left = _literal_value(
            node.left,
            local_values,
            instance_values,
            depth=depth + 1,
        )
        right = _literal_value(
            node.right,
            local_values,
            instance_values,
            depth=depth + 1,
        )
        if isinstance(node.op, ast.BitOr) and isinstance(left, dict) and isinstance(right, dict):
            return {**left, **right}
        if isinstance(node.op, ast.Add):
            if isinstance(left, str) and isinstance(right, str):
                return left + right
            if isinstance(left, list) and isinstance(right, list):
                return [*left, *right]
        return UNSET
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id in {"dict", "list", "tuple", "set"} and not node.args:
            if node.func.id == "dict":
                result: dict[str, Any] = {}
                for keyword in node.keywords:
                    value = _literal_value(
                        keyword.value,
                        local_values,
                        instance_values,
                        depth=depth + 1,
                    )
                    if keyword.arg and value is not UNSET:
                        result[keyword.arg] = value
                return result
            return []
    return UNSET


def _self_attribute_name(node: ast.AST) -> str:
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    ):
        return node.attr
    return ""


def _self_subscript_target(node: ast.AST) -> tuple[str, str]:
    if not isinstance(node, ast.Subscript):
        return "", ""
    collection_name = _self_attribute_name(node.value)
    key_node = node.slice
    if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
        return collection_name, key_node.value
    return "", ""


def _string_mapping(value: dict[str, Any]) -> dict[str, str]:
    return {
        str(key): item
        for key, item in value.items()
        if isinstance(key, str) and isinstance(item, str)
    }


def _dict_mapping(value: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(key): dict(item)
        for key, item in value.items()
        if isinstance(key, str) and isinstance(item, dict)
    }


def _string_list_mapping(value: dict[str, Any]) -> dict[str, list[str]]:
    return {
        str(key): [item for item in items if isinstance(item, str)]
        for key, items in value.items()
        if isinstance(key, str) and isinstance(items, list)
    }


def _control_from_config_type(raw_type: Any, *, default: Any) -> str:
    normalized = str(raw_type or "").strip().casefold().replace("-", "_")
    if normalized in {"drop_down", "dropdown", "select"}:
        return CONTROL_MULTISELECT if isinstance(default, list) else CONTROL_SELECT
    if normalized in {"check_box", "checkbox", "switch", "bool", "boolean"}:
        return CONTROL_SWITCH
    if normalized in {"text_area", "textarea", "multiline"}:
        return CONTROL_TEXTAREA
    return ""


def _build_config_fingerprint(
    *,
    descriptor_fingerprint: str,
    source_hashes: list[tuple[str, str]],
    resources: list[ConfigResourceDescription],
) -> str:
    facts = {
        "descriptorFingerprint": descriptor_fingerprint,
        "sources": sorted(source_hashes),
        "resources": [
            {
                "filename": resource.filename,
                "taskIndex": resource.task_index,
                "fields": [
                    {
                        "path": declaration.path,
                        "defaultSet": declaration.default is not UNSET,
                        "default": (
                            declaration.default
                            if declaration.default is not UNSET
                            else None
                        ),
                        "choices": [choice.to_dict() for choice in declaration.choices],
                        "control": declaration.control,
                    }
                    for declaration in resource.fields
                ],
            }
            for resource in resources
        ],
    }
    encoded = json.dumps(
        facts,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
