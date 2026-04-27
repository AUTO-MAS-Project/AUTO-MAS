#!/usr/bin/env python3
"""独立最小 PyPI 插件脚手架。"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from string import Template
from typing import Dict

try:
    import importlib.metadata as importlib_metadata
except Exception:  # pragma: no cover
    import importlib_metadata  # type: ignore[no-redef]


PLUGIN_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
ENTRY_POINT_GROUPS = ("auto_mas.plugins", "automas.plugins")
TEMPLATE_DIR_NAME = "plugin_templates"

TEMPLATE_OUTPUTS = {
    Path("pyproject.toml"): Path("pyproject.toml.template"),
    Path("README.md"): Path("README.md.template"),
    Path("src/${plugin_name}/__init__.py"): Path("__init__.py.template"),
    Path("src/${plugin_name}/plugin.py"): Path("plugin.py.template"),
    Path("src/${plugin_name}/schema.py"): Path("schema.py.template"),
    Path(".github/publish.yml"): Path("publish.yml.template"),
    Path(".gitattributes"): Path(".gitattributes.template"),
    Path(".editorconfig"): Path(".editorconfig.template"),
    Path(".gitignore"): Path(".gitignore.template"),
}


class ScaffoldError(Exception):
    """独立脚手架错误。"""


def get_workspace_dir() -> Path:
    """获取当前工作目录。"""
    return Path.cwd()


def get_plugins_dir(workspace_dir: Path) -> Path:
    """获取 plugins 根目录。"""
    return workspace_dir / "plugins"


def get_pypi_site_dir(plugins_dir: Path) -> Path:
    """获取 plugins/pypi/site-packages 目录。"""
    return plugins_dir / "pypi" / "site-packages"


def is_inside_git_repo(path: Path) -> bool:
    """判断路径是否位于 Git 仓库内（向上查找 .git）。"""
    current = path.resolve()
    for parent in (current, *current.parents):
        git_marker = parent / ".git"
        if git_marker.exists():
            return True
    return False


def iter_plugin_entry_points(plugins_dir: Path):
    """枚举本地插件 site-packages 内的插件 entry points。"""
    site_dir = get_pypi_site_dir(plugins_dir)
    if not site_dir.exists():
        return []

    result = []
    seen = set()
    for dist in importlib_metadata.distributions(path=[str(site_dir)]):
        for ep in getattr(dist, "entry_points", []):
            if ep.group not in ENTRY_POINT_GROUPS:
                continue
            key = (ep.group, ep.name, ep.value)
            if key in seen:
                continue
            seen.add(key)
            result.append(ep)
    return result


def validate_plugin_name(plugin_name: str, plugins_dir: Path) -> str:
    """在输入阶段校验插件名。

    Args:
        plugin_name (str): 插件名输入。
        plugins_dir (Path): plugins 根目录。

    Returns:
        str: 规范化后插件名。

    Raises:
        ScaffoldError: 当命名不合法、目录冲突或 entry point 冲突时抛出。
    """
    normalized = plugin_name.strip()
    if not normalized:
        raise ScaffoldError("插件名不能为空")
    if not PLUGIN_NAME_PATTERN.match(normalized):
        raise ScaffoldError("插件名必须为小写蛇形命名，例如 demo_plugin")

    target_dir = (plugins_dir / normalized).resolve()
    root = plugins_dir.resolve()
    if root != target_dir and root not in target_dir.parents:
        raise ScaffoldError("目标路径非法，必须位于 plugins 目录内")

    if target_dir.exists():
        raise ScaffoldError(f"目标目录已存在: {target_dir}")

    for ep in iter_plugin_entry_points(plugins_dir):
        ep_name = str(getattr(ep, "name", "") or "").strip()
        if ep_name != normalized:
            continue
        dist = getattr(ep, "dist", None)
        dist_name = str(getattr(dist, "name", "") or "").strip() or "unknown"
        raise ScaffoldError(f"插件名已被 PyPI 插件占用: {normalized} (distribution={dist_name})")

    return normalized


def validate_description(description: str) -> str:
    """校验插件简介。"""
    value = description.strip()
    if not value:
        return ""
    return value


def ensure_pycharm_vcs_mapping(workspace_dir: Path, plugin_name: str) -> tuple[bool, str]:
    """为 PyCharm 的 vcs.xml 写入插件仓库映射。"""
    idea_dir = workspace_dir / ".idea"
    if not idea_dir.exists():
        return False, "未检测到 .idea 目录，已跳过 PyCharm VCS 映射写入"

    vcs_xml = idea_dir / "vcs.xml"
    project_dir_token = "$PROJECT_DIR$"
    plugin_mapping = f"{project_dir_token}/plugins/{plugin_name}"

    try:
        if vcs_xml.exists():
            tree = ET.parse(vcs_xml)
            root = tree.getroot()
        else:
            root = ET.Element("project", {"version": "4"})
            tree = ET.ElementTree(root)

        component = None
        for node in root.findall("component"):
            if node.get("name") == "VcsDirectoryMappings":
                component = node
                break

        if component is None:
            component = ET.SubElement(root, "component", {"name": "VcsDirectoryMappings"})

        has_root_mapping = any(
            item.tag == "mapping"
            and item.get("directory") == project_dir_token
            and item.get("vcs") == "Git"
            for item in component.findall("mapping")
        )
        if not has_root_mapping:
            ET.SubElement(component, "mapping", {"directory": project_dir_token, "vcs": "Git"})

        has_plugin_mapping = any(
            item.tag == "mapping"
            and item.get("directory") == plugin_mapping
            and item.get("vcs") == "Git"
            for item in component.findall("mapping")
        )
        if has_plugin_mapping:
            return True, "PyCharm VCS 映射已存在"

        ET.SubElement(component, "mapping", {"directory": plugin_mapping, "vcs": "Git"})
        ET.indent(tree, space="  ")
        tree.write(vcs_xml, encoding="utf-8", xml_declaration=True)
        return True, "已写入 PyCharm VCS 映射"
    except Exception as e:
        return False, f"写入 PyCharm VCS 映射失败: {type(e).__name__}: {e}"


def get_template_dir() -> Path:
    """获取脚手架模板目录。"""
    return Path(__file__).resolve().parent / TEMPLATE_DIR_NAME


def render_template(content: str, variables: Dict[str, str]) -> str:
    """使用安全占位符替换渲染模板文本。"""
    try:
        return Template(content).substitute(variables)
    except KeyError as e:
        raise ScaffoldError(f"模板占位符缺失: {e}") from e


def build_template_files(plugin_name: str, description: str) -> Dict[Path, str]:
    """构建最小 PyPI 模板文件内容。"""
    template_dir = get_template_dir()
    if not template_dir.exists():
        raise ScaffoldError(f"模板目录不存在: {template_dir}")

    variables = {
        "plugin_name": plugin_name,
        "description": description,
        "description_escaped": description.replace('"', '\\"'),
    }

    files: Dict[Path, str] = {}
    for output_template, source_template in TEMPLATE_OUTPUTS.items():
        source_path = template_dir / source_template
        if not source_path.exists():
            raise ScaffoldError(f"模板文件不存在: {source_path}")
        content = source_path.read_text(encoding="utf-8")
        output_path = Path(render_template(output_template.as_posix(), variables))
        files[output_path] = render_template(content, variables)

    return files


def maybe_init_git(target_dir: Path) -> tuple[bool, list[str]]:
    """按需初始化 Git 仓库并创建首次提交。"""
    warnings: list[str] = []
    if (target_dir / ".git").exists():
        warnings.append("检测到已存在 .git，已跳过初始化")
        return False, warnings

    git_cmd = shutil.which("git")
    if not git_cmd:
        warnings.append("未检测到 git 命令，已跳过初始化")
        return False, warnings

    init_result = subprocess.run(
        [git_cmd, "init"],
        cwd=str(target_dir),
        capture_output=True,
        text=True,
        check=False,
    )
    if init_result.returncode != 0:
        warnings.append(f"git init 失败: {(init_result.stderr or '').strip() or 'unknown error'}")
        return False, warnings

    add_result = subprocess.run(
        [git_cmd, "add", "."],
        cwd=str(target_dir),
        capture_output=True,
        text=True,
        check=False,
    )
    if add_result.returncode != 0:
        warnings.append(f"git add . 失败: {(add_result.stderr or '').strip() or 'unknown error'}")
        return False, warnings

    commit_result = subprocess.run(
        [git_cmd, "commit", "-m", "initial commit"],
        cwd=str(target_dir),
        capture_output=True,
        text=True,
        check=False,
    )
    if commit_result.returncode != 0:
        detail = (commit_result.stderr or "").strip() or (commit_result.stdout or "").strip() or "unknown error"
        warnings.append(f"git commit 失败: {detail}")
        warnings.append("请检查 Git 用户名/邮箱是否已配置（git config user.name / user.email）")
        return False, warnings

    return True, warnings


def read_input(prompt: str) -> str:
    """输出提示并立即刷新，再读取输入。

    为了提升可读性，提示文本会独占一行，用户在下一行输入。
    """
    if not sys.stdin.isatty():
        raise ScaffoldError("当前终端不支持交互输入，请使用 --name 与 --description 参数")
    sys.stdout.write(f"\n{prompt}\n")
    sys.stdout.flush()
    line = sys.stdin.readline()
    if line == "":
        raise EOFError("输入流已关闭")
    return line.rstrip("\r\n")


def prompt_non_empty(message: str) -> str:
    """提示用户输入非空文本。"""
    while True:
        value = read_input(message).strip()
        if value:
            return value
        print("输入不能为空，请重新输入。")


def prompt_optional(message: str) -> str:
    """提示用户输入可留空文本。"""
    return read_input(message).strip()


def prompt_yes_no(message: str, default: bool = False) -> bool:
    """提示用户输入是/否。"""
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        raw = read_input(f"{message} {suffix}: ").strip().lower()
        if not raw:
            return default
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False
        print("请输入 y 或 n。")


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="独立最小 PyPI 插件脚手架（不依赖后端初始化）")
    parser.add_argument("--name", type=str, help="插件名（小写蛇形）")
    parser.add_argument("--description", type=str, help="插件简介")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--init-git", action="store_true", help="生成后初始化 Git（默认）")
    group.add_argument("--no-git", action="store_true", help="生成后不初始化 Git")
    return parser.parse_args()


def main() -> int:
    """独立脚手架主入口。"""
    args = parse_args()

    workspace = get_workspace_dir()
    plugins_dir = get_plugins_dir(workspace)
    plugins_dir.mkdir(parents=True, exist_ok=True)

    input_name = (args.name or "").strip()
    interactive = not bool(input_name)

    while True:
        if not input_name:
            if not interactive:
                print("生成失败: 插件名不能为空")
                return 1
            input_name = prompt_non_empty("请输入插件名, 如demo_plugin,默认我们会给你加上automas_plugin_前缀, 无需自己写:")
        try:
            plugin_name = validate_plugin_name(input_name, plugins_dir)
            break
        except ScaffoldError as e:
            print(f"插件名无效: {e}")
            if not interactive:
                return 1
            input_name = ""

    if args.description is None and interactive:
        description = validate_description(prompt_optional("请输入插件简介（可留空）："))
    else:
        description = validate_description(args.description or "")

    target_dir = (plugins_dir / plugin_name).resolve()
    parent_in_git_repo = is_inside_git_repo(target_dir.parent)
    git_available = shutil.which("git") is not None
    skip_git_reason = ""

    if args.no_git:
        init_git = False
    else:
        init_git = True

    if init_git and not git_available:
        init_git = False
        skip_git_reason = "当前环境未检测到 git，已自动跳过初始化。"

    if init_git:
        if parent_in_git_repo:
            print("\n提示：检测到父目录位于 Git 仓库中，将以子仓库模式初始化插件仓库。")
        else:
            print("\n提示：未检测到父仓库，将初始化独立 Git 仓库。")
    elif skip_git_reason:
        print(f"\n提示：{skip_git_reason}")
    else:
        print("\n提示：已通过 --no-git 禁用 Git 初始化。")

    files = build_template_files(plugin_name, description)

    try:
        target_dir.mkdir(parents=True, exist_ok=False)
        created = []
        for rel_path, content in files.items():
            file_path = target_dir / rel_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            created.append(str((Path(plugin_name) / rel_path).as_posix()))
    except Exception as e:
        print(f"生成失败: {type(e).__name__}: {e}")
        return 1

    git_ok = False
    warnings: list[str] = []
    vcs_mapping_status = ""
    if skip_git_reason:
        warnings.append(skip_git_reason)
    if init_git:
        git_ok, warnings = maybe_init_git(target_dir)
        if git_ok:
            _, vcs_mapping_status = ensure_pycharm_vcs_mapping(workspace, plugin_name)
            if vcs_mapping_status:
                print(f"- PyCharm VCS 映射: {vcs_mapping_status}")

    print("\n最小 PyPI 插件模板生成成功")
    print(f"- 输出目录: {target_dir}")
    print(f"- Entry Point: auto_mas.plugins / {plugin_name}")
    if init_git:
        print(f"- Git 模式: {'子仓库模式' if parent_in_git_repo else '独立仓库模式'}")
    else:
        print("- Git 模式: 已禁用")
    print(f"- Git 初始化: {'是' if git_ok else '否'}")
    print("- 已创建文件:")
    for item in created:
        print(f"  * {item}")
    if warnings:
        print("- 警告:")
        for warning in warnings:
            print(f"  * {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
