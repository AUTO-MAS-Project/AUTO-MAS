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

"""MFW 内嵌副本：项目根从哪来、副本怎么建、怎么跟着来源走。

MFW 脚本一律在副本上跑，没有开关：用户选一次项目目录，AUTO-MAS 按 interface 白名单
投影出一份只含内置运行所需文件的副本，此后运行、预览、更新全在副本上。副本路径由
脚本 ID 推出，不进配置，用户不可手改；``Info.Path`` 只是来源目录——导入完成后它对
运行没有任何作用，用户删掉也无妨（留着只为「重新导入」）。

老脚本（副本还不存在）与来源换了目录（``Info.Path`` 与导入报告里记的来源不一致）都在
``ensure_embedded_copy`` 里自动导入一次，各入口（运行前检查、预览、更新）都经过它。

副本放在 ``data/mfw/<脚本 uuid 前 12 位>/`` 而不是 ``data/<uuid>/``：后者会被配置备份
整目录快照，几十到两百 MB 的项目副本不该混进去。删脚本时 ``remove_script`` 连带删。

这里全是同步的文件操作，API 与管理器用 ``asyncio.to_thread`` 调。
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import uuid
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.task.MaaFW.tools.core.automas_maafw_project_update.apply import (
    discard_update_baseline,
)
from app.task.MaaFW.tools.core.automas_maafw_project_update.blob_store import (
    RuntimeBlobStore,
)
from app.task.MaaFW.tools.core.automas_maafw_project_update.projection import (
    SHARED_CONTENT_SUFFIXES,
    ProjectionError,
    build_projection_plan,
    materialize_projection,
    read_json_object,
)
from app.task.MaaFW.tools.core.automas_maafw_runtime_pool.host_environment import (
    EMBEDDED_COPIES_DIR_PARTS,
    PROJECT_PYCACHE_DIR_NAME,
)
from app.task.MaaFW.tools.embedded.project_path import (
    release_project_path_sync,
    try_reserve_project_path_sync,
)
from app.utils import get_logger

EMBEDDED_PROJECTS_DIR = Path(*EMBEDDED_COPIES_DIR_PARTS)
logger = get_logger("MFW 内嵌")

# 副本目录名 = 脚本 uuid 去掉连字符的前 12 位（48 位，一个用户几百个脚本撞上的概率可以忽略），
# 仍能从脚本 ID 直接推出、不用查表。不用完整 uuid 只为路径长度，见 EMBEDDED_COPIES_DIR_PARTS。
COPY_DIR_NAME_LENGTH = 12

STAGING_DIR_NAME = ".staging"
# 副本里 Python 字节码缓存的落点（``PYTHONPYCACHEPREFIX``，见 host_environment）：agent 与
# 环境准备写出的 pyc 全在这一个目录下，副本其余部分不再被运行期弄脏；随副本一起删。
PYCACHE_DIR_NAME = PROJECT_PYCACHE_DIR_NAME


class EmbeddedProjectError(RuntimeError):
    """内嵌副本操作失败。文案面向用户，调用方原样带出。"""


def embedded_projects_root(base: Path | None = None) -> Path:
    return (base if base is not None else Path.cwd()) / EMBEDDED_PROJECTS_DIR


def embedded_copy_dir_name(script_id: str) -> str:
    """副本目录名：脚本 uuid 去掉连字符的前 12 位；不是 uuid 形状就拒绝，别让别的东西拼进路径。"""

    normalized = str(script_id or "").strip()
    if not normalized:
        raise EmbeddedProjectError("内嵌副本需要 scriptId")
    try:
        return uuid.UUID(normalized).hex[:COPY_DIR_NAME_LENGTH]
    except ValueError as exc:
        raise EmbeddedProjectError(f"scriptId 不是合法的 uuid：{script_id}") from exc


def is_embedded_copy_dir_name(name: str) -> bool:
    """根目录下一个条目是不是副本目录的名字形状（启动期清理只认这种形状）。"""

    return len(name) == COPY_DIR_NAME_LENGTH and all(
        ch in "0123456789abcdef" for ch in name
    )


def embedded_project_dir(script_id: str, base: Path | None = None) -> Path:
    """副本目录：``data/mfw/<脚本 uuid 前 12 位>``，由脚本 ID 推出、不进配置。"""

    return embedded_projects_root(base) / embedded_copy_dir_name(script_id)


def resolve_maafw_project_root(
    script_id: str, script_config: Any, base: Path | None = None
) -> Path:
    """有效项目根：永远是副本。``Info.Path`` 只是来源，运行时不读它。

    所有"拿项目目录做事"的地方都从这里取，别再各自读 Info.Path。副本可能还没建
    （老脚本、刚选目录），要先经 ``ensure_embedded_copy``。
    """

    del script_config  # 只为与旧调用方签名兼容：有效根不再取决于配置
    return embedded_project_dir(script_id, base)


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
        shared = materialize_projection(
            plan,
            staging_dir,
            progress=progress,
            blob_store=RuntimeBlobStore.default(base),
        )
        if not copy_is_healthy(staging_dir):
            raise EmbeddedProjectError("投影结果里没有 interface.json，拒绝换入")
        if final_dir.exists():
            final_dir.rename(old_dir)
        staging_dir.rename(final_dir)
    except Exception:
        # 先把旧副本放回去，再清半成品：清理本身失败不能连累回滚，也不能盖掉原始异常。
        if old_dir.exists() and not final_dir.exists():
            old_dir.rename(final_dir)
        try:
            remove_tree(staging_dir)
        except OSError as exc:
            logger.warning(f"[MFW 内嵌] 导入半成品清理失败，留待启动时清理: {exc}")
        raise
    try:
        remove_tree(old_dir)
    except OSError as exc:
        logger.warning(f"[MFW 内嵌] 旧副本清理失败，留待启动时清理: {exc}")
    # 树整棵换了，更新器上一次记下的清单已经对不上；不丢掉的话后面每次更新都会
    # 以「文件被本地修改」失败，而且没有别的入口能清它。
    discard_copy_update_baseline(script_id, base)

    report = plan.report()
    report["sourcePath"] = str(source)
    report["copyPath"] = str(final_dir)
    # 与其它副本共用的运行时文件（同内容只在磁盘上存一份）。
    report["sharedFiles"] = shared["sharedFiles"]
    report["sharedBytes"] = shared["sharedBytes"]
    return {
        "report": report,
        "sourceVersion": read_interface_version(final_dir),
        "importedAt": _now_text(),
        "copyPath": str(final_dir),
    }


# 克隆副本时不带的运行期产物：MaaFW 原生日志目录、Python 字节码缓存、导入半成品。
# 这些都是副本跑起来之后自己长出来的，新脚本从零开始更干净，也不会把源脚本的日志带走。
CLONE_SKIP_ROOT_NAMES = frozenset({"debug", STAGING_DIR_NAME})
CLONE_SKIP_DIR_NAMES = frozenset({"__pycache__", PYCACHE_DIR_NAME})


def clone_embedded_copy(
    source_script_id: str, target_script_id: str, base: Path | None = None
) -> bool:
    """从另一个脚本的副本克隆一份给 ``target_script_id``；源没有健康副本就什么都不做，返回是否克隆了。

    共用库里的文件（``st_nlink > 1``，只会被更新器整文件替换、从不原地写）直接再挂一个
    硬链接；源副本里还没入库的模型 / 二进制大文件（在扩大共用面之前导入的老副本）
    经共用库放到新副本，下次源副本重导或更新时也会收敛到同一份；其余文件真复制——
    和导入时的共用规则一致，克隆出来的脚本不会多占运行时与模型那份空间。
    先在 staging 里建好再原子换入：半成品不会被当成健康副本，目标原有的副本（老脚本
    换项目）只在克隆成功后才被换掉，失败时原样放回。
    """

    source_dir = embedded_project_dir(source_script_id, base)
    target_dir = embedded_project_dir(target_script_id, base)
    if not copy_is_healthy(source_dir):
        return False
    staging_root = embedded_projects_root(base) / STAGING_DIR_NAME
    staging_root.mkdir(parents=True, exist_ok=True)
    staging_dir = staging_root / f"{target_dir.name}-{uuid.uuid4().hex[:8]}"
    old_dir = staging_root / f"{target_dir.name}-old-{uuid.uuid4().hex[:8]}"
    blob_store = RuntimeBlobStore.default(base)

    def _walk_error(exc: OSError) -> None:
        # 读不了的子目录不能静默跳过：那会产出一份缺子树却「健康」的副本。
        raise EmbeddedProjectError(f"复制副本失败: {exc.filename}: {exc}") from exc

    try:
        for current_root, dir_names, file_names in os.walk(
            source_dir, onerror=_walk_error
        ):
            relative = Path(current_root).relative_to(source_dir)
            dir_names[:] = sorted(
                name
                for name in dir_names
                if name not in CLONE_SKIP_DIR_NAMES
                and not (relative == Path() and name in CLONE_SKIP_ROOT_NAMES)
            )
            (staging_dir / relative).mkdir(parents=True, exist_ok=True)
            for name in file_names:
                src = Path(current_root) / name
                dst = staging_dir / relative / name
                try:
                    info = src.stat()
                    if info.st_nlink > 1:
                        try:
                            os.link(src, dst)
                            continue
                        except OSError:
                            pass
                    if (
                        blob_store.eligible(info.st_size)
                        and src.suffix.lower() in SHARED_CONTENT_SUFFIXES
                    ):
                        blob_store.place(src, dst)
                        continue
                    shutil.copy2(src, dst)
                except OSError as exc:
                    raise EmbeddedProjectError(
                        f"复制副本失败: {src.name}: {exc}"
                    ) from exc
        if not copy_is_healthy(staging_dir):
            raise EmbeddedProjectError("克隆结果里没有 interface.json，拒绝换入")
        if target_dir.exists():
            target_dir.rename(old_dir)
        staging_dir.rename(target_dir)
    except Exception:
        if old_dir.exists() and not target_dir.exists():
            old_dir.rename(target_dir)
        try:
            remove_tree(staging_dir)
        except OSError as exc:
            logger.warning(f"[MFW 内嵌] 克隆半成品清理失败，留待启动时清理: {exc}")
        raise
    try:
        remove_tree(old_dir)
    except OSError as exc:
        logger.warning(f"[MFW 内嵌] 旧副本清理失败，留待启动时清理: {exc}")
    # 目标的树整棵换了，更新器上一次记下的清单已经对不上（与重新导入同理）。
    discard_copy_update_baseline(target_script_id, base)
    return True


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
        "copyPath": str(copy_dir),
        "copyHealthy": copy_is_healthy(copy_dir),
        "sourcePath": source,
        "sourceExists": bool(source) and Path(source).is_dir(),
        "sourceVersion": str(script_config.get("Embedded", "SourceVersion") or ""),
        "importedAt": str(script_config.get("Embedded", "ImportedAt") or ""),
        "report": report,
    }


def imported_source_path(script_config: Any) -> str:
    """导入报告里记的来源目录；没导入过（老脚本）时为空。"""

    raw = script_config.get("Embedded", "Report")
    report: Any = raw
    if isinstance(raw, str):
        try:
            report = json.loads(raw) if raw.strip() else {}
        except ValueError:
            return ""
    if not isinstance(report, dict):
        return ""
    return str(report.get("sourcePath") or "").strip()


def _same_directory(left: str, right: str) -> bool:
    if not left or not right:
        return False
    try:
        return os.path.normcase(str(Path(left).resolve())) == os.path.normcase(
            str(Path(right).resolve())
        )
    except OSError:
        return False


def inherit_embedded_record(
    source_config: Any, target_script_id: str, base: Path | None = None
) -> dict[str, Any]:
    """从源脚本克隆副本之后，目标该写进 ``Embedded.*`` 的记录：报告沿用源的（``copyPath``
    改成自己的），来源版本沿用源记的（没有就读副本 interface），导入时间取现在。"""

    target_dir = embedded_project_dir(target_script_id, base)
    raw = source_config.get("Embedded", "Report")
    report: Any = {}
    if isinstance(raw, str):
        try:
            report = json.loads(raw) if raw.strip() else {}
        except ValueError:
            report = {}
    elif isinstance(raw, dict):
        report = dict(raw)
    if not isinstance(report, dict):
        report = {}
    report["copyPath"] = str(target_dir)
    return {
        "report": report,
        "sourceVersion": str(source_config.get("Embedded", "SourceVersion") or "")
        or read_interface_version(target_dir),
        "importedAt": _now_text(),
        "copyPath": str(target_dir),
    }


def _clone_from_sibling(
    script_id: str,
    source: str,
    siblings: Iterable[tuple[str, Any]],
    *,
    base: Path | None,
    send_log: Callable[[str], None] | None,
) -> dict[str, Any] | None:
    """来源目录已删、副本又没了：找一个同来源、副本健康的脚本克隆过来。找不到返回 None。"""

    for other_id, other_config in siblings:
        other_id = str(other_id)
        if other_id == script_id:
            continue
        other_source = imported_source_path(other_config) or str(
            other_config.get("Info", "Path") or ""
        )
        if not other_source or not _same_directory(source, other_source):
            continue
        other_dir = embedded_project_dir(other_id, base)
        if not copy_is_healthy(other_dir):
            continue
        # 源副本正在更新 / 准备环境时不能克隆半截树；换下一个同来源的脚本。
        key = try_reserve_project_path_sync(other_dir)
        if key is None:
            continue
        try:
            if not clone_embedded_copy(other_id, script_id, base):
                continue
        finally:
            release_project_path_sync(key)
        other_name = str(other_config.get("Info", "Name") or other_id[:8])
        message = f"[MFW 内嵌] 来源目录已不存在，已从脚本「{other_name}」的副本克隆"
        logger.info(message)
        if send_log is not None:
            send_log(message)
        return inherit_embedded_record(other_config, script_id, base)
    return None


def ensure_embedded_copy(
    script_id: str,
    script_config: Any,
    *,
    base: Path | None = None,
    send_log: Callable[[str], None] | None = None,
    siblings: Iterable[tuple[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """副本不在（老脚本、被删）或来源换了目录时导入一次；返回新报告，否则 None。

    调用方拿到非 None 要把报告写回配置。来源目录不在：副本还健康就什么都不做——
    导入完成后来源本来就可以删；副本也没了就在 ``siblings``（其它 MFW 脚本）里找同来源、
    副本健康的克隆一份，实在没有才抛错让用户重新选目录。
    """

    copy_dir = embedded_project_dir(script_id, base)
    healthy = copy_is_healthy(copy_dir)
    source = str(script_config.get("Info", "Path") or "").strip()
    if healthy and (
        not source or _same_directory(source, imported_source_path(script_config))
    ):
        return None
    if not source:
        raise EmbeddedProjectError("还没有选择 MFW 项目目录")
    if not Path(source).is_dir():
        if healthy:
            # 来源目录换成了一个不存在的路径：副本还是上一个来源的，照常用它。
            return None
        rebuilt = _clone_from_sibling(
            script_id, source, siblings or (), base=base, send_log=send_log
        )
        if rebuilt is not None:
            return rebuilt
        raise EmbeddedProjectError(
            "副本不在了，来源目录也已不存在；请重新选择一个解压好的 MFW 项目目录"
        )
    if send_log is not None:
        send_log(
            "[MFW 内嵌] 正在从来源目录导入副本"
            if not healthy
            else "[MFW 内嵌] 来源目录已更换，正在重新导入副本"
        )
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
    "PYCACHE_DIR_NAME",
    "EmbeddedProjectError",
    "clone_embedded_copy",
    "copy_is_healthy",
    "discard_copy_update_baseline",
    "embedded_project_dir",
    "embedded_projects_root",
    "embedded_status",
    "ensure_embedded_copy",
    "import_embedded_project",
    "imported_source_path",
    "inherit_embedded_record",
    "read_interface_version",
    "remove_tree",
    "resolve_maafw_project_root",
    "shell_hint_from_report",
]
