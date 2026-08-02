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
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""只读解析 ok-script 项目资源，不导入或执行上游模块。"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .descriptor import (
    PROTOCOL_FRAMEWORK_CLI,
    PROTOCOL_LEGACY_EXE,
    PROTOCOL_MAIN_SCRIPT,
    OkProjectCapabilities,
    OkProjectCapability,
    OkProjectDescriptor,
    OkProjectDiagnostic,
    OkProjectInspectError,
    OkProjectMetadataSource,
    OkTaskDescriptor,
)


_VERSION_SUFFIX_RE = re.compile(
    r"[-_ ]?v?\d+(?:\.\d+)+(?:[-_.a-z0-9]*)?$",
    re.IGNORECASE,
)
_REQUIREMENT_RE = re.compile(
    r"^\s*ok[-_]script\s*(?P<specifier>(?:===|==|~=|!=|<=|>=|<|>).+)?$",
    re.IGNORECASE,
)
_SIMPLE_YAML_VALUE_RE = re.compile(
    r"^\s*(?P<key>[A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(?P<value>.*?)\s*$"
)


@dataclass(frozen=True, slots=True)
class _ParsedConfig:
    parsed: bool
    config_folder: str
    log_file: str
    gui_title: str
    version: str
    tasks: tuple[OkTaskDescriptor, ...]


