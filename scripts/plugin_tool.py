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


@dataclass(frozen=True)
class GitInitResult:
    initialized: bool
    staged: bool
    committed: bool
    messages: tuple[str, ...] = ()


@dataclass(frozen=True)
class SyncResult:
    ok: bool
    detail: str


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
    """Find the AUTO-MAS root even when invoked from a subdirectory."""
    cwd = Path.cwd().resolve()
    candidates = (cwd, *cwd.parents, Path(__file__).resolve().parent.parent)
    for candidate in candidates:
        if (
            (candidate / "pyproject.toml").is_file()
            and (candidate / "scripts" / "sync_plugin_workspace.py").is_file()
        ):
            return candidate
    raise ScaffoldError("未找到 AUTO-MAS 工作区，请在仓库目录内运行此命令")


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


def run_command(command: list[str], *, cwd: Path) -> SyncResult:
    """Run a child command and return concise, user-facing diagnostics."""
    try:
        result = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return SyncResult(False, f"{type(exc).__name__}: {exc}")

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    detail = stdout if result.returncode == 0 else stderr or stdout
    return SyncResult(result.returncode == 0, detail or f"exit code {result.returncode}")


def sync_uv_plugin_workspace(workspace_dir: Path) -> SyncResult:
    """Register local plugins in the uv workspace and PyCharm modules."""
    script_path = Path(__file__).resolve().parent / "sync_plugin_workspace.py"
    if not script_path.exists():
        return SyncResult(False, f"workspace sync helper not found: {script_path}")

    command = [
        sys.executable,
        str(script_path),
        "--write",
        "--sync-idea",
    ]
    return run_command(command, cwd=workspace_dir)


def sync_uv_environment(workspace_dir: Path) -> SyncResult:
    """Install development and local-plugin dependency groups."""
    uv_cmd = shutil.which("uv")
    if not uv_cmd:
        return SyncResult(False, "未检测到 uv 命令")
    return run_command(
        [uv_cmd, "sync", "--dev", "--group", "plugins"],
        cwd=workspace_dir,
    )


def maybe_init_git(target_dir: Path, *, create_commit: bool = True) -> GitInitResult:
    """Initialize an independent Git repository and optionally create a commit."""
    messages: list[str] = []
    if (target_dir / ".git").exists():
        return GitInitResult(True, False, False, ("目标目录已经是 Git 仓库",))

    git_cmd = shutil.which("git")
    if not git_cmd:
        return GitInitResult(False, False, False, ("未检测到 git 命令",))

    init_result = run_command(
        [git_cmd, "init", "--initial-branch=main"],
        cwd=target_dir,
    )
    if not init_result.ok:
        init_result = run_command([git_cmd, "init"], cwd=target_dir)
    initialized = init_result.ok and (target_dir / ".git").exists()
    if not initialized:
        return GitInitResult(False, False, False, (f"git init 失败: {init_result.detail}",))

    root_result = run_command([git_cmd, "rev-parse", "--show-toplevel"], cwd=target_dir)
    try:
        actual_root = Path(root_result.detail).resolve() if root_result.ok else None
    except OSError:
        actual_root = None
    if actual_root != target_dir.resolve():
        return GitInitResult(
            False,
            False,
            False,
            (f"Git 仓库根目录异常: {root_result.detail}",),
        )

    add_result = run_command([git_cmd, "add", "."], cwd=target_dir)
    if not add_result.ok:
        return GitInitResult(True, False, False, (f"git add 失败: {add_result.detail}",))

    if not create_commit:
        return GitInitResult(True, True, False)

    commit_result = run_command(
        [git_cmd, "commit", "-m", "chore: initialize plugin"],
        cwd=target_dir,
    )
    if not commit_result.ok:
        messages.append(f"首次提交失败: {commit_result.detail}")
        messages.append("仓库已经初始化并暂存文件；请检查 Git user.name 和 user.email")
        return GitInitResult(True, True, False, tuple(messages))

    return GitInitResult(True, True, True)


