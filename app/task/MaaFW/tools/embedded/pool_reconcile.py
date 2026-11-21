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

"""MFW 运行池与 agent 隔离 venv 的引用对账回收（宿主侧，agent 环境这一块）。

这里只收普通数据：调用方（项目更新一侧，``live_projects.py``、``maintenance.py``）先在事件
循环上算好「应保留的项目路径集合」与「本次被替换下来的 maafw 版本」交进来，这里不读脚本配置、
不碰项目副本。

运行池（``config/maafw_runtime_pool/runtimes/<id>``）按「requirement 集合 + 宿主
解释器身份」建 runtime，此前的回收只按 ``lastUsedAt`` 宽限 + 保留最新一个，且每个
进程只在第一次准备环境时跑一次——实测从没真正清掉过东西：项目升级换了 maafw
版本、宿主换了随包 Python、以及 runner venv 曾把项目 requirements.txt 折进身份而
裂出来的那些副本，全都永远留在盘上（测试包里 9 个 runtime、519 MB）。

这里改成按引用对账：

1. 权威集合 = 所有 MaaFW 类脚本的项目目录（由调用方给），每个项目用
   ``describe_runner_runtime_selection`` 算出借运行环境（``borrow_runtime_environment``）
   会选中的 runtime id 与 maafw requirement——两边走同一批 helper，算出来的就是运行时
   会用的那一个。
2. 交给 ``MaaFWRuntimePool.reclaim_stale_runtimes``：不在权威集合里的 runtime、
   binding、native 与作废缓存按各自的判据删（旧布局 runtime 先就地收割 binding；
   在用的靠租约 / 进程内引用计数保护；其余过 24 h 宽限或本轮被替换才删）。
3. 池里已无旧身份 runtime 时顺手 ``uv cache clean``：runtime 是从池自己的 uv
   缓存硬链接出来的，旧 runtime 删掉后那些文件就只剩缓存这一份，不清等于没删。
   仍有旧 runtime 在等新身份替换时不清，保住离线用户靠缓存重建的能力。

核心包 ``runtime_pool`` 不读 ``Config``，权威集合由项目更新一侧算好交进来。与
:func:`reconcile_agent_venvs` 同一套保守规则：任一存活项目此刻不可达、任一
项目算不出 selection、托管解释器还没装（算不出身份），整轮弃权——回收晚一轮
没有代价，误删一份 runtime 要重下几十到上百 MB。
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.task.MaaFW.tools.core.agent_env.planner import collect_orphan_agent_venvs
from app.task.MaaFW.tools.core.agent_env.runtime_lease import (
    describe_runner_runtime_selection,
)
from app.task.MaaFW.tools.core.agent_env.venv_share import (
    collect_stale_venv_refs,
    discard_venv_lock_file,
    isolated_venv_guard,
)
from app.task.MaaFW.tools.core.native.requirement import (
    resolve_project_maafw_requirement,
)
from app.task.MaaFW.tools.core.runtime_pool import MaaFWRuntimePoolService
from app.task.MaaFW.tools.core.runtime_pool.binding import (
    prune_selections,
    retained_versions,
)
from app.task.MaaFW.tools.core.runtime_pool.identity import infer_exact_maafw_version
from app.utils import get_logger

logger = get_logger("MFW 运行池回收")
# 隔离 venv 回收的日志沿用原先的 logger 名（那段代码原先在 ``maintenance.py`` 里）。
_venv_logger = get_logger("MFW 维护")

_RECONCILE_LOCK = threading.Lock()

# 刚动过的 venv 不碰，避免与正在准备环境的运行抢。
MAAFW_AGENT_VENV_GRACE_SECONDS = 60 * 60


def runtime_pool_root() -> Path:
    """池根，与 ``MaaFWRuntimePoolService`` 的默认值一致。"""

    return Path.cwd() / "config" / "maafw_runtime_pool"


def agent_venvs_root() -> Path:
    """agent 隔离 venv 的根（``config/maafw_agent_venvs``）。"""

    return Path.cwd() / "config" / "maafw_agent_venvs"


def reconcile_agent_venvs(live_paths: list[str]) -> None:
    """清掉已无存活视图引用的 agent 隔离 venv 与无主的引用记录。

    ``live_paths`` 是存活脚本的有效项目根（调用方已去掉还没导入过、目录不存在的）。
    存活集合按各存活视图的引用记录（准备时写在 ``.refs/`` 下）、建计划时会算出的目录、
    以及还没准备过的视图升级前按路径建的老目录算，不读 venv 目录内的清单；存活视图的
    引用记录读不出来就整轮不回收（见 ``agent_env.planner.collect_orphan_agent_venvs``）。
    再加两道保护——刚动过的一律不碰；正被准备（锁文件被占）的也不碰，避免与正在
    准备环境的运行抢。不属于任何存活视图的引用记录一并删掉。
    """

    root = agent_venvs_root()
    try:
        orphans = collect_orphan_agent_venvs(root, live_paths)
    except Exception as exc:
        _venv_logger.warning(f"MFW 隔离 venv 孤儿扫描失败: {exc}")
        return

    cutoff = time.time() - MAAFW_AGENT_VENV_GRACE_SECONDS
    for venv_path in orphans:
        try:
            if venv_path.stat().st_mtime > cutoff:
                continue  # 刚动过，可能有运行正在用它
            with isolated_venv_guard(venv_path, blocking=False) as locked:
                if not locked:
                    _venv_logger.info(
                        f"MFW 隔离 venv 正在被准备，本次不清理: {venv_path}"
                    )
                    continue
                shutil.rmtree(venv_path)
        except OSError as exc:
            _venv_logger.warning(f"MFW 隔离 venv 清理失败: {venv_path} - {exc}")
            continue
        # 锁文件出了锁才删得掉（Windows 上开着的文件删不了）
        discard_venv_lock_file(venv_path)
        _venv_logger.info(f"已清理无人引用的 MFW 隔离 venv: {venv_path}")

    try:
        stale_refs = collect_stale_venv_refs(root, live_paths)
    except Exception as exc:
        _venv_logger.warning(f"MFW 隔离 venv 引用记录扫描失败: {exc}")
        return
    for ref_path in stale_refs:
        try:
            ref_path.unlink(missing_ok=True)
        except OSError as exc:
            _venv_logger.warning(f"MFW 隔离 venv 引用记录清理失败: {ref_path} - {exc}")
            continue
        _venv_logger.debug(f"已清理无主的 MFW 隔离 venv 引用记录: {ref_path}")


def reconcile_runtime_pool(
    project_paths: Iterable[str | Path],
    *,
    replaced_versions: Iterable[str] = (),
    reason: str = "",
    dry_run: bool = False,
) -> dict[str, Any] | None:
    """按权威集合对账一轮运行池；返回池的回收报告，弃权时返回 ``None``。

    阻塞调用（要起解释器探针、可能跑 ``uv cache clean``），放线程里跑。同一进程
    里同时只跑一轮：另一轮正在跑时**直接丢弃、不排队**——权威集合是全局状态，
    后到的那轮看到的和正在跑的没区别；丢掉的那轮想清的东西最晚下次启动清。

    任一项目算不出 selection 时整轮弃权，而且这是**永久性**的：只要那个项目的
    ``requirements.txt`` 一直声明两行 maafw / 一直不是 UTF-8，回收就一直不跑。
    这种项目 prepare 同样会报同一个错，用户在运行它时会看到；日志里每轮都会点名。
    """

    if not _RECONCILE_LOCK.acquire(blocking=False):
        logger.debug(f"MFW 运行池回收已在进行，跳过本次（{reason or '未注明'}）")
        return None
    try:
        return _reconcile(
            [str(path) for path in project_paths],
            replaced_versions=[str(item) for item in replaced_versions],
            reason=reason or "未注明",
            dry_run=dry_run,
        )
    finally:
        _RECONCILE_LOCK.release()


def _reconcile(
    project_paths: list[str],
    *,
    replaced_versions: list[str],
    reason: str,
    dry_run: bool,
) -> dict[str, Any] | None:
    root = runtime_pool_root()
    if not (root / "runtimes").is_dir():
        return None

    # 与隔离 venv 清理同一条规则：开机自启动早于网络盘挂载时项目路径还不可达，
    # 此时算不出它的 selection，分不清的时候不删。
    unreachable = [path for path in project_paths if not Path(path).is_dir()]
    if unreachable:
        logger.info(
            "MFW 运行池回收已跳过：以下项目路径当前不可达，"
            f"无法可靠判定归属: {unreachable[:3]}"
        )
        return None

    try:
        pool = MaaFWRuntimePoolService().pool
    except Exception as exc:  # noqa: BLE001 - 池本身有问题时不回收
        logger.warning(f"MFW 运行池回收已跳过：池初始化失败: {exc}")
        return None

    valid_runtime_ids: set[str] = set()
    binding_versions: set[str] = set()
    native_versions: set[str] = set()
    unresolved: list[str] = []
    for path in project_paths:
        try:
            selection = describe_runner_runtime_selection(path, pool)
        except Exception as exc:  # noqa: BLE001 - 单个项目算不出就整轮弃权
            logger.warning(
                f"MFW 运行池回收已跳过：项目 {path} 的 runtime 归属算不出来: {exc}"
            )
            return None
        if selection is None:
            logger.info(
                "MFW 运行池回收已跳过：池内托管解释器尚未就绪，无法判定 runtime 身份"
            )
            return None
        valid_runtime_ids.add(selection.runtime_id)
        if selection.binding_version is None:
            # 范围声明且本地还定不下来：它的 binding 还没建，靠宽限兜住即可
            unresolved.append(path)
            continue
        binding_versions.add(selection.binding_version)
        if selection.native_needed:
            native_versions.add(selection.binding_version)
    if unresolved:
        logger.debug(
            f"MFW 运行池回收：{len(unresolved)} 个项目的 binding 版本尚未定下（范围声明、"
            f"本地无候选），只靠宽限保护: {unresolved[:3]}"
        )

    try:
        if not dry_run:
            prune_selections(pool.root, project_paths)
        report = pool.reclaim_stale_runtimes(
            valid_runtime_ids=valid_runtime_ids,
            binding_versions=binding_versions,
            native_versions=native_versions,
            replaced_versions=replaced_versions,
            retained_versions=retained_versions(pool.root),
            dry_run=dry_run,
        )
    except Exception as exc:  # noqa: BLE001 - 回收失败不该影响调用方
        logger.warning(f"MFW 运行池回收失败（{reason}）: {exc}")
        return None

    deleted = list(report.get("deleted") or [])
    quarantined = list(report.get("quarantined") or [])
    kept = list(report.get("kept") or [])
    skipped = list(report.get("skipped") or [])
    errors = list(report.get("errors") or [])
    harvested = list(report.get("harvested") or [])
    bindings_deleted = list(report.get("bindingsDeleted") or [])
    cache_deleted = list(report.get("cacheDeleted") or [])
    remaining = list(report.get("remainingLegacy") or [])
    swept = list(report.get("stagingSwept") or [])
    staging_residue = list(report.get("stagingResidue") or [])
    verb = "将清理" if dry_run else "已清理"
    for item in harvested:
        status = item.get("status")
        if status == "harvested":
            logger.info(
                f"MFW 运行池回收：已从旧运行环境 {item.get('runtimeId')} 收割 maafw "
                f"{item.get('version')} 的 binding（零下载）"
            )
        else:
            logger.warning(
                f"MFW 运行池回收：旧运行环境 {item.get('runtimeId')} 里 maafw "
                f"{item.get('version')} 的 binding 收割失败（{status}），"
                f"下次准备环境时改为下载: {item.get('error') or ''}"
            )
    if deleted:
        logger.info(
            f"MFW 运行池回收（{reason}）：{verb}无人引用的 runtime {len(deleted)} 个: "
            + ", ".join(deleted)
        )
    if bindings_deleted:
        logger.info(
            f"MFW 运行池回收（{reason}）：{verb}无人引用的 binding / 原生库 "
            f"{len(bindings_deleted)} 个: " + ", ".join(bindings_deleted)
        )
    if cache_deleted:
        logger.info(
            f"MFW 运行池回收（{reason}）：{verb}作废缓存 {len(cache_deleted)} 项: "
            + ", ".join(cache_deleted)
        )
    for item in quarantined:
        logger.warning(
            f"MFW 运行池回收：{item.get('runtimeId') or item.get('entry')} 已移出池但有"
            f"文件删不掉（多半还被进程映射着），残留在 {item.get('path')}，下次启动再清"
        )
    if staging_residue:
        logger.warning(
            "MFW 运行池回收：staging 里仍有删不掉的残留，下次再清: "
            + ", ".join(staging_residue)
        )
    if kept:
        logger.debug(
            f"MFW 运行池回收（{reason}）：{len(kept)} 个旧 runtime 暂留: "
            + "; ".join(
                f"{item.get('runtimeId')}[{','.join(item.get('reasons') or [])}]"
                for item in kept
            )
        )
    for item in skipped:
        logger.warning(
            f"MFW 运行池回收：{item.get('runtimeId') or item.get('entry')} 本轮删不掉，"
            f"下次再试: {item.get('error')}"
        )
    for item in errors:
        logger.warning(
            f"MFW 运行池回收：runtime {item.get('runtimeId')} 的 manifest 有问题，"
            f"已跳过: {item.get('error')}"
        )
    if swept:
        logger.info(f"MFW 运行池回收：已清掉 staging 残留 {len(swept)} 个")
    freed_bytes = int(report.get("freedBytes") or 0)
    cache_shared_bytes = int(report.get("cacheSharedBytes") or 0)
    if freed_bytes or cache_shared_bytes:
        # 独占文件删了就腾出来；uv 从缓存硬链接进 venv 的那些要等清缓存那一行
        logger.info(
            f"MFW 运行池回收（{reason}）：{'将' if dry_run else '已'}释放 "
            f"{_format_mb(freed_bytes)}"
            + (
                f"（另有 {_format_mb(cache_shared_bytes)} 与 uv 缓存共用，清缓存时释放）"
                if cache_shared_bytes
                else ""
            )
        )

    # D8：只有池里已无旧布局 runtime、当前身份的 base 已经建好时才清缓存。旧 runtime
    # 还在等替换时不清、base 还没建时也不清（升级后第一次启动就把旧布局全收割掉了，
    # base 要靠这份缓存离线建出来）。「有东西该清」这件事要**记在盘上**：升级后第一
    # 轮删光旧布局时 base 还没建、清不了，等 base 建好的那一轮又什么都没删——只看
    # 本轮删没删，缓存会永远留着（测试包上就这么留了 490 MB）。
    removed_something = bool(deleted or bindings_deleted or cache_deleted or swept)
    if dry_run:
        return report
    pending = _cache_clean_pending_path(pool.root)
    if removed_something and not pending.exists():
        try:
            pending.write_text(
                json.dumps({"reason": reason, "markedAt": _now_text()}),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.debug(f"MFW 运行池：写缓存待清理标记失败: {exc}")
    # 布局 v2 落地后每个池至少清一次：删旧布局那一轮可能跑在还不写标记的老代码上
    # （测试包就是），那份缓存没有别的机会被清掉。清过一次记个戳，之后只看标记。
    done_stamp = _cache_clean_done_path(pool.root)
    first_clean_due = not done_stamp.exists() and _has_files(pool.root / "cache" / "uv")
    if not (removed_something or pending.exists() or first_clean_due):
        return report
    if remaining:
        logger.debug("MFW 运行池：仍有旧布局 runtime 待替换，uv 缓存留待下次清理")
        return report
    if not all(_runtime_usable(pool, runtime_id) for runtime_id in valid_runtime_ids):
        logger.debug("MFW 运行池：当前身份的 base 尚未建好，uv 缓存留待下次清理")
        return report
    try:
        cache = pool.clean_cache()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"MFW 运行池 uv 缓存清理失败: {exc}")
        return report
    report["cacheClean"] = cache
    status = str(cache.get("status") or "unknown")
    if status == "cleaned":
        removed_bytes = int(cache.get("removedBytes") or 0)
        logger.info(
            f"MFW 运行池 uv 缓存已清理，释放 {_format_mb(removed_bytes)}: "
            f"removedFiles={int(cache.get('removedFiles') or 0)}, "
            f"removedBytes={removed_bytes}"
        )
    elif status == "skipped":
        # managed 安装：缓存是 Runtime 注入的共享目录，归它管。这里必须留痕，
        # 否则用户在这类安装上看不到「旧 runtime 删了但包文件还在缓存里」。
        logger.info(
            "MFW 运行池 uv 缓存未清理：缓存由 Runtime 注入共享，交给 Runtime 维护"
            f"（{cache.get('cachePath')}）"
        )
    elif status in {"error", "unavailable", "unsafe"}:
        logger.warning(
            f"MFW 运行池 uv 缓存未清理: status={status}, "
            f"error={cache.get('error') or 'no detail'}"
        )
    if status in {"cleaned", "absent", "skipped"}:
        # 清过了 / 没有可清的 / 不归我们清：标记撤掉、记戳；出错的留着下次再试
        try:
            pending.unlink(missing_ok=True)
            done_stamp.write_text(
                json.dumps({"status": status, "cleanedAt": _now_text()}),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.debug(f"MFW 运行池：更新缓存清理标记失败: {exc}")
    return report


def _format_mb(value: int) -> str:
    return f"{value / (1024 * 1024):.1f} MB"


def _cache_clean_pending_path(pool_root: Path) -> Path:
    return Path(pool_root) / ".uv-cache-clean-pending"


def _cache_clean_done_path(pool_root: Path) -> Path:
    return Path(pool_root) / ".uv-cache-clean-done"


def _has_files(directory: Path) -> bool:
    if not directory.is_dir():
        return False
    for _dirpath, _dirs, files in os.walk(directory):
        if files:
            return True
    return False


def _now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _runtime_usable(pool: Any, runtime_id: str) -> bool:
    """当前身份的 base 在不在池里、能不能用（``pool.get`` 会真起一次解释器核 ABI）。"""

    try:
        return pool.get(runtime_id) is not None
    except Exception:  # noqa: BLE001 - ABI 对不上等同不可用
        return False


def previous_maafw_version(project_path: str | Path) -> str | None:
    """项目更新前记下它当前钉定的 maafw 精确版本（范围声明或读不出时为 None）。

    更新提交后拿它与新版本比：版本换了就把旧版本作为 ``replaced_versions`` 传给
    回收，旧 runtime 不必再等 24 h 宽限。
    """

    try:
        requirement = resolve_project_maafw_requirement(Path(project_path))
    except Exception:  # noqa: BLE001 - 读不出来就当没有精确版本
        return None
    return infer_exact_maafw_version(requirement)


def reconcile_after_project_update(
    project_paths: Iterable[str | Path],
    project_path: str | Path,
    previous_version: str | None,
    *,
    reason: str = "project-update",
) -> dict[str, Any] | None:
    """项目更新提交之后跑一轮回收；maafw 版本换了就豁免旧版本的宽限。

    提交前的运行环境预检已经把新版本的 runtime 建好了（见
    ``tools/embedded/precheck.py``），所以此时删旧的不会让项目暂时跑不了。
    阻塞调用，放线程里跑；``project_paths`` 是权威集合，由调用方在事件循环
    线程上先算好传进来（``live_projects.reconcile_in_background``）。
    """

    replaced: list[str] = []
    if previous_version:
        current_version = previous_maafw_version(project_path)
        paths = list(project_paths)
        # 同一项目的多个视图挂同一个载荷，运行中的兄弟要跑完才切：旧版本只有在
        # 谱系里最后一个视图也离开它之后才算「被替换」，否则豁免宽限会删掉正在用的。
        still_used = any(
            previous_maafw_version(path) == previous_version for path in paths
        )
        if current_version != previous_version and not still_used:
            replaced.append(previous_version)
        project_paths = paths
    return reconcile_runtime_pool(
        project_paths,
        replaced_versions=replaced,
        reason=reason,
    )


__all__ = [
    "MAAFW_AGENT_VENV_GRACE_SECONDS",
    "agent_venvs_root",
    "previous_maafw_version",
    "reconcile_after_project_update",
    "reconcile_agent_venvs",
    "reconcile_runtime_pool",
    "runtime_pool_root",
]
