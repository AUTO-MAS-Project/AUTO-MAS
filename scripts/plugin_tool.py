#!/usr/bin/env python3
"""独立最小 PyPI 插件脚手架。"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict

try:
    import importlib.metadata as importlib_metadata
except Exception:  # pragma: no cover
    import importlib_metadata  # type: ignore[no-redef]


PLUGIN_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
ENTRY_POINT_GROUPS = ("auto_mas.plugins", "automas.plugins")


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
        raise ScaffoldError("插件简介不能为空")
    return value


def build_template_files(plugin_name: str, description: str) -> Dict[Path, str]:
    """构建最小 PyPI 模板文件内容。"""
    escaped_description = description.replace('"', '\\"')
    pyproject = f'''[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "automas_plugin_{plugin_name}"
version = "0.1.0"
description = "{escaped_description}"
readme = {{ file = "README.md", content-type = "text/markdown" }}
requires-python = ">=3.10"
dependencies = ["pydantic>=2.0"]

[project.entry-points."auto_mas.plugins"]
{plugin_name} = "{plugin_name}.plugin:Plugin"

[tool.setuptools.packages.find]
where = ["src"]
'''

    init_py = (
        '"""最小 PyPI 插件示例包。"""\n\n'
        "from .plugin import Config, Plugin\n\n"
        '__all__ = ["Plugin", "Config"]\n'
    )

    plugin_py = '''from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from app.core.plugins.context import PluginContext


class Plugin:
    """最小 PyPI 插件示例。"""

    def __init__(self, ctx: "PluginContext") -> None:
        """初始化插件实例。

        Args:
            ctx (PluginContext): 插件上下文对象。

        Returns:
            None: 无返回值。
        """
        self.ctx = ctx

    async def on_start(self) -> None:
        """生命周期：实例进入运行态。"""
        self.ctx.logger.info("[{}] 插件启动".format(self.ctx.plugin_name))
        self.ctx.logger.info(f"hello={self.ctx.config.get('hello')}")

    async def on_stop(self, reason: str) -> None:
        """生命周期：实例停止前调用。

        Args:
            reason (str): 停止原因。

        Returns:
            None: 无返回值。
        """
        self.ctx.logger.info("[{}] 插件停止, reason={}".format(self.ctx.plugin_name, reason))


class Config(BaseModel):
    """最小配置模型示例。"""

    model_config = ConfigDict(extra="allow")

    hello: str = Field(default="world", description="问候词")
'''

    readme = f'''# automas_{plugin_name}

{description}

'''

    return {
        Path("pyproject.toml"): pyproject,
        Path("README.md"): readme,
        Path("src") / plugin_name / "__init__.py": init_py,
        Path("src") / plugin_name / "plugin.py": plugin_py,
    }


def maybe_init_git(target_dir: Path) -> tuple[bool, list[str]]:
    """按需初始化 Git 仓库。"""
    warnings: list[str] = []
    if (target_dir / ".git").exists():
        warnings.append("检测到已存在 .git，已跳过初始化")
        return False, warnings

    git_cmd = shutil.which("git")
    if not git_cmd:
        warnings.append("未检测到 git 命令，已跳过初始化")
        return False, warnings

    result = subprocess.run(
        [git_cmd, "init"],
        cwd=str(target_dir),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        warnings.append(f"git init 失败: {(result.stderr or '').strip() or 'unknown error'}")
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
    parser.add_argument("--init-git", action="store_true", help="生成后初始化 Git")
    parser.add_argument("--no-init-git", action="store_true", help="生成后不初始化 Git")
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

    try:
        description = validate_description((args.description or "").strip())
    except ScaffoldError:
        description = prompt_non_empty("请输入插件简介：")

    if args.init_git:
        init_git = True
    elif args.no_init_git:
        init_git = False
    else:
        print("\n注意：父目录已是 Git 仓库时，初始化将创建嵌套仓库。")
        init_git = prompt_yes_no("是否在新插件目录初始化 Git？", default=False)

    target_dir = (plugins_dir / plugin_name).resolve()
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
    if init_git:
        git_ok, warnings = maybe_init_git(target_dir)

    print("\n最小 PyPI 插件模板生成成功")
    print(f"- 输出目录: {target_dir}")
    print(f"- Entry Point: auto_mas.plugins / {plugin_name}")
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