class ProjectParser:
    """从源码态或安装态目录生成版本化项目 descriptor。"""

    def __init__(
        self,
        root_path: str | Path,
        *,
        python_executable: str | Path | None = None,
    ) -> None:
        self.root_path = Path(root_path).expanduser().resolve()
        self.python_executable = (
            Path(python_executable).expanduser().resolve()
            if python_executable
            else None
        )

    def parse(self) -> OkProjectDescriptor:
        """解析项目事实并返回无运行副作用的 descriptor。"""

        root = self.root_path
        if not root.is_dir():
            raise OkProjectInspectError(f"项目目录不存在: {root}")

        diagnostics: list[OkProjectDiagnostic] = []
        metadata_sources: list[OkProjectMetadataSource] = []

        pyappify_path = _first_existing(
            (root / "pyappify.yml", root / "pyappify.yaml")
        )
        yaml_data = _read_simple_yaml(pyappify_path) if pyappify_path else {}
        if pyappify_path is not None:
            metadata_sources.append(
                OkProjectMetadataSource(
                    kind="pyappify",
                    path=pyappify_path,
                    fields=tuple(
                        key
                        for key in ("name", "version", "main_script")
                        if key in yaml_data
                    ),
                )
            )

        raw_yaml_name = next(iter(yaml_data.get("name", [])), "")
        yaml_resource_name = _normalize_resource_name(raw_yaml_name)
        app_json_path, app_data = _discover_app_json(
            root,
            yaml_resource_name,
            diagnostics,
        )
        if app_json_path is not None:
            metadata_sources.append(
                OkProjectMetadataSource(
                    kind="app-json",
                    path=app_json_path,
                    fields=tuple(
                        key
                        for key in (
                            "name",
                            "resourceName",
                            "displayName",
                            "title",
                            "version",
                            "appVersion",
                            "executable",
                            "exe",
                        )
                        if key in app_data
                    ),
                )
            )

        app_resource_name = _normalize_resource_name(
            app_data.get("name") or app_data.get("resourceName")
        )
        if (
            yaml_resource_name
            and app_resource_name
            and yaml_resource_name != app_resource_name
        ):
            diagnostics.append(
                OkProjectDiagnostic(
                    code="IDENTITY_SOURCE_MISMATCH",
                    level="warning",
                    message=(
                        "pyappify 与 app.json 的项目资源名不一致，"
                        "已优先采用 pyappify"
                    ),
                    path=str(app_json_path or ""),
                )
            )

        resource_name = yaml_resource_name or app_resource_name
        if not resource_name:
            exe_files = sorted(root.glob("ok-*.exe"))
            resource_name = (
                _normalize_resource_name(exe_files[0].stem)
                if exe_files
                else _normalize_resource_name(root.name)
            )
        if not resource_name:
            raise OkProjectInspectError("无法识别 ok-script 项目资源名")

        app_root = app_json_path.parent if app_json_path is not None else root
        runtime_working_dir = _discover_runtime_working_dir(
            root,
            app_root,
            resource_name,
        )
        config_source, config_working_dir, config_candidates = _discover_config_source(
            root=root,
            app_root=app_root,
            runtime_working_dir=runtime_working_dir,
            prefer_installed=app_json_path is not None and pyappify_path is None,
        )
        if len(config_candidates) > 1:
            diagnostics.append(
                OkProjectDiagnostic(
                    code="CONFIG_SOURCE_AMBIGUOUS",
                    level="warning",
                    message=(
                        f"发现 {len(config_candidates)} 个 config.py，"
                        "已按源码态/安装态优先级选择第一个"
                    ),
                    path=str(config_source or ""),
                )
            )

        parsed_config = _parse_config(config_source, diagnostics)
        if config_source is not None:
            metadata_sources.append(
                OkProjectMetadataSource(
                    kind="config-python",
                    path=config_source,
                    fields=tuple(
                        name
                        for name, value in (
                            ("version", parsed_config.version),
                            ("config_folder", parsed_config.config_folder),
                            ("log_file", parsed_config.log_file),
                            ("gui_title", parsed_config.gui_title),
                            ("onetime_tasks", parsed_config.tasks),
                        )
                        if value
                    ),
                )
            )
        else:
            diagnostics.append(
                OkProjectDiagnostic(
                    code="CONFIG_SOURCE_MISSING",
                    level="warning",
                    message="未找到根目录、src、working 或 repo 中的 config.py",
                    path=str(root),
                )
            )

        working_dir = config_working_dir or runtime_working_dir
        config_target = _config_target(config_source, working_dir)
        config_folder = _safe_relative_folder(
            parsed_config.config_folder or "configs",
            diagnostics,
            config_source,
        )
        config_dir = _discover_config_dir(
            config_folder=config_folder,
            working_dir=working_dir,
            runtime_working_dir=runtime_working_dir,
            root_path=root,
        )
        if not config_dir.is_dir():
            diagnostics.append(
                OkProjectDiagnostic(
                    code="CONFIG_DIRECTORY_MISSING",
                    level="warning",
                    message="项目配置目录尚未生成",
                    path=str(config_dir),
                )
            )

        log_path = _discover_log_path(
            log_file=parsed_config.log_file,
            working_dir=working_dir,
            runtime_working_dir=runtime_working_dir,
            root_path=root,
            diagnostics=diagnostics,
        )
        framework_requirement, requirement_path = _read_framework_requirement(
            root,
            runtime_working_dir,
            app_root,
        )
        if requirement_path is not None:
            metadata_sources.append(
                OkProjectMetadataSource(
                    kind="requirements",
                    path=requirement_path,
                    fields=("frameworkRequirement",),
                )
            )

        main_script = _discover_main_script(
            root,
            app_root,
            working_dir,
            yaml_data,
        )
        if main_script is not None:
            metadata_sources.append(
                OkProjectMetadataSource(
                    kind="main-script",
                    path=main_script,
                )
            )

        executable = _discover_executable(
            root,
            app_root,
            resource_name,
            app_data,
        )
        selected_python = self.python_executable or _discover_python(
            root,
            app_root,
            resource_name,
        )
        if selected_python is None and main_script is not None:
            selected_python = Path(sys.executable).resolve()

        protocols: list[str] = []
        if selected_python is not None:
            protocols.append(PROTOCOL_FRAMEWORK_CLI)
        if main_script is not None and selected_python is not None:
            protocols.append(PROTOCOL_MAIN_SCRIPT)
        if executable is not None:
            protocols.append(PROTOCOL_LEGACY_EXE)

        if parsed_config.tasks:
            task_capability = OkProjectCapability(
                available=True,
                verified=True,
                source="config.py:onetime_tasks",
            )
        else:
            task_capability = OkProjectCapability(
                available=False,
                verified=False,
                reason="未从项目配置中解析到一次性任务",
            )
            diagnostics.append(
                OkProjectDiagnostic(
                    code="TASKS_NOT_DISCOVERED",
                    level="warning",
                    message="未从 config.py 的 onetime_tasks 解析到任务",
                    path=str(config_source or root),
                )
            )

        if protocols:
            diagnostics.append(
                OkProjectDiagnostic(
                    code="RUNTIME_UNVERIFIED",
                    level="info",
                    message="已发现运行协议候选，真实运行能力仍需 provider 验证",
                )
            )
        else:
            diagnostics.append(
                OkProjectDiagnostic(
                    code="RUNTIME_PROTOCOL_MISSING",
                    level="warning",
                    message="未发现 Python、main.py 或项目可执行文件运行候选",
                )
            )

        config_available = config_source is not None and parsed_config.parsed
        capabilities = OkProjectCapabilities(
            config=OkProjectCapability(
                available=config_available or config_dir.is_dir(),
                verified=config_available or config_dir.is_dir(),
                source=(
                    "config.py"
                    if config_available
                    else "json-directory"
                    if config_dir.is_dir()
                    else ""
                ),
                reason=(
                    ""
                    if config_available or config_dir.is_dir()
                    else "未找到可解析配置源码或 JSON 配置目录"
                ),
            ),
            task=task_capability,
            game_path=OkProjectCapability(
                available=False,
                verified=False,
                reason="游戏路径角色需要 provider 明确声明",
            ),
            events=OkProjectCapability(
                available=False,
                verified=False,
                reason="结构化事件能力需要上游或 provider 明确声明",
            ),
            runtime=OkProjectCapability(
                available=bool(protocols),
                verified=False,
                source=",".join(protocols),
                reason=(
                    "仅探测到运行协议候选，尚未经过 provider 或真实运行验证"
                    if protocols
                    else "未探测到可用运行协议候选"
                ),
            ),
        )

        if not any(
            (
                pyappify_path is not None,
                app_json_path is not None,
                config_source is not None,
                main_script is not None,
                executable is not None,
            )
        ):
            raise OkProjectInspectError(
                "目录缺少 pyappify.yml、app.json、config.py、main.py 或可执行文件，"
                "不是可识别的 ok-script 项目"
            )

        yaml_version = next(iter(yaml_data.get("version", [])), "")
        project_version = str(
            app_data.get("version")
            or app_data.get("appVersion")
            or yaml_version
            or parsed_config.version
        ).strip()
        gui_title = parsed_config.gui_title
        display_name = str(
            app_data.get("displayName")
            or app_data.get("title")
            or gui_title
            or raw_yaml_name
            or resource_name
        ).strip()

        fingerprint = _build_fingerprint(
            root_path=root,
            metadata_sources=metadata_sources,
            executable=executable,
            resource_name=resource_name,
            config_target=config_target,
            config_folder=config_folder,
            tasks=parsed_config.tasks,
            protocols=tuple(protocols),
        )

        return OkProjectDescriptor(
            root_path=root,
            working_dir=working_dir,
            resource_name=resource_name,
            display_name=display_name,
            project_version=project_version,
            framework_requirement=framework_requirement,
            python_executable=selected_python,
            executable=executable,
            main_script=main_script,
            config_source=config_source,
            config_target=config_target,
            config_folder=config_folder,
            config_dir=config_dir,
            log_path=log_path,
            gui_title=gui_title,
            tasks=parsed_config.tasks,
            protocols=tuple(protocols),
            default_protocol=protocols[0] if protocols else "",
            metadata_sources=tuple(metadata_sources),
            capabilities=capabilities,
            diagnostics=tuple(diagnostics),
            fingerprint=fingerprint,
        )


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return ""


