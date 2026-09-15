#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""MFW 内嵌副本：项目根从哪来、副本怎么建、怎么退。

用户为 MFW 脚本选一次项目目录，AUTO-MAS 按 interface 白名单投影出一份只含内置运行
所需文件的副本，此后运行、预览、更新全在副本上。副本路径由脚本 ID 推出，不进配置，
用户不可手改；``Info.Path`` 继续存来源目录，退出内嵌就回到它。

副本放在 ``data/maafw_projects/<uuid>/`` 而不是 ``data/<uuid>/``：后者会被配置备份
整目录快照，几十到两百 MB 的项目副本不该混进去。删脚本时 ``remove_script`` 连带删。

这里全是同步的文件操作，API 与管理器用 ``asyncio.to_thread`` 调。
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.task.MaaFW.tools.core.automas_maafw_project_update.apply import (
    discard_update_baseline,
)
from app.task.MaaFW.tools.core.automas_maafw_project_update.projection import (
    ProjectionError,
    build_projection_plan,
    materialize_projection,
    read_json_object,
)

EMBEDDED_PROJECTS_DIR = Path("data") / "maafw_projects"
STAGING_DIR_NAME = ".staging"


class EmbeddedProjectError(RuntimeError):
    """内嵌副本操作失败。文案面向用户，调用方原样带出。"""


def embedded_projects_root(base: Path | None = None) -> Path:
    return (base if base is not None else Path.cwd()) / EMBEDDED_PROJECTS_DIR


def embedded_project_dir(script_id: str, base: Path | None = None) -> Path:
    """副本目录。用完整 uuid：与 data/<uuid>/ 同一套身份，找起来不用查表。"""

    normalized = str(script_id or "").strip()
    if not normalized:
        raise EmbeddedProjectError("内嵌副本需要 scriptId")
    # 只允许 uuid 形状，防止拼进路径里的东西不是脚本 ID。
    try:
        normalized = str(uuid.UUID(normalized))
    except ValueError as exc:
        raise EmbeddedProjectError(f"scriptId 不是合法的 uuid：{script_id}") from exc
    return embedded_projects_root(base) / normalized


def is_embedded(script_config: Any) -> bool:
    try:
        return bool(script_config.get("Embedded", "Enabled"))
    except Exception:  # noqa: BLE001 - 旧配置对象缺项不该挡住运行
        return False


def resolve_maafw_project_root(
    script_id: str, script_config: Any, base: Path | None = None
) -> Path:
    """有效项目根：内嵌时是副本，否则是用户选的 Info.Path。

    所有"拿项目目录做事"的地方都从这里取，别再各自读 Info.Path。
    """

    if is_embedded(script_config):
        return embedded_project_dir(script_id, base)
    return Path(str(script_config.get("Info", "Path") or "").strip())


def _clear_readonly_and_retry(
    func: Callable[[str], Any], path: str, _exc_info: Any
) -> None:
    os.chmod(path, stat.S_IWRITE)
    func(path)


def remove_tree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, onexc=_clear_readonly_and_retry)


def _update_operation_root(base: Path | None) -> Path:
    """更新器的 operation 根；与 ``project_update/state.py`` 的默认值同一口径。"""

    return (
        (base if base is not None else Path.cwd()) / "data" / "maafw_update_operations"
    )


def discard_copy_update_baseline(script_id: str, base: Path | None = None) -> bool:
    """副本被整体换掉（重新导入）或删掉（退出内嵌）之后，丢掉更新器记的清单。"""

    return discard_update_baseline(
        embedded_project_dir(script_id, base),
        operation_root=_update_operation_root(base),
    )


def copy_is_healthy(copy_dir: Path) -> bool:
    return (copy_dir / "interface.json").is_file() or (
        copy_dir / "interface.jsonc"
    ).is_file()


def read_interface_version(project_dir: Path) -> str:
    for name in ("interface.json", "interface.jsonc"):
        candidate = project_dir / name
        if candidate.is_file():
            try:
                return str(
                    read_json_object(candidate, "ProjectInterface").get("version") or ""
                )
            except ProjectionError:
                return ""
    return ""


