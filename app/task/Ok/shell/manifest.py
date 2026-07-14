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

"""只读解析 ok-script 衍生项目，生成供 CLI 和未来插件消费的 Manifest。"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


OK_PROJECT_MANIFEST_SCHEMA_VERSION = 1
OK_ADAPTER_API_VERSION = 1

PROTOCOL_FRAMEWORK_CLI = "framework-cli"
PROTOCOL_MAIN_SCRIPT = "main-script"
PROTOCOL_LEGACY_EXE = "legacy-exe"

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


class OkProjectInspectError(ValueError):
    """ok-script 项目无法完成只读解析。"""


@dataclass(frozen=True)
class OkTaskManifest:
    """单个可运行任务的稳定描述。"""

    selector: str
    index: int
    module: str = ""
    class_name: str = ""
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "selector": self.selector,
            "index": self.index,
            "module": self.module,
            "className": self.class_name,
            "label": self.label or self.selector,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OkTaskManifest":
        return cls(
            selector=str(data.get("selector") or ""),
            index=int(data.get("index") or 0),
            module=str(data.get("module") or ""),
            class_name=str(data.get("className") or ""),
            label=str(data.get("label") or ""),
        )


@dataclass(frozen=True)
class OkProjectManifest:
    """项目解析结果；运行器只消费该对象，不重新解释项目字段。"""

    root_path: Path
    working_dir: Path
    resource_name: str
    display_name: str
    project_version: str
    framework_requirement: str
    python_executable: Path | None
    executable: Path | None
    main_script: Path | None
    config_target: str
    config_dir: Path
    log_path: Path
    tasks: tuple[OkTaskManifest, ...]
    protocols: tuple[str, ...]
    default_protocol: str
    fingerprint: str
    schema_version: int = OK_PROJECT_MANIFEST_SCHEMA_VERSION
    adapter_api_version: int = OK_ADAPTER_API_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "adapterApiVersion": self.adapter_api_version,
            "rootPath": str(self.root_path),
            "workingDirectory": str(self.working_dir),
            "resourceName": self.resource_name,
            "displayName": self.display_name,
            "projectVersion": self.project_version,
            "frameworkRequirement": self.framework_requirement,
            "pythonExecutable": (
                str(self.python_executable) if self.python_executable else None
            ),
            "executable": str(self.executable) if self.executable else None,
            "mainScript": str(self.main_script) if self.main_script else None,
            "configTarget": self.config_target,
            "configDirectory": str(self.config_dir),
            "logPath": str(self.log_path),
            "tasks": [task.to_dict() for task in self.tasks],
            "protocols": list(self.protocols),
            "defaultProtocol": self.default_protocol,
            "fingerprint": self.fingerprint,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OkProjectManifest":
        schema_version = int(data.get("schemaVersion") or 0)
        if schema_version != OK_PROJECT_MANIFEST_SCHEMA_VERSION:
            raise OkProjectInspectError(
                f"不支持的 Manifest 版本: {schema_version}"
            )

        root_path = Path(str(data.get("rootPath") or "")).resolve()
        if not root_path.is_dir():
            raise OkProjectInspectError(f"项目目录不存在: {root_path}")

        tasks_data = data.get("tasks")
        tasks = tuple(
            OkTaskManifest.from_dict(item)
            for item in tasks_data
            if isinstance(item, dict)
        ) if isinstance(tasks_data, list) else ()

        protocols_data = data.get("protocols")
        protocols = tuple(
            str(item) for item in protocols_data if isinstance(item, str)
        ) if isinstance(protocols_data, list) else ()

        working_dir = Path(
            str(data.get("workingDirectory") or root_path)
        ).resolve()
        config_dir = Path(
            str(data.get("configDirectory") or working_dir / "configs")
        ).resolve()
        log_path = Path(
            str(data.get("logPath") or working_dir / "logs" / "ok-script.log")
        ).resolve()

        return cls(
            root_path=root_path,
            working_dir=working_dir,
            resource_name=str(data.get("resourceName") or ""),
            display_name=str(data.get("displayName") or ""),
            project_version=str(data.get("projectVersion") or ""),
            framework_requirement=str(data.get("frameworkRequirement") or ""),
            python_executable=_optional_path(data.get("pythonExecutable")),
            executable=_optional_path(data.get("executable")),
            main_script=_optional_path(data.get("mainScript")),
            config_target=str(data.get("configTarget") or "src.config:config"),
            config_dir=config_dir,
            log_path=log_path,
            tasks=tasks,
            protocols=protocols,
            default_protocol=str(data.get("defaultProtocol") or ""),
            fingerprint=str(data.get("fingerprint") or ""),
            schema_version=schema_version,
            adapter_api_version=int(data.get("adapterApiVersion") or 0),
        )


def _optional_path(value: object) -> Path | None:
    text = str(value or "").strip()
    return Path(text) if text else None


def _normalize_resource_name(value: object) -> str:
    text = str(value or "").strip().strip("\"'")
    normalized = _VERSION_SUFFIX_RE.sub("", text).strip()
    return normalized or text


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


def _find_assignment_string(tree: ast.AST, name: str) -> str:
    for node in getattr(tree, "body", []):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) and target.id == name for target in targets):
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value
    return ""


def _find_config_dict(tree: ast.AST) -> ast.Dict | None:
    for node in getattr(tree, "body", []):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) and target.id == "config" for target in targets):
            continue
        if isinstance(node.value, ast.Dict):
            return node.value
    return None


def _dict_value(node: ast.Dict, key_name: str) -> ast.AST | None:
    for key, value in zip(node.keys, node.values):
        if isinstance(key, ast.Constant) and key.value == key_name:
            return value
    return None


def _parse_tasks(config_path: Path | None) -> tuple[OkTaskManifest, ...]:
    if config_path is None:
        return ()
    try:
        tree = ast.parse(_read_text(config_path), filename=str(config_path))
    except SyntaxError:
        return ()

    config_dict = _find_config_dict(tree)
    if config_dict is None:
        return ()
    task_list = _dict_value(config_dict, "onetime_tasks")
    if not isinstance(task_list, (ast.List, ast.Tuple)):
        return ()

    tasks: list[OkTaskManifest] = []
    for index, item in enumerate(task_list.elts, start=1):
        if not isinstance(item, (ast.List, ast.Tuple)) or len(item.elts) < 2:
            continue
        try:
            module_name = ast.literal_eval(item.elts[0])
            class_name = ast.literal_eval(item.elts[1])
        except (ValueError, TypeError):
            continue
        if not isinstance(module_name, str) or not isinstance(class_name, str):
            continue
        tasks.append(
            OkTaskManifest(
                selector=class_name,
                index=index,
                module=module_name,
                class_name=class_name,
                label=class_name,
            )
        )
    return tuple(tasks)


def _read_framework_requirement(root_path: Path) -> tuple[str, Path | None]:
    candidates = (
        root_path / "requirements.txt",
        root_path / "requirements.in",
        root_path / "working" / "requirements.txt",
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


def _discover_python(root_path: Path, resource_name: str) -> Path | None:
    candidates = (
        root_path / ".venv" / "Scripts" / "python.exe",
        root_path / "venv" / "Scripts" / "python.exe",
        root_path / "python" / "python.exe",
        root_path / "data" / "apps" / resource_name / "python" / "python.exe",
    )
    return _first_existing(candidates)


def _discover_executable(
    root_path: Path,
    resource_name: str,
    app_data: dict[str, Any],
) -> Path | None:
    configured = str(app_data.get("executable") or app_data.get("exe") or "").strip()
    candidates = []
    if configured:
        candidates.append(root_path / configured)
    candidates.extend(
        (
            root_path / f"{resource_name}.exe",
            root_path / "ok-script.exe",
        )
    )
    return _first_existing(candidates)


def _discover_main_script(root_path: Path, yaml_data: dict[str, list[str]]) -> Path | None:
    candidates = [root_path / value for value in yaml_data.get("main_script", [])]
    candidates.append(root_path / "main.py")
    return _first_existing(candidates)


def _discover_config_source(root_path: Path, resource_name: str) -> Path | None:
    return _first_existing(
        (
            root_path / "src" / "config.py",
            root_path / "working" / "src" / "config.py",
            root_path
            / "data"
            / "apps"
            / resource_name
            / "working"
            / "src"
            / "config.py",
        )
    )


def _discover_working_dir(root_path: Path, resource_name: str) -> Path:
    found = _first_existing_dir(
        (
            root_path / "data" / "apps" / resource_name / "working",
            root_path / "working",
        )
    )
    return found or root_path


def _discover_config_dir(root_path: Path, working_dir: Path) -> Path:
    found = _first_existing_dir(
        (
            working_dir / "configs",
            root_path / "configs",
        )
    )
    return found or (working_dir / "configs").resolve()


def _discover_log_path(root_path: Path, working_dir: Path) -> Path:
    candidates = (
        working_dir / "logs" / "ok-script.log",
        root_path / "logs" / "ok-script.log",
    )
    return (_first_existing(candidates) or candidates[0].resolve())


def _build_fingerprint(paths: Iterable[Path], executable: Path | None) -> str:
    digest = hashlib.sha256()
    for path in sorted({item.resolve() for item in paths if item.is_file()}):
        digest.update(str(path).casefold().encode("utf-8"))
        try:
            digest.update(path.read_bytes())
        except OSError:
            continue
    if executable is not None and executable.is_file():
        stat = executable.stat()
        digest.update(str(executable).casefold().encode("utf-8"))
        digest.update(f"{stat.st_size}:{stat.st_mtime_ns}".encode("ascii"))
    return digest.hexdigest()


def inspect_ok_project(
    root_path: str | Path,
    *,
    python_executable: str | Path | None = None,
) -> OkProjectManifest:
    """静态解析 ok-script 项目，不导入项目模块或启动进程。"""

    root = Path(root_path).resolve()
    if not root.is_dir():
        raise OkProjectInspectError(f"项目目录不存在: {root}")

    pyappify_path = root / "pyappify.yml"
    if not pyappify_path.is_file():
        alternate = root / "pyappify.yaml"
        pyappify_path = alternate if alternate.is_file() else pyappify_path
    yaml_data = _read_simple_yaml(pyappify_path)

    raw_name = next(iter(yaml_data.get("name", [])), "")
    resource_name = _normalize_resource_name(raw_name)
    if not resource_name:
        exe_files = sorted(root.glob("ok-*.exe"))
        if exe_files:
            resource_name = exe_files[0].stem
        else:
            resource_name = _normalize_resource_name(root.name)
    if not resource_name:
        raise OkProjectInspectError("无法识别 ok-script 项目资源名")

    app_json_candidates = (
        root / "app.json",
        root / "data" / "apps" / resource_name / "app.json",
    )
    app_json_path = _first_existing(app_json_candidates)
    app_data = _read_json_object(app_json_path) if app_json_path else {}

    configured_name = app_data.get("name") or app_data.get("resourceName")
    if configured_name:
        resource_name = _normalize_resource_name(configured_name)

    config_source = _discover_config_source(root, resource_name)
    tasks = _parse_tasks(config_source)
    framework_requirement, requirement_path = _read_framework_requirement(root)
    main_script = _discover_main_script(root, yaml_data)
    executable = _discover_executable(root, resource_name, app_data)
    working_dir = _discover_working_dir(root, resource_name)
    config_dir = _discover_config_dir(root, working_dir)
    log_path = _discover_log_path(root, working_dir)

    project_version = str(
        app_data.get("version")
        or app_data.get("appVersion")
        or next(iter(yaml_data.get("version", [])), "")
    ).strip()
    if not project_version and config_source is not None:
        try:
            project_version = _find_assignment_string(
                ast.parse(_read_text(config_source), filename=str(config_source)),
                "version",
            )
        except SyntaxError:
            project_version = ""

    selected_python = (
        Path(python_executable).resolve()
        if python_executable
        else _discover_python(root, resource_name)
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
    if not protocols:
        protocols.append(PROTOCOL_FRAMEWORK_CLI)

    fingerprint_paths = [pyappify_path]
    if app_json_path is not None:
        fingerprint_paths.append(app_json_path)
    if config_source is not None:
        fingerprint_paths.append(config_source)
    if requirement_path is not None:
        fingerprint_paths.append(requirement_path)

    display_name = str(
        app_data.get("displayName")
        or app_data.get("title")
        or raw_name
        or resource_name
    ).strip()

    return OkProjectManifest(
        root_path=root,
        working_dir=working_dir,
        resource_name=resource_name,
        display_name=display_name,
        project_version=project_version,
        framework_requirement=framework_requirement,
        python_executable=selected_python,
        executable=executable,
        main_script=main_script,
        config_target="src.config:config",
        config_dir=config_dir,
        log_path=log_path,
        tasks=tasks,
        protocols=tuple(protocols),
        default_protocol=protocols[0],
        fingerprint=_build_fingerprint(fingerprint_paths, executable),
    )


def save_manifest(manifest: OkProjectManifest, path: Path) -> None:
    """原子保存 Manifest。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    temp_path.write_text(
        json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(path)


def load_manifest(path: Path) -> OkProjectManifest:
    """从 JSON 文件读取 Manifest。"""

    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OkProjectInspectError(f"Manifest 读取失败: {exc}") from exc
    if not isinstance(data, dict):
        raise OkProjectInspectError("Manifest 顶层必须是对象")
    return OkProjectManifest.from_dict(data)