def _read_simple_yaml(path: Path) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for raw_line in _read_text(path).splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        match = _SIMPLE_YAML_VALUE_RE.match(line)
        if match is None:
            continue
        key = match.group("key")
        value = match.group("value").strip().strip("\"'")
        if value:
            values.setdefault(key, []).append(value)
    return values


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _first_existing(paths: Iterable[Path]) -> Path | None:
    for path in paths:
        if path.is_file():
            return path.resolve()
    return None


def _first_existing_dir(paths: Iterable[Path]) -> Path | None:
    for path in paths:
        if path.is_dir():
            return path.resolve()
    return None


def _normalize_resource_name(value: object) -> str:
    text = str(value or "").strip().strip("\"'")
    normalized = _VERSION_SUFFIX_RE.sub("", text).strip()
    return normalized or text


def _discover_app_json(
    root_path: Path,
    resource_hint: str,
    diagnostics: list[OkProjectDiagnostic],
) -> tuple[Path | None, dict[str, Any]]:
    candidates: list[Path] = [root_path / "app.json"]
    apps_root = root_path / "data" / "apps"
    if resource_hint:
        candidates.append(apps_root / resource_hint / "app.json")
    if apps_root.is_dir():
        candidates.extend(sorted(apps_root.glob("*/app.json")))

    existing: list[tuple[Path, dict[str, Any]]] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen or not resolved.is_file():
            continue
        seen.add(resolved)
        existing.append((resolved, _read_json_object(resolved)))

    if not existing:
        return None, {}
    if resource_hint:
        for path, data in existing:
            name = _normalize_resource_name(
                data.get("name") or data.get("resourceName")
            )
            if name == resource_hint:
                return path, data
    if len(existing) > 1:
        diagnostics.append(
            OkProjectDiagnostic(
                code="APP_METADATA_AMBIGUOUS",
                level="warning",
                message="发现多个 app.json，已按固定候选顺序选择第一个",
                path=str(existing[0][0]),
            )
        )
    return existing[0]


