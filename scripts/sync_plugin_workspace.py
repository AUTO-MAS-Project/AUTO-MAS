#!/usr/bin/env python3
"""Synchronize local AUTO-MAS plugins with the root uv workspace."""

from __future__ import annotations

import argparse
import sys
import tomllib
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


ENTRY_POINT_GROUPS = ("auto_mas.plugins", "automas.plugins")
ROOT_SDK_NAME = "uv (AUTO-MAS)"
ROOT_SDK_TYPE = "Python SDK"
ROOT_MODULE_NAME = "auto-mas"
CORE_PLUGIN_MODULE_NAME = "auto-mas-core"
WORKSPACE_EXCLUDES = {"pypi", "_generated"}


@dataclass(frozen=True)
class PluginProject:
    path: Path
    member: str
    distribution: str
    entry_points: tuple[str, ...]


def _load_toml(path: Path) -> dict:
    with path.open("rb") as file:
        data = tomllib.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"TOML root must be a table: {path}")
    return data


def _entry_points(project: dict) -> tuple[str, ...]:
    entry_points = project.get("entry-points", {})
    if not isinstance(entry_points, dict):
        return ()

    result: list[str] = []
    for group in ENTRY_POINT_GROUPS:
        group_table = entry_points.get(group)
        if not isinstance(group_table, dict):
            continue
        result.extend(str(name).strip() for name in group_table if str(name).strip())
    return tuple(sorted(set(result)))


def discover_plugin_projects(workspace: Path) -> list[PluginProject]:
    plugins_dir = workspace / "plugins"
    if not plugins_dir.exists():
        return []

    projects: list[PluginProject] = []
    for item in sorted(plugins_dir.iterdir(), key=lambda path: path.name):
        if not item.is_dir() or item.name in WORKSPACE_EXCLUDES or item.name.startswith("_"):
            continue
        pyproject = item / "pyproject.toml"
        if not pyproject.exists():
            continue

        data = _load_toml(pyproject)
        project = data.get("project", {})
        if not isinstance(project, dict):
            continue

        distribution = str(project.get("name") or item.name).strip()
        if not distribution:
            continue

        entry_points = _entry_points(project)

        projects.append(
            PluginProject(
                path=item,
                member=item.relative_to(workspace).as_posix(),
                distribution=distribution,
                entry_points=entry_points,
            )
        )
    return projects


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_dependency_groups(projects: list[PluginProject]) -> str:
    distributions = sorted(project.distribution for project in projects)
    lines = ["[dependency-groups]", "dev = [", '    "auto-mas-core",', "]", "plugins = ["]
    for distribution in distributions:
        lines.append(f"    {_quote(distribution)},")
    lines.append("]")
    return "\n".join(lines) + "\n"


def render_workspace(projects: list[PluginProject]) -> str:
    lines = ["[tool.uv.workspace]", "members = ["]
    for project in sorted(projects, key=lambda item: item.member):
        lines.append(f"    {_quote(project.member)},")
    lines.extend(["]", "exclude = [", '    "plugins/pypi",', '    "plugins/_generated",', "]"])
    return "\n".join(lines) + "\n"


def render_sources(projects: list[PluginProject]) -> str:
    lines = ["[tool.uv.sources]"]
    for distribution in sorted(project.distribution for project in projects):
        lines.append(f"{_quote(distribution)} = {{ workspace = true }}")
    return "\n".join(lines) + "\n"


