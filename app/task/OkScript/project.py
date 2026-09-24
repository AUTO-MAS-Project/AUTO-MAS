#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""ok-script 项目识别：认出安装目录里是哪个项目、什么版本、有哪些一次性任务。

读取的全部是上游对外契约，集中在本模块，上游改布局时在这里响亮失败：

- 安装布局来自 ok-script 项目统一使用的打包器 pyappify：根目录 ``<应用名>.exe``，
  ``data/apps/<应用名>/app.json`` 记录应用名与当前版本（``current_version``），
  ``repo/`` 是项目源码，``working/`` 是运行目录（``configs/``、``logs/ok-script.log``），
  ``python/`` 是运行时。布局变了 → 识别失败并提示选择安装根目录。
- 一次性任务列表来自项目 ``src/config.py`` 的 ``config["onetime_tasks"]``：ok-script
  的 ``-t N`` 按这个列表从 1 编号（ok-end-field README「命令行参数」一节）。只做字面量
  解析（ast），不导入、不执行上游代码；不是字面量声明 → 提示暂不支持该版本。
- 任务显示名取任务类 ``__init__`` 里的 ``self.name = "..."`` 字面量（即上游界面里的
  任务名），取不到就回退为类名，只影响显示。继承 ``TriggerTask`` 的任务是持续触发任务，
  本专项暂不运行它们，据此标出。
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from app.utils.io import ConfigCorruptedError, read_dict_file

# 已有独立专项的 ok-script 项目：应用名 → MAS 专项显示名
DEDICATED_ADAPTERS: dict[str, str] = {
    "ok-ww": "ok-ww",
    "ok-nte": "ok-nte",
}
# 已按真实发行包核对过目录布局、任务列表与完成标记的项目
VERIFIED_APPS: frozenset[str] = frozenset({"ok-ef"})

# 持续触发任务的基类名（ok-script ``ok.task.task.TriggerTask``）
_TRIGGER_TASK_BASE = "TriggerTask"


class OkScriptProjectError(Exception):
    """安装目录无法识别为可运行的 ok-script 项目；消息直接给用户看。"""


@dataclass(frozen=True)
class OkScriptTask:
    """一次性任务。

    Attributes:
        task_id: ``模块.类名``，版本更新调整列表顺序时依然能对上同一个任务。
        index: 在 ``onetime_tasks`` 中的序号（从 1 开始），即 ``-t N`` 的 N。
        name: 上游界面里的任务名，取不到时为类名。
        continuous: 是否为持续触发任务（不会自行结束）。
    """

    task_id: str
    index: int
    name: str
    continuous: bool


@dataclass(frozen=True)
class OkScriptProject:
    """识别出的 ok-script 项目。"""

    root: Path
    app_name: str
    version: str
    tasks: tuple[OkScriptTask, ...]
    verified: bool

    @property
    def exe_path(self) -> Path:
        return self.root / f"{self.app_name}.exe"

    @property
    def app_dir(self) -> Path:
        return self.root / "data" / "apps" / self.app_name

    @property
    def app_json_path(self) -> Path:
        return self.app_dir / "app.json"

    @property
    def working_dir(self) -> Path:
        return self.app_dir / "working"

    @property
    def log_path(self) -> Path:
        return self.working_dir / "logs" / "ok-script.log"

    @property
    def python_dir(self) -> Path:
        return self.app_dir / "python"

    def find_task(self, task_id: str) -> OkScriptTask | None:
        return next((task for task in self.tasks if task.task_id == task_id), None)


def probe_project(root: Path | str) -> OkScriptProject:
    """识别安装目录。

    Args:
        root: 用户选择的安装根目录。

    Returns:
        OkScriptProject: 识别结果。

    Raises:
        OkScriptProjectError: 目录不是可运行的 ok-script 项目，或版本不受支持。
    """

    raw = str(root or "").strip()
    if not raw:
        raise OkScriptProjectError("请先选择 ok-script 项目的安装目录")
    root_path = Path(raw)
    if not root_path.is_dir():
        raise OkScriptProjectError(f"安装目录不存在：{root_path}")

    app_name = _find_app_name(root_path)
    if app_name in DEDICATED_ADAPTERS:
        raise OkScriptProjectError(
            f"{app_name} 已有独立专项，请改用「{DEDICATED_ADAPTERS[app_name]}」脚本类型"
        )

    app_dir = root_path / "data" / "apps" / app_name
    try:
        app_json = read_dict_file(app_dir / "app.json")
    except ConfigCorruptedError as e:
        raise OkScriptProjectError(
            f"{app_name} 的启动器记录已损坏（{e.path.name}），请打开 {app_name}.exe 修复后重试"
        ) from e

    config_path = _find_config_py(app_dir / "repo")
    if config_path is None:
        raise OkScriptProjectError(
            f"未找到 {app_name} 的任务列表，请先打开 {app_name}.exe 完成安装或更新后重试"
        )
    try:
        config_source = config_path.read_text(encoding="utf-8")
        entries, source_version = _parse_config(config_source)
    except (OSError, SyntaxError, UnicodeDecodeError) as e:
        raise OkScriptProjectError(
            f"读取 {app_name} 的任务列表失败（{config_path.name}）：{e}"
        ) from e

    version = str(app_json.get("current_version") or source_version or "未知")
    if entries is None:
        raise OkScriptProjectError(
            f"{app_name} {version} 的任务列表不是可识别的格式，暂不支持该版本"
        )

    repo_dir = app_dir / "repo"
    tasks = tuple(
        OkScriptTask(
            task_id=f"{module}.{class_name}",
            index=index,
            **_read_task_meta(repo_dir, module, class_name),
        )
        for index, (module, class_name) in enumerate(entries, start=1)
    )
    if not tasks:
        raise OkScriptProjectError(f"{app_name} {version} 没有可运行的一次性任务")

    return OkScriptProject(
        root=root_path,
        app_name=app_name,
        version=version,
        tasks=tasks,
        verified=app_name in VERIFIED_APPS,
    )