def _discover_runtime_working_dir(
    root_path: Path,
    app_root: Path,
    resource_name: str,
) -> Path:
    found = _first_existing_dir(
        (
            app_root / "working",
            root_path / "data" / "apps" / resource_name / "working",
            root_path / "working",
        )
    )
    return found or root_path


def _discover_config_source(
    *,
    root: Path,
    app_root: Path,
    runtime_working_dir: Path,
    prefer_installed: bool,
) -> tuple[Path | None, Path | None, tuple[Path, ...]]:
    source_bases = (root, runtime_working_dir, root / "repo", app_root / "repo")
    installed_bases = (
        runtime_working_dir,
        app_root / "repo",
        root / "repo",
        root,
    )
    bases = installed_bases if prefer_installed else source_bases

    candidates: list[tuple[Path, Path]] = []
    seen: set[Path] = set()
    for base in bases:
        for relative in (Path("config.py"), Path("src") / "config.py"):
            candidate = (base / relative).resolve()
            if candidate in seen or not candidate.is_file():
                continue
            seen.add(candidate)
            candidates.append((candidate, base.resolve()))

    if not candidates:
        return None, None, ()
    selected_path, selected_base = candidates[0]
    return selected_path, selected_base, tuple(path for path, _ in candidates)


def _parse_config(
    config_path: Path | None,
    diagnostics: list[OkProjectDiagnostic],
) -> _ParsedConfig:
    if config_path is None:
        return _ParsedConfig(False, "", "", "", "", ())
    try:
        tree = ast.parse(_read_text(config_path), filename=str(config_path))
    except SyntaxError as exc:
        diagnostics.append(
            OkProjectDiagnostic(
                code="CONFIG_PARSE_ERROR",
                level="error",
                message=f"config.py 语法解析失败: {exc.msg}",
                path=str(config_path),
            )
        )
        return _ParsedConfig(False, "", "", "", "", ())

    assignments = _top_level_assignments(tree)
    config_dict = _resolve_node(assignments.get("config"), assignments)
    if not isinstance(config_dict, ast.Dict):
        diagnostics.append(
            OkProjectDiagnostic(
                code="CONFIG_OBJECT_MISSING",
                level="warning",
                message="config.py 未声明可静态解析的 config 字典",
                path=str(config_path),
            )
        )
        return _ParsedConfig(
            False,
            "",
            "",
            "",
            _string_value(assignments.get("version"), assignments),
            (),
        )

    config_folder = _string_value(
        _dict_value(config_dict, "config_folder"),
        assignments,
    )
    log_file = _string_value(_dict_value(config_dict, "log_file"), assignments)
    gui_title = _string_value(_dict_value(config_dict, "gui_title"), assignments)
    version = (
        _string_value(assignments.get("version"), assignments)
        or _string_value(_dict_value(config_dict, "version"), assignments)
    )
    task_node = _resolve_node(
        _dict_value(config_dict, "onetime_tasks"),
        assignments,
    )
    tasks = _parse_tasks(task_node, assignments)
    return _ParsedConfig(
        parsed=True,
        config_folder=config_folder,
        log_file=log_file,
        gui_title=gui_title,
        version=version,
        tasks=tasks,
    )


def _top_level_assignments(tree: ast.Module) -> dict[str, ast.AST]:
    assignments: dict[str, ast.AST] = {}
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                assignments[target.id] = node.value
    return assignments