def _now_text() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def import_embedded_project(
    script_id: str,
    source_path: str | Path,
    *,
    base: Path | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """把来源目录投影成副本。先在 staging 里建好，再原子换到正式位置。

    返回值直接写进 ``Embedded.*``：``report`` / ``sourceVersion`` / ``importedAt``。
    失败时 staging 被清掉、正式位置原样不动——重新导入失败不会把旧副本弄没。
    """

    source = Path(str(source_path or "").strip())
    if not source.is_absolute() or not source.is_dir():
        raise EmbeddedProjectError(
            "来源目录不存在或不是绝对路径，请先在项目路径里选一个 MFW 项目目录"
        )
    source = source.resolve()
    final_dir = embedded_project_dir(script_id, base)
    root = embedded_projects_root(base)
    if _is_relative_to(source, root):
        raise EmbeddedProjectError("来源目录不能是内嵌副本自己")

    try:
        plan = build_projection_plan(source)
    except ProjectionError as exc:
        raise EmbeddedProjectError(f"导入失败：{exc}") from exc

    staging_root = root / STAGING_DIR_NAME
    staging_root.mkdir(parents=True, exist_ok=True)
    staging_dir = staging_root / f"{final_dir.name}-{uuid.uuid4().hex[:8]}"
    old_dir = staging_root / f"{final_dir.name}-old-{uuid.uuid4().hex[:8]}"
    try:
        materialize_projection(plan, staging_dir, progress=progress)
        if not copy_is_healthy(staging_dir):
            raise EmbeddedProjectError("投影结果里没有 interface.json，拒绝换入")
        if final_dir.exists():
            final_dir.rename(old_dir)
        staging_dir.rename(final_dir)
    except Exception:
        remove_tree(staging_dir)
        if old_dir.exists() and not final_dir.exists():
            old_dir.rename(final_dir)
        raise
    remove_tree(old_dir)
    # 树整棵换了，更新器上一次记下的清单已经对不上；不丢掉的话后面每次更新都会
    # 以「文件被本地修改」失败，而且没有别的入口能清它。
    discard_copy_update_baseline(script_id, base)

    report = plan.report()
    report["sourcePath"] = str(source)
    report["copyPath"] = str(final_dir)
    return {
        "report": report,
        "sourceVersion": read_interface_version(final_dir),
        "importedAt": _now_text(),
        "copyPath": str(final_dir),
    }


def embedded_status(
    script_id: str, script_config: Any, *, base: Path | None = None
) -> dict[str, Any]:
    """给界面看的状态：开没开、副本健不健康、来源还在不在、报告。"""

    copy_dir = embedded_project_dir(script_id, base)
    source = str(script_config.get("Info", "Path") or "").strip()
    raw_report = script_config.get("Embedded", "Report")
    report: dict[str, Any] = {}
    if isinstance(raw_report, dict):
        report = raw_report
    elif isinstance(raw_report, str) and raw_report.strip():
        try:
            parsed = json.loads(raw_report)
            report = parsed if isinstance(parsed, dict) else {}
        except ValueError:
            report = {}
    return {
        "enabled": is_embedded(script_config),
        "copyPath": str(copy_dir),
        "copyHealthy": copy_is_healthy(copy_dir),
        "sourcePath": source,
        "sourceExists": bool(source) and Path(source).is_dir(),
        "sourceVersion": str(script_config.get("Embedded", "SourceVersion") or ""),
        "importedAt": str(script_config.get("Embedded", "ImportedAt") or ""),
        "report": report,
    }


def ensure_embedded_copy(
    script_id: str,
    script_config: Any,
    *,
    base: Path | None = None,
    send_log: Callable[[str], None] | None = None,
) -> dict[str, Any] | None:
    """内嵌模式下副本缺失或损坏时，来源还在就重新投影一次；返回新报告，否则 None。

    调用方拿到非 None 要把报告写回配置。来源不在则抛错说明——副本没了又没处重建。
    """

    if not is_embedded(script_config):
        return None
    copy_dir = embedded_project_dir(script_id, base)
    if copy_is_healthy(copy_dir):
        return None
    source = str(script_config.get("Info", "Path") or "").strip()
    if not source or not Path(source).is_dir():
        raise EmbeddedProjectError(
            "内嵌副本缺失，且来源目录已不存在；请重新选择项目目录后再导入"
        )
    if send_log is not None:
        send_log("[MFW 内嵌] 副本缺失或损坏，正在从来源目录重新导入")
    return import_embedded_project(script_id, source, base=base)


def shell_hint_from_report(script_config: Any) -> str:
    """副本里没有 MFW.exe 可扫，外壳家族只能从导入报告取。"""

    raw = script_config.get("Embedded", "Report")
    report: Any = raw
    if isinstance(raw, str):
        try:
            report = json.loads(raw) if raw.strip() else {}
        except ValueError:
            return ""
    if not isinstance(report, dict):
        return ""
    families = report.get("shellFamilies")
    if not isinstance(families, list):
        return ""
    present = {str(item).strip() for item in families}
    for family in ("MXU", "MFAAvalonia", "MFW", "CFA", "MaaPiCli"):
        if family in present:
            return family
    return ""


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


__all__ = [
    "EMBEDDED_PROJECTS_DIR",
    "EmbeddedProjectError",
    "copy_is_healthy",
    "discard_copy_update_baseline",
    "embedded_project_dir",
    "embedded_projects_root",
    "embedded_status",
    "ensure_embedded_copy",
    "import_embedded_project",
    "is_embedded",
    "read_interface_version",
    "remove_tree",
    "resolve_maafw_project_root",
    "shell_hint_from_report",
]