def _find_app_name(root: Path) -> str:
    """按 pyappify 布局找应用名：``<名>.exe`` 与 ``data/apps/<名>/app.json`` 同时存在。"""

    apps_dir = root / "data" / "apps"
    names = (
        sorted(
            item.name
            for item in apps_dir.iterdir()
            if item.is_dir()
            and (item / "app.json").is_file()
            and (root / f"{item.name}.exe").is_file()
        )
        if apps_dir.is_dir()
        else []
    )
    if not names:
        raise OkScriptProjectError(
            "未识别到 ok-script 项目：请选择项目（如 ok-ef）的安装根目录，"
            "即包含「项目名.exe」和 data 文件夹的那一层"
        )
    if len(names) > 1:
        raise OkScriptProjectError(
            f"该目录下有多个 ok-script 项目（{'、'.join(names)}），无法确定要运行哪一个"
        )
    return names[0]


def _find_config_py(repo_dir: Path) -> Path | None:
    """ok-script 默认按 ``src.config:config``、再按 ``config:config`` 加载项目配置。"""

    for candidate in (repo_dir / "src" / "config.py", repo_dir / "config.py"):
        if candidate.is_file():
            return candidate
    return None


def _parse_config(source: str) -> tuple[list[tuple[str, str]] | None, str | None]:
    """从 config.py 源码里取 ``onetime_tasks`` 与模块级 ``version`` 字面量。

    Returns:
        (任务列表, 版本)：任务列表为 ``[(模块, 类名), ...]``，找不到或不是字面量
        声明时为 None；版本取不到时为 None。
    """

    tree = ast.parse(source)
    entries: list[tuple[str, str]] | None = None
    version: str | None = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
        else:
            continue
        names = {target.id for target in targets if isinstance(target, ast.Name)}
        value = node.value
        if "version" in names and isinstance(value, ast.Constant):
            if isinstance(value.value, str) and value.value.strip():
                version = value.value.strip()
        if "config" in names and isinstance(value, ast.Dict):
            entries = _literal_task_list(value)
    return entries, version


def _literal_task_list(config: ast.Dict) -> list[tuple[str, str]] | None:
    for key, value in zip(config.keys, config.values):
        if not (isinstance(key, ast.Constant) and key.value == "onetime_tasks"):
            continue
        if not isinstance(value, (ast.List, ast.Tuple)):
            return None
        entries: list[tuple[str, str]] = []
        for item in value.elts:
            if not isinstance(item, (ast.List, ast.Tuple)) or len(item.elts) != 2:
                return None
            module, class_name = item.elts
            if not (
                isinstance(module, ast.Constant)
                and isinstance(module.value, str)
                and isinstance(class_name, ast.Constant)
                and isinstance(class_name.value, str)
            ):
                return None
            entries.append((module.value, class_name.value))
        return entries
    return None


def _read_task_meta(repo_dir: Path, module: str, class_name: str) -> dict[str, object]:
    """取任务显示名与是否持续触发；源码读不到或结构不认识时回退为类名。"""

    fallback: dict[str, object] = {"name": class_name, "continuous": False}
    relative = Path(*module.split("."))
    for candidate in (
        repo_dir / relative.with_suffix(".py"),
        repo_dir / relative / "__init__.py",
    ):
        if candidate.is_file():
            break
    else:
        return fallback

    try:
        tree = ast.parse(candidate.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return fallback

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                "name": _task_display_name(node) or class_name,
                "continuous": any(
                    _base_name(base) == _TRIGGER_TASK_BASE for base in node.bases
                ),
            }
    return fallback


def _task_display_name(class_def: ast.ClassDef) -> str | None:
    for item in class_def.body:
        if not (isinstance(item, ast.FunctionDef) and item.name == "__init__"):
            continue
        for node in ast.walk(item):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if (
                    isinstance(target, ast.Attribute)
                    and target.attr == "name"
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)
                    and node.value.value.strip()
                ):
                    return node.value.value.strip()
    return None


def _base_name(base: ast.expr) -> str | None:
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        return base.attr
    return None