def _resolve_node(
    node: ast.AST | None,
    assignments: dict[str, ast.AST],
    *,
    depth: int = 0,
) -> ast.AST | None:
    if isinstance(node, ast.Name) and depth < 8:
        target = assignments.get(node.id)
        if target is not None and target is not node:
            return _resolve_node(target, assignments, depth=depth + 1)
    return node


def _dict_value(node: ast.Dict, key_name: str) -> ast.AST | None:
    for key, value in zip(node.keys, node.values):
        if isinstance(key, ast.Constant) and key.value == key_name:
            return value
    return None


def _string_value(
    node: ast.AST | None,
    assignments: dict[str, ast.AST],
) -> str:
    resolved = _resolve_node(node, assignments)
    if isinstance(resolved, ast.Constant) and isinstance(resolved.value, str):
        return resolved.value.strip()
    return ""


def _dotted_name(
    node: ast.AST,
    assignments: dict[str, ast.AST],
) -> str:
    resolved = _resolve_node(node, assignments)
    if isinstance(resolved, ast.Constant) and isinstance(resolved.value, str):
        return resolved.value.strip()
    if isinstance(resolved, ast.Name):
        return resolved.id
    if isinstance(resolved, ast.Attribute):
        parent = _dotted_name(resolved.value, assignments)
        return f"{parent}.{resolved.attr}" if parent else resolved.attr
    return ""


def _parse_tasks(
    task_node: ast.AST | None,
    assignments: dict[str, ast.AST],
) -> tuple[OkTaskDescriptor, ...]:
    if not isinstance(task_node, (ast.List, ast.Tuple)):
        return ()

    tasks: list[OkTaskDescriptor] = []
    for index, item in enumerate(task_node.elts, start=1):
        resolved_item = _resolve_node(item, assignments)
        if not isinstance(resolved_item, (ast.List, ast.Tuple)):
            continue
        if len(resolved_item.elts) < 2:
            continue
        module_name = _dotted_name(resolved_item.elts[0], assignments)
        class_name = _dotted_name(resolved_item.elts[1], assignments)
        if not class_name:
            continue
        selector = class_name.rsplit(".", 1)[-1]
        label = (
            _string_value(resolved_item.elts[2], assignments)
            if len(resolved_item.elts) >= 3
            else ""
        )
        tasks.append(
            OkTaskDescriptor(
                selector=selector,
                index=index,
                module=module_name,
                class_name=class_name,
                label=label or selector,
            )
        )
    return tuple(tasks)


def _config_target(config_source: Path | None, working_dir: Path) -> str:
    if config_source is None:
        return "src.config:config"
    try:
        relative = config_source.relative_to(working_dir)
    except ValueError:
        relative = Path(config_source.name)
    module = ".".join(relative.with_suffix("").parts)
    return f"{module}:config"


def _safe_relative_folder(
    value: str,
    diagnostics: list[OkProjectDiagnostic],
    config_source: Path | None,
) -> str:
    normalized = value.strip().replace("\\", "/") or "configs"
    path = Path(normalized)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        diagnostics.append(
            OkProjectDiagnostic(
                code="CONFIG_FOLDER_UNSAFE",
                level="error",
                message="config_folder 必须是项目 working directory 内的相对路径",
                path=str(config_source or ""),
            )
        )
        return "configs"
    return path.as_posix()


def _discover_config_dir(
    *,
    config_folder: str,
    working_dir: Path,
    runtime_working_dir: Path,
    root_path: Path,
) -> Path:
    relative = Path(config_folder)
    candidates = (
        working_dir / relative,
        runtime_working_dir / relative,
        root_path / relative,
    )
    return _first_existing_dir(candidates) or candidates[0].resolve()


def _discover_log_path(
    *,
    log_file: str,
    working_dir: Path,
    runtime_working_dir: Path,
    root_path: Path,
    diagnostics: list[OkProjectDiagnostic],
) -> Path:
    normalized = log_file.strip().replace("\\", "/")
    relative = Path(normalized or "logs/ok-script.log")
    if relative.is_absolute() or any(part in ("", ".", "..") for part in relative.parts):
        diagnostics.append(
            OkProjectDiagnostic(
                code="LOG_PATH_UNSAFE",
                level="warning",
                message="log_file 必须是项目 working directory 内的相对路径",
            )
        )
        relative = Path("logs") / "ok-script.log"
    candidates = (
        working_dir / relative,
        runtime_working_dir / relative,
        root_path / relative,
    )
    return _first_existing(candidates) or candidates[0].resolve()