def read_input(prompt: str) -> str:
    """Read one interactive value with a compact inline prompt."""
    if not sys.stdin.isatty():
        raise ScaffoldError("当前终端不支持交互输入，请使用命令行参数")
    sys.stdout.write(f"{prompt}: ")
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
        value = read_input(f"{message} [{suffix}]").strip().lower()
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
    git_group = parser.add_mutually_exclusive_group()
    git_group.add_argument(
        "--git",
        "--init-git",
        action="store_true",
        dest="init_git",
        help="初始化独立 Git 仓库（默认）",
    )
    git_group.add_argument(
        "--no-git",
        action="store_false",
        dest="init_git",
        help="不初始化 Git 仓库",
    )
    parser.set_defaults(init_git=True)
    commit_group = parser.add_mutually_exclusive_group()
    commit_group.add_argument(
        "--commit",
        action="store_true",
        dest="create_commit",
        help="创建首次提交（默认）",
    )
    commit_group.add_argument(
        "--no-commit",
        action="store_false",
        dest="create_commit",
        help="只初始化并暂存仓库，不创建首次提交",
    )
    parser.set_defaults(create_commit=True)
    sync_group = parser.add_mutually_exclusive_group()
    sync_group.add_argument(
        "--sync",
        action="store_true",
        dest="sync_workspace",
        help="同步 workspace、PyCharm 模块和 uv 环境（默认）",
    )
    sync_group.add_argument(
        "--no-sync",
        action="store_false",
        dest="sync_workspace",
        help="跳过 workspace 和 uv 环境同步",
    )
    parser.set_defaults(sync_workspace=True)
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


def print_step(label: str, state: str, detail: str = "") -> None:
    """Print one stable status line suitable for terminals and CI logs."""
    detail = "; ".join(line.strip() for line in detail.splitlines() if line.strip())
    suffix = f": {detail}" if detail else ""
    print(f"[{state}] {label}{suffix}")


def main() -> int:
    """脚手架主入口。"""
    args = parse_args()

    try:
        workspace = get_workspace_dir()
    except ScaffoldError as exc:
        print(f"生成失败: {exc}")
        return 1
    plugins_dir = get_plugins_dir(workspace)
    try:
        plugins_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"生成失败: 无法创建插件目录: {exc}")
        return 1

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

    try:
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
    except ScaffoldError as exc:
        print(f"生成失败: {exc}")
        return 1

    created_target = False
    try:
        target_dir.mkdir(parents=True, exist_ok=False)
        created_target = True
        created: list[str] = []
        for rel_path, content in files.items():
            file_path = target_dir / rel_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            created.append(str((Path(plugin_name) / rel_path).as_posix()))
    except Exception as exc:
        if created_target and target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        print(f"生成失败: {type(exc).__name__}: {exc}")
        return 1

    print()
    print(f"已创建插件 {plugin_name}")
    print(f"目录: {target_dir}")
    print(f"模板: {preset.label}")
    print(f"文件: {len(created)} 个")
    print()

    warnings: list[str] = []
    git_result = GitInitResult(False, False, False)
    if args.init_git:
        git_result = maybe_init_git(
            target_dir,
            create_commit=args.create_commit,
        )
        if git_result.initialized:
            mode = "嵌套独立仓库" if parent_in_git_repo else "独立仓库"
            print_step("Git 仓库", "OK", mode)
            vcs_ok, vcs_message = ensure_pycharm_vcs_mapping(workspace, plugin_name)
            if vcs_ok:
                vcs_state = "OK"
            elif "未检测到 .idea" in vcs_message:
                vcs_state = "SKIP"
            else:
                vcs_state = "WARN"
            print_step("PyCharm VCS 映射", vcs_state, vcs_message)
        else:
            print_step("Git 仓库", "FAIL")
        if args.create_commit:
            if git_result.committed:
                print_step("首次提交", "OK", "chore: initialize plugin")
            elif git_result.initialized:
                print_step("首次提交", "WARN", "仓库已创建，但提交未完成")
        else:
            print_step("首次提交", "SKIP", "--no-commit，文件已暂存")
        warnings.extend(git_result.messages)
    else:
        print_step("Git 仓库", "SKIP", "--no-git")

    workspace_sync = SyncResult(True, "")
    environment_sync = SyncResult(True, "")
    if args.sync_workspace:
        workspace_sync = sync_uv_plugin_workspace(workspace)
        print_step(
            "workspace 与 PyCharm 模块",
            "OK" if workspace_sync.ok else "FAIL",
            workspace_sync.detail,
        )
        if workspace_sync.ok:
            environment_sync = sync_uv_environment(workspace)
            print_step(
                "uv 开发环境",
                "OK" if environment_sync.ok else "FAIL",
                environment_sync.detail,
            )
        else:
            environment_sync = SyncResult(False, "workspace 同步失败，未执行 uv sync")
            print_step("uv 开发环境", "SKIP", environment_sync.detail)
    else:
        print_step("workspace 与 PyCharm 模块", "SKIP", "--no-sync")
        print_step("uv 开发环境", "SKIP", "--no-sync")

    if warnings:
        print()
        print("注意:")
        for item in warnings:
            print(f"- {item}")

    print()
    print(f"Entry Point: auto_mas.plugins / {plugin_name}")
    if args.sync_workspace and (not workspace_sync.ok or not environment_sync.ok):
        print("插件文件已创建，但开发环境同步未完成。")
        return 2
    if args.init_git and not git_result.initialized:
        print("插件文件已创建，但 Git 仓库初始化失败。")
        return 2
    print("完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
