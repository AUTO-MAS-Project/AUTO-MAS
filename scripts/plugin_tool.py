#!/usr/bin/env python3
"""插件脚手架工具。"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
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
PAGE_TEMPLATE_DIR_NAME = "plugin_page_templates"


@dataclass(frozen=True)
class TemplatePreset:
    """脚手架模板预设。"""

    key: str
    label: str
    outputs: dict[Path, Path]


PLUGIN_TEMPLATE_OUTPUTS = {
    Path("pyproject.toml"): Path("pyproject.toml.template"),
    Path("README.md"): Path("README.md.template"),
    Path("src/${plugin_name}/__init__.py"): Path("__init__.py.template"),
    Path("src/${plugin_name}/plugin.py"): Path("plugin.py.template"),
    Path("src/${plugin_name}/schema.py"): Path("schema.py.template"),
    Path(".github/workflows/publish.yml"): Path("publish.yml.template"),
    Path(".gitattributes"): Path(".gitattributes.template"),
    Path(".editorconfig"): Path(".editorconfig.template"),
    Path(".gitignore"): Path(".gitignore.template"),
}

SCRIPT_ADAPTER_TEMPLATE_OUTPUTS = {
    Path("pyproject.toml"): Path("pyproject.toml.template"),
    Path("README.md"): Path("script_adapter/README.md.template"),
    Path("src/${plugin_name}/__init__.py"): Path("script_adapter/__init__.py.template"),
    Path("src/${plugin_name}/plugin.py"): Path("script_adapter/plugin.py.template"),
    Path("src/${plugin_name}/schema.py"): Path("script_adapter/schema.py.template"),
    Path("src/${plugin_name}/adapter/__init__.py"): Path(
        "script_adapter/adapter/__init__.py.template"
    ),
    Path("src/${plugin_name}/adapter/runtime.py"): Path(
        "script_adapter/adapter/runtime.py.template"
    ),
    Path(".github/workflows/publish.yml"): Path("publish.yml.template"),
    Path(".gitattributes"): Path(".gitattributes.template"),
    Path(".editorconfig"): Path(".editorconfig.template"),
    Path(".gitignore"): Path(".gitignore.template"),
}

PLUGIN_PAGE_TEMPLATE_OUTPUTS = {
    Path("pyproject.toml"): Path("pyproject.toml.template"),
    Path("README.md"): Path("README.md.template"),
    Path("package.json"): Path("package.json.template"),
    Path("src/${plugin_name}/__init__.py"): Path("__init__.py.template"),
    Path("src/${plugin_name}/plugin.py"): Path("plugin.py.template"),
    Path("src/${plugin_name}/schema.py"): Path("schema.py.template"),
    Path("src/${plugin_name}/frontend/manifest.json"): Path(
        "frontend/manifest.json.template"
    ),
    Path("src/${plugin_name}/frontend/dist/index.js"): Path(
        "frontend/dist/index.js.template"
    ),
    Path("frontend-src/package.json"): Path("frontend-src/package.json.template"),
    Path("frontend-src/plugin.frontend.dev.json"): Path(
        "frontend-src/plugin.frontend.dev.json.template"
    ),
    Path("frontend-src/vite.config.mjs"): Path("frontend-src/vite.config.mjs.template"),
    Path("frontend-src/scripts/write-manifest.mjs"): Path(
        "frontend-src/scripts/write-manifest.mjs.template"
    ),
    Path("frontend-src/src/main.ts"): Path("frontend-src/src/main.ts.template"),
    Path("frontend-src/src/${plugin_page_component}.ce.vue"): Path(
        "frontend-src/src/PluginPage.ce.vue.template"
    ),
    Path(".github/workflows/publish.yml"): Path("publish.yml.template"),
    Path(".gitattributes"): Path(".gitattributes.template"),
    Path(".editorconfig"): Path(".editorconfig.template"),
    Path(".gitignore"): Path(".gitignore.template"),
}

TEMPLATE_PRESETS = {
    "plugin": TemplatePreset(
        key="plugin",
        label="普通插件",
        outputs=PLUGIN_TEMPLATE_OUTPUTS,
    ),
    "script-adapter": TemplatePreset(
        key="script-adapter",
        label="专项脚本适配插件",
        outputs=SCRIPT_ADAPTER_TEMPLATE_OUTPUTS,
    ),
}


class ScaffoldError(Exception):
    """脚手架错误。"""


def get_workspace_dir() -> Path:
    """获取当前工作目录。"""
    return Path.cwd()


def get_plugins_dir(workspace_dir: Path) -> Path:
    """获取 plugins 根目录。"""
    return workspace_dir / "plugins"


def get_pypi_site_dir(plugins_dir: Path) -> Path:
    """获取 plugins/pypi/site-packages 目录。"""
    return plugins_dir / "pypi" / "site-packages"


def get_template_dir() -> Path:
    """获取模板目录。"""
    return Path(__file__).resolve().parent / TEMPLATE_DIR_NAME


def get_page_template_dir() -> Path:
    """获取带页面插件模板目录。"""
    return Path(__file__).resolve().parent / PAGE_TEMPLATE_DIR_NAME


def is_inside_git_repo(path: Path) -> bool:
    """判断目标路径是否位于 Git 仓库内。"""
    current = path.resolve()
    for parent in (current, *current.parents):
        if (parent / ".git").exists():
            return True
    return False


def iter_plugin_entry_points(plugins_dir: Path):
    """枚举本地插件环境中的插件入口点。"""
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
    """校验插件名。"""
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
        raise ScaffoldError(
            f"插件名已被本地 PyPI 插件占用: {normalized} (distribution={dist_name})"
        )

    return normalized


def validate_description(description: str) -> str:
    """校验插件简介。"""
    return description.strip()


def to_pascal_case(value: str) -> str:
    """把蛇形命名转换为帕斯卡命名。"""
    return "".join(part.capitalize() for part in value.split("_") if part)


def to_kebab_case(value: str) -> str:
    """把蛇形命名转换为 kebab-case。"""
    return "-".join(part for part in value.split("_") if part)


def build_template_variables(
    plugin_name: str,
    description: str,
    workspace_dir: Path,
) -> Dict[str, str]:
    """构建脚手架模板变量。"""
    plugin_class_name = to_pascal_case(plugin_name)
    plugin_element_tag = f"{to_kebab_case(plugin_name)}-panel"
    plugin_page_component = f"{plugin_class_name}Page"
    return {
        "plugin_name": plugin_name,
        "plugin_title": plugin_name.replace("_", " ").title(),
        "plugin_class_name": plugin_class_name,
        "plugin_element_tag": plugin_element_tag,
        "plugin_page_component": plugin_page_component,
        "plugin_page_id": f"{plugin_name}-page",
        "plugin_page_path": f"/{plugin_name}",
        "script_type_key": plugin_name.upper(),
        "description": description,
        "description_escaped": description.replace('"', '\\"'),
        "workspace_dir": workspace_dir.resolve().as_posix(),
    }


def render_template(content: str, variables: Dict[str, str]) -> str:
    """渲染模板内容。"""
    try:
        return Template(content).substitute(variables)
    except KeyError as exc:  # pragma: no cover
        raise ScaffoldError(f"模板变量缺失: {exc}") from exc


def build_template_files(
    plugin_name: str,
    description: str,
    kind: str,
    workspace_dir: Path,
) -> Dict[Path, str]:
    """构建目标文件内容。"""
    template_dir = get_template_dir()
    preset = TEMPLATE_PRESETS.get(kind)
    if preset is None:
        raise ScaffoldError(f"未知模板类型: {kind}")
    if not template_dir.exists():
        raise ScaffoldError(f"模板目录不存在: {template_dir}")

    variables = build_template_variables(plugin_name, description, workspace_dir)

    files: Dict[Path, str] = {}
    for output_template, source_template in preset.outputs.items():
        source_path = template_dir / source_template
        if not source_path.exists():
            raise ScaffoldError(f"模板文件不存在: {source_path}")
        output_path = Path(render_template(output_template.as_posix(), variables))
        files[output_path] = render_template(
            source_path.read_text(encoding="utf-8"),
            variables,
        )
    return files


def build_page_template_files(
    plugin_name: str,
    description: str,
    workspace_dir: Path,
) -> Dict[Path, str]:
    """构建带页面插件目标文件内容。"""
    template_dir = get_page_template_dir()
    if not template_dir.exists():
        raise ScaffoldError(f"带页面插件模板目录不存在: {template_dir}")

    variables = build_template_variables(plugin_name, description, workspace_dir)

    files: Dict[Path, str] = {}
    for output_template, source_template in PLUGIN_PAGE_TEMPLATE_OUTPUTS.items():
        source_path = template_dir / source_template
        if not source_path.exists():
            raise ScaffoldError(f"带页面插件模板文件不存在: {source_path}")
        output_path = Path(render_template(output_template.as_posix(), variables))
        files[output_path] = render_template(
            source_path.read_text(encoding="utf-8"),
            variables,
        )
    return files


def ensure_pycharm_vcs_mapping(workspace_dir: Path, plugin_name: str) -> tuple[bool, str]:
    """在 PyCharm 的 vcs.xml 中补充子仓库映射。"""
    idea_dir = workspace_dir / ".idea"
    if not idea_dir.exists():
        return False, "未检测到 .idea 目录，已跳过 PyCharm VCS 映射"

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
    except Exception as exc:  # pragma: no cover
        return False, f"写入 PyCharm VCS 映射失败: {type(exc).__name__}: {exc}"


def sync_uv_plugin_workspace(workspace_dir: Path) -> tuple[bool, str]:
    """Run the workspace synchronization helper after scaffolding a plugin."""
    script_path = Path(__file__).resolve().parent / "sync_plugin_workspace.py"
    if not script_path.exists():
        return False, f"workspace sync helper not found: {script_path}"

    command = [
        sys.executable,
        str(script_path),
        "--write",
        "--sync-idea",
    ]
    result = subprocess.run(
        command,
        cwd=str(workspace_dir),
        capture_output=True,
        text=True,
        check=False,
    )
    detail = (result.stdout or "").strip()
    if result.returncode == 0:
        return True, detail or "uv workspace synchronized"

    error = (result.stderr or "").strip() or detail or "unknown error"
    return False, f"uv workspace sync failed: {error}"


def maybe_init_git(target_dir: Path) -> tuple[bool, list[str]]:
    """按需初始化 Git 仓库并提交初始内容。"""
    warnings: list[str] = []
    if (target_dir / ".git").exists():
        warnings.append("检测到目标目录已存在 .git，已跳过初始化")
        return False, warnings

    git_cmd = shutil.which("git")
    if not git_cmd:
        warnings.append("未检测到 git 命令，已跳过初始化")
        return False, warnings

    for command in (
        [git_cmd, "init"],
        [git_cmd, "add", "."],
        [git_cmd, "commit", "-m", "initial commit"],
    ):
        result = subprocess.run(
            command,
            cwd=str(target_dir),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            continue
        detail = (result.stderr or "").strip() or (result.stdout or "").strip() or "unknown error"
        warnings.append(f"{' '.join(command[1:])} 失败: {detail}")
        if command[-1] == "initial commit":
            warnings.append("请检查 Git 用户名和邮箱是否已配置")
        return False, warnings

    return True, warnings


def read_input(prompt: str) -> str:
    """读取交互输入。"""
    if not sys.stdin.isatty():
        raise ScaffoldError("当前终端不支持交互输入，请使用命令行参数")
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


def prompt_yes_no(message: str, *, default: bool = False) -> bool:
    """提示用户选择是/否。"""
    suffix = "Y/n" if default else "y/N"
    while True:
        value = read_input(f"{message} ({suffix})").strip().lower()
        if not value:
            return default
        if value in {"y", "yes", "是"}:
            return True
        if value in {"n", "no", "否"}:
            return False
        print("请输入 y 或 n。")


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="AUTO-MAS 插件脚手架工具")
    parser.add_argument("--name", type=str, help="插件名，小写蛇形命名")
    parser.add_argument("--description", type=str, help="插件简介")
    parser.add_argument(
        "--kind",
        type=str,
        default="plugin",
        choices=sorted(TEMPLATE_PRESETS.keys()),
        help="脚手架模板类型",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--init-git", action="store_true", help="生成后初始化 Git 仓库")
    group.add_argument("--no-git", action="store_true", help="生成后不初始化 Git 仓库")
    page_group = parser.add_mutually_exclusive_group()
    page_group.add_argument(
        "--with-page",
        action="store_true",
        default=None,
        help="生成带 Vue 页面插件（仅支持 --kind plugin）",
    )
    page_group.add_argument(
        "--no-page",
        action="store_false",
        dest="with_page",
        help="生成普通无页面插件",
    )
    return parser.parse_args()


def main() -> int:
    """脚手架主入口。"""
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
            input_name = prompt_non_empty("请输入插件名，例如 demo_plugin")
        try:
            plugin_name = validate_plugin_name(input_name, plugins_dir)
            break
        except ScaffoldError as exc:
            print(f"插件名无效: {exc}")
            if not interactive:
                return 1
            input_name = ""

    if args.description is None and interactive:
        description = validate_description(prompt_optional("请输入插件简介（可留空）"))
    else:
        description = validate_description(args.description or "")

    with_page = bool(args.with_page)
    if args.with_page is None and interactive and args.kind == "plugin":
        with_page = prompt_yes_no("是否需要带页面？", default=False)
    if with_page and args.kind != "plugin":
        print("生成失败: 带页面模板仅支持普通插件（--kind plugin）")
        return 1

    target_dir = (plugins_dir / plugin_name).resolve()
    parent_in_git_repo = is_inside_git_repo(target_dir.parent)
    init_git = not args.no_git
    skip_git_reason = ""
    if init_git and shutil.which("git") is None:
        init_git = False
        skip_git_reason = "当前环境未检测到 git，已自动跳过初始化"

    preset = (
        TemplatePreset(
            key="plugin-page",
            label="带页面插件",
            outputs=PLUGIN_PAGE_TEMPLATE_OUTPUTS,
        )
        if with_page
        else TEMPLATE_PRESETS[args.kind]
    )
    files = (
        build_page_template_files(plugin_name, description, workspace)
        if with_page
        else build_template_files(plugin_name, description, args.kind, workspace)
    )

    try:
        target_dir.mkdir(parents=True, exist_ok=False)
        created: list[str] = []
        for rel_path, content in files.items():
            file_path = target_dir / rel_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            created.append(str((Path(plugin_name) / rel_path).as_posix()))
    except Exception as exc:
        print(f"生成失败: {type(exc).__name__}: {exc}")
        return 1

    git_ok = False
    warnings: list[str] = []
    if skip_git_reason:
        warnings.append(skip_git_reason)
    if init_git:
        git_ok, warnings = maybe_init_git(target_dir)
        if git_ok:
            _, vcs_message = ensure_pycharm_vcs_mapping(workspace, plugin_name)
            if vcs_message:
                print(f"- PyCharm VCS 映射: {vcs_message}")

    workspace_sync_ok, workspace_sync_message = sync_uv_plugin_workspace(workspace)
    if not workspace_sync_ok:
        warnings.append(workspace_sync_message)

    print("\n插件脚手架生成成功")
    print(f"- 模板类型: {preset.label}")
    print(f"- 输出目录: {target_dir}")
    print(f"- Entry Point: auto_mas.plugins / {plugin_name}")
    if init_git:
        git_mode = "子仓库模式" if parent_in_git_repo else "独立仓库模式"
        print(f"- Git 模式: {git_mode}")
    else:
        print("- Git 模式: 已禁用")
    print(f"- Git 初始化: {'成功' if git_ok else '未执行'}")
    print(f"- UV workspace: {'已同步' if workspace_sync_ok else '未同步'}")
    if workspace_sync_ok and workspace_sync_message:
        for line in workspace_sync_message.splitlines():
            print(f"  * {line}")
    print("- 已创建文件:")
    for item in created:
        print(f"  * {item}")
    if warnings:
        print("- 注意事项:")
        for item in warnings:
            print(f"  * {item}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