def _is_header(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("[") and stripped.endswith("]") and not stripped.startswith("[[")


def replace_table(text: str, header: str, replacement: str) -> str:
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.strip() == header:
            start = index
            break

    if start is None:
        text = text.rstrip() + "\n\n" + replacement.rstrip() + "\n"
        return text

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if _is_header(lines[index]):
            end = index
            break

    replacement_lines = replacement.rstrip().splitlines()
    if end < len(lines) and replacement_lines and lines[end].strip():
        replacement_lines.append("")
    new_lines = lines[:start] + replacement_lines + lines[end:]
    return "\n".join(new_lines).rstrip() + "\n"


def render_root_pyproject(current: str, projects: list[PluginProject]) -> str:
    updated = replace_table(current, "[dependency-groups]", render_dependency_groups(projects))
    updated = replace_table(updated, "[tool.uv.workspace]", render_workspace(projects))
    updated = replace_table(updated, "[tool.uv.sources]", render_sources(projects))
    return updated


def _module_file_name(distribution: str) -> str:
    return distribution.replace("-", "_") + ".iml"


def _create_pycharm_module_tree(project: PluginProject) -> ET.ElementTree:
    root = ET.Element(
        "module",
        {
            "external.system.id": "pyproject.toml",
            "type": "PYTHON_MODULE",
            "version": "4",
        },
    )
    manager = ET.SubElement(root, "component", {"name": "NewModuleRootManager"})
    content = ET.SubElement(manager, "content", {"url": f"file://$MODULE_DIR$/{project.member}"})
    if (project.path / "src").exists():
        ET.SubElement(
            content,
            "sourceFolder",
            {"url": f"file://$MODULE_DIR$/{project.member}/src", "isTestSource": "false"},
        )
    if (project.path / ".venv").exists():
        ET.SubElement(content, "excludeFolder", {"url": f"file://$MODULE_DIR$/{project.member}/.venv"})

    ET.SubElement(manager, "orderEntry", {"type": "module", "module-name": ROOT_MODULE_NAME})
    if project.distribution != "auto-mas-core":
        ET.SubElement(manager, "orderEntry", {"type": "module", "module-name": CORE_PLUGIN_MODULE_NAME})
    ET.SubElement(manager, "orderEntry", {"type": "sourceFolder", "forTests": "false"})
    ET.SubElement(
        manager,
        "orderEntry",
        {"type": "jdk", "jdkName": ROOT_SDK_NAME, "jdkType": ROOT_SDK_TYPE},
    )
    return ET.ElementTree(root)


def _register_pycharm_module(idea_dir: Path, iml_path: Path) -> Path | None:
    modules_xml = idea_dir / "modules.xml"
    if modules_xml.exists():
        tree = ET.parse(modules_xml)
        root = tree.getroot()
    else:
        root = ET.Element("project", {"version": "4"})
        tree = ET.ElementTree(root)

    manager = root.find("component[@name='ProjectModuleManager']")
    if manager is None:
        manager = ET.SubElement(root, "component", {"name": "ProjectModuleManager"})

    modules = manager.find("modules")
    if modules is None:
        modules = ET.SubElement(manager, "modules")

    fileurl = f"file://$PROJECT_DIR$/.idea/{iml_path.name}"
    filepath = f"$PROJECT_DIR$/.idea/{iml_path.name}"
    has_module = any(
        module.get("fileurl") == fileurl or module.get("filepath") == filepath
        for module in modules.findall("module")
    )
    if has_module:
        return None

    ET.SubElement(modules, "module", {"fileurl": fileurl, "filepath": filepath})
    ET.indent(tree, space="  ")
    before = modules_xml.read_text(encoding="utf-8") if modules_xml.exists() else ""
    tree.write(modules_xml, encoding="utf-8", xml_declaration=True)
    after = modules_xml.read_text(encoding="utf-8")
    return modules_xml if before != after else None


def sync_pycharm_modules(workspace: Path, projects: list[PluginProject]) -> list[Path]:
    idea_dir = workspace / ".idea"
    if not idea_dir.exists():
        return []

    changed: list[Path] = []
    for project in projects:
        iml_path = idea_dir / _module_file_name(project.distribution)
        if iml_path.exists():
            tree = ET.parse(iml_path)
            before = iml_path.read_text(encoding="utf-8")
        else:
            tree = _create_pycharm_module_tree(project)
            before = ""

        modules_xml = _register_pycharm_module(idea_dir, iml_path)
        if modules_xml is not None and modules_xml not in changed:
            changed.append(modules_xml)

        root = tree.getroot()
        manager = root.find("component[@name='NewModuleRootManager']")
        if manager is None:
            continue

        order_entries = manager.findall("orderEntry")
        jdk_entry = next((entry for entry in order_entries if entry.get("type") == "jdk"), None)
        if jdk_entry is None:
            source_entry = next(
                (entry for entry in order_entries if entry.get("type") == "sourceFolder"),
                None,
            )
            jdk_entry = ET.Element(
                "orderEntry",
                {"type": "jdk", "jdkName": ROOT_SDK_NAME, "jdkType": ROOT_SDK_TYPE},
            )
            if source_entry is None:
                manager.append(jdk_entry)
            else:
                insert_at = list(manager).index(source_entry)
                manager.insert(insert_at, jdk_entry)
        else:
            jdk_entry.set("jdkName", ROOT_SDK_NAME)
            jdk_entry.set("jdkType", ROOT_SDK_TYPE)

        has_root_module_dep = any(
            entry.get("type") == "module" and entry.get("module-name") == ROOT_MODULE_NAME
            for entry in manager.findall("orderEntry")
        )
        if not has_root_module_dep:
            source_entry = next(
                (entry for entry in manager.findall("orderEntry") if entry.get("type") == "sourceFolder"),
                None,
            )
            module_entry = ET.Element(
                "orderEntry",
                {"type": "module", "module-name": ROOT_MODULE_NAME},
            )
            if source_entry is None:
                manager.append(module_entry)
            else:
                insert_at = list(manager).index(source_entry)
                manager.insert(insert_at, module_entry)

        if project.distribution != "auto-mas-core":
            has_core_module_dep = any(
                entry.get("type") == "module" and entry.get("module-name") == CORE_PLUGIN_MODULE_NAME
                for entry in manager.findall("orderEntry")
            )
            if not has_core_module_dep:
                source_entry = next(
                    (entry for entry in manager.findall("orderEntry") if entry.get("type") == "sourceFolder"),
                    None,
                )
                module_entry = ET.Element(
                    "orderEntry",
                    {"type": "module", "module-name": CORE_PLUGIN_MODULE_NAME},
                )
                if source_entry is None:
                    manager.append(module_entry)
                else:
                    insert_at = list(manager).index(source_entry)
                    manager.insert(insert_at, module_entry)

        content = manager.find("content")
        if content is not None:
            src_url = f"file://$MODULE_DIR$/{project.member}/src"
            has_src = any(
                folder.get("url") == src_url
                for folder in content.findall("sourceFolder")
            )
            if not has_src and (project.path / "src").exists():
                ET.SubElement(content, "sourceFolder", {"url": src_url, "isTestSource": "false"})

        ET.indent(tree, space="  ")
        tree.write(iml_path, encoding="utf-8", xml_declaration=True)
        after = iml_path.read_text(encoding="utf-8")
        if before != after:
            changed.append(iml_path)

    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if pyproject.toml is out of sync")
    parser.add_argument("--write", action="store_true", help="update pyproject.toml")
    parser.add_argument("--sync-idea", action="store_true", help="align existing PyCharm plugin modules with the root uv SDK")
    args = parser.parse_args()

    if args.check == args.write:
        parser.error("choose exactly one of --check or --write")

    workspace = Path.cwd()
    pyproject = workspace / "pyproject.toml"
    projects = discover_plugin_projects(workspace)
    current = pyproject.read_text(encoding="utf-8")
    expected = render_root_pyproject(current, projects)

    if args.check:
        if current != expected:
            print("pyproject.toml is out of sync with local plugin projects", file=sys.stderr)
            return 1
        return 0

    pyproject.write_text(expected, encoding="utf-8")
    print(f"Synced {len(projects)} plugin projects into pyproject.toml")
    if args.sync_idea:
        changed = sync_pycharm_modules(workspace, projects)
        print(f"Updated {len(changed)} PyCharm module files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
