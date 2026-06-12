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

        entry_points = _entry_points(project)
        if not entry_points:
            continue

        distribution = str(project.get("name") or item.name).strip()
        if not distribution:
            continue

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


def sync_pycharm_modules(workspace: Path, projects: list[PluginProject]) -> list[Path]:
    idea_dir = workspace / ".idea"
    if not idea_dir.exists():
        return []

    changed: list[Path] = []
    for project in projects:
        iml_path = idea_dir / _module_file_name(project.distribution)
        if not iml_path.exists():
            continue

        tree = ET.parse(iml_path)
        root = tree.getroot()
        manager = root.find("component[@name='NewModuleRootManager']")
        if manager is None:
            continue

        has_jdk = any(entry.get("type") == "jdk" for entry in manager.findall("orderEntry"))
        if not has_jdk:
            source_entry = next(
                (entry for entry in manager.findall("orderEntry") if entry.get("type") == "sourceFolder"),
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
        before = iml_path.read_text(encoding="utf-8")
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