def _read_framework_requirement(
    root_path: Path,
    working_dir: Path,
    app_root: Path,
) -> tuple[str, Path | None]:
    candidates = (
        root_path / "requirements.txt",
        root_path / "requirements.in",
        working_dir / "requirements.txt",
        app_root / "requirements.txt",
        app_root / "repo" / "requirements.txt",
    )
    for path in candidates:
        if not path.is_file():
            continue
        for raw_line in _read_text(path).splitlines():
            line = raw_line.split("#", 1)[0].strip()
            match = _REQUIREMENT_RE.match(line)
            if match is not None:
                return (match.group("specifier") or "").strip(), path.resolve()
    return "", None


def _discover_python(
    root_path: Path,
    app_root: Path,
    resource_name: str,
) -> Path | None:
    return _first_existing(
        (
            root_path / ".venv" / "Scripts" / "python.exe",
            root_path / "venv" / "Scripts" / "python.exe",
            root_path / "python" / "python.exe",
            app_root / "python" / "python.exe",
            root_path / "data" / "apps" / resource_name / "python" / "python.exe",
        )
    )


def _discover_executable(
    root_path: Path,
    app_root: Path,
    resource_name: str,
    app_data: dict[str, Any],
) -> Path | None:
    configured = str(
        app_data.get("executable") or app_data.get("exe") or ""
    ).strip()
    candidates: list[Path] = []
    if configured:
        configured_path = Path(configured)
        if not configured_path.is_absolute() and ".." not in configured_path.parts:
            candidates.extend(
                (root_path / configured_path, app_root / configured_path)
            )
    candidates.extend(
        (
            root_path / f"{resource_name}.exe",
            app_root / f"{resource_name}.exe",
            root_path / "ok-script.exe",
            app_root / "ok-script.exe",
        )
    )
    return _first_existing(candidates)


def _discover_main_script(
    root_path: Path,
    app_root: Path,
    working_dir: Path,
    yaml_data: dict[str, list[str]],
) -> Path | None:
    candidates: list[Path] = []
    for value in yaml_data.get("main_script", []):
        relative = Path(value)
        if relative.is_absolute() or ".." in relative.parts:
            continue
        candidates.append(root_path / relative)
    candidates.extend(
        (
            root_path / "main.py",
            working_dir / "main.py",
            root_path / "repo" / "main.py",
            app_root / "repo" / "main.py",
        )
    )
    return _first_existing(candidates)


def _build_fingerprint(
    *,
    root_path: Path,
    metadata_sources: list[OkProjectMetadataSource],
    executable: Path | None,
    resource_name: str,
    config_target: str,
    config_folder: str,
    tasks: tuple[OkTaskDescriptor, ...],
    protocols: tuple[str, ...],
) -> str:
    digest = hashlib.sha256()
    digest.update(b"ok-project-descriptor-v2\0")
    for source in sorted(
        metadata_sources,
        key=lambda item: (item.kind, str(item.path).casefold()),
    ):
        try:
            relative = source.path.relative_to(root_path).as_posix()
        except ValueError:
            relative = source.path.name
        digest.update(f"{source.kind}:{relative}\0".encode("utf-8"))
        try:
            digest.update(source.path.read_bytes())
        except OSError:
            continue

    if executable is not None and executable.is_file():
        try:
            relative_executable = executable.relative_to(root_path).as_posix()
        except ValueError:
            relative_executable = executable.name
        try:
            stat = executable.stat()
            digest.update(relative_executable.encode("utf-8"))
            digest.update(f"{stat.st_size}:{stat.st_mtime_ns}".encode("ascii"))
        except OSError:
            pass

    facts = {
        "resourceName": resource_name,
        "configTarget": config_target,
        "configFolder": config_folder,
        "tasks": [task.to_dict() for task in tasks],
        "protocols": list(protocols),
    }
    digest.update(
        json.dumps(facts, ensure_ascii=False, sort_keys=True).encode("utf-8")
    )
    return digest.hexdigest()
