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

"""MFW 运行池的引用对账回收（宿主侧）。

运行池（``config/maafw_runtime_pool/runtimes/<id>``）按「requirement 集合 + 宿主
解释器身份」建 runtime，此前的回收只按 ``lastUsedAt`` 宽限 + 保留最新一个，且每个
进程只在第一次准备环境时跑一次——实测从没真正清掉过东西：项目升级换了 maafw
版本、宿主换了随包 Python、以及 runner venv 曾把项目 requirements.txt 折进身份而
裂出来的那些副本，全都永远留在盘上（测试包里 9 个 runtime、519 MB）。

这里改成按引用对账：

1. 权威集合 = 所有 MaaFW 类脚本的项目目录，每个项目用
   ``describe_runner_runtime_selection`` 算出 ``prepare_runner_environment`` 会选中
   的 runtime id 与 maafw requirement——两边走同一批 helper，算出来的就是运行时
   会用的那一个。
2. 不在权威集合里的 runtime 都是孤儿，交给 ``MaaFWRuntimePool.reclaim_stale_runtimes``
   按「无活租约 ∧（requirement 已不再被任何项目需要 ∨ 新身份下它的 runtime 已建好）
   ∧（过 24 h 宽限 ∨ 本轮被项目更新替换掉）」删除。租约是唯一的运行期保护：
   正在跑的 worker 拿着租约，回收永远绕开它。
3. 池里已无旧身份 runtime 时顺手 ``uv cache clean``：runtime 是从池自己的 uv
   缓存硬链接出来的，旧 runtime 删掉后那些文件就只剩缓存这一份，不清等于没删。
   仍有旧 runtime 在等新身份替换时不清，保住离线用户靠缓存重建的能力。

核心包 ``runtime_pool`` 不读 ``Config``，权威集合只在这一层算。与
``Config.clean_maafw_agent_venvs`` 同一套保守规则：任一存活项目此刻不可达、任一
项目算不出 selection、托管解释器还没装（算不出身份），整轮弃权——回收晚一轮
没有代价，误删一份 runtime 要重下几十到上百 MB。
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.utils import get_logger

logger = get_logger("MFW 运行池回收")

_RECONCILE_LOCK = threading.Lock()


def runtime_pool_root() -> Path:
    """池根，与 ``MaaFWRuntimePoolService`` 的默认值一致。"""

    return Path.cwd() / "config" / "maafw_runtime_pool"


def collect_live_project_paths() -> list[str]:
    """当前配置里全部 MaaFW 类脚本的项目目录（权威集合的输入）。"""

    from app.core import Config
    from app.models.config import MaaFWConfig

    return [
        path
        for config in Config.ScriptConfig.values()
        if isinstance(config, MaaFWConfig)
        and (path := str(config.get("Info", "Path") or "").strip())
    ]


def script_config_loaded_intact() -> bool:
    """脚本表是空的时候，看配置文件本身是不是真的空。

    解析失败、或文件里明明有脚本却一个都没加载出来，都算没加载起来——此时
    「权威集合为空」不可信，按它回收会把所有 runtime 当孤儿删光。
    """

    from app.core import Config

    if len(Config.ScriptConfig) > 0:
        return True
    path = getattr(Config.ScriptConfig, "file", None)
    if path is None or not Path(path).is_file():
        return True
    try:
        text = Path(path).read_text(encoding="utf-8")
        data = json.loads(text) if text.strip() else {}
    except (OSError, ValueError):
        return False
    return not (isinstance(data, dict) and data)


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

    # 这几个模块会拉起 runtime_pool 与 runner，只在真要用时导入。
    from app.task.MaaFW.tools.core.automas_maafw_runner.environment import (
        describe_runner_runtime_selection,
    )
    from app.task.MaaFW.tools.core.automas_maafw_runtime_pool import (
        MaaFWRuntimePoolService,
    )

    try:
        pool = MaaFWRuntimePoolService().pool
    except Exception as exc:  # noqa: BLE001 - 池本身有问题时不回收
        logger.warning(f"MFW 运行池回收已跳过：池初始化失败: {exc}")
        return None

    valid_runtime_ids: set[str] = set()
    needed_requirements: set[str] = set()
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
        needed_requirements.add(selection.maafw_requirement)

    try:
        report = pool.reclaim_stale_runtimes(
            valid_runtime_ids=valid_runtime_ids,
            needed_requirements=needed_requirements,
            replaced_versions=replaced_versions,
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
    remaining = list(report.get("remainingLegacy") or [])
    swept = list(report.get("stagingSwept") or [])
    staging_residue = list(report.get("stagingResidue") or [])
    if deleted:
        verb = "将清理" if dry_run else "已清理"
        logger.info(
            f"MFW 运行池回收（{reason}）：{verb}无人引用的 runtime {len(deleted)} 个: "
            + ", ".join(deleted)
        )
    for item in quarantined:
        logger.warning(
            f"MFW 运行池回收：runtime {item.get('runtimeId')} 已移出池但有文件删不掉"
            f"（多半还被进程映射着），残留在 {item.get('path')}，下次启动再清"
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
            f"MFW 运行池回收：runtime {item.get('runtimeId')} 本轮删不掉，下次再试: "
            f"{item.get('error')}"
        )
    for item in errors:
        logger.warning(
            f"MFW 运行池回收：runtime {item.get('runtimeId')} 的 manifest 有问题，"
            f"已跳过: {item.get('error')}"
        )
    if swept:
        logger.info(f"MFW 运行池回收：已清掉 staging 残留 {len(swept)} 个")

    # D8：只有池里已无旧身份 runtime、且本轮确实删了东西时才清缓存。旧 runtime 还在
    # 等新身份替换时不清（离线用户要靠缓存建新的）；什么都没删也不清（缓存里没
    # 有新垃圾，白跑一次子进程）。
    if not dry_run and not remaining and (deleted or swept):
        try:
            cache = pool.clean_cache()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"MFW 运行池 uv 缓存清理失败: {exc}")
        else:
            report["cacheClean"] = cache
            status = str(cache.get("status") or "unknown")
            if status == "cleaned":
                logger.info(
                    "MFW 运行池 uv 缓存已清理: "
                    f"removedFiles={int(cache.get('removedFiles') or 0)}, "
                    f"removedBytes={int(cache.get('removedBytes') or 0)}"
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
    return report


def previous_maafw_version(project_path: str | Path) -> str | None:
    """项目更新前记下它当前钉定的 maafw 精确版本（范围声明或读不出时为 None）。

    更新提交后拿它与新版本比：版本换了就把旧版本作为 ``replaced_versions`` 传给
    回收，旧 runtime 不必再等 24 h 宽限。
    """

    from app.task.MaaFW.tools.core.automas_maafw_runner.environment import (
        resolve_project_maafw_requirement,
    )
    from app.task.MaaFW.tools.core.automas_maafw_runtime_pool.identity import (
        infer_exact_maafw_version,
    )

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
    线程上先算好传进来。
    """

    replaced: list[str] = []
    if previous_version:
        current_version = previous_maafw_version(project_path)
        if current_version != previous_version:
            replaced.append(previous_version)
    return reconcile_runtime_pool(
        project_paths,
        replaced_versions=replaced,
        reason=reason,
    )


def reconcile_in_background(
    reason: str,
    *,
    updated_project_path: str | Path | None = None,
    previous_version: str | None = None,
) -> None:
    """起一个守护线程跑一轮回收，调用方不等结果。

    删脚本、项目更新提交这类路径都不该被回收拖慢（解释器探针 + 可能的
    ``uv cache clean`` 要几秒）。给了 ``updated_project_path`` 就走
    ``reconcile_after_project_update``，把被替换掉的旧版本一并豁免宽限。

    权威集合在**调用方线程**（事件循环）上先算好：``Config.ScriptConfig`` 只在
    事件循环上改，守护线程里去遍历它会撞上「dict changed size」。
    """

    if not script_config_loaded_intact():
        logger.warning(
            "脚本配置文件非空但没有加载出任何脚本，疑似损坏，跳过 MFW 运行池回收"
        )
        return
    project_paths = collect_live_project_paths()

    def _run() -> None:
        try:
            if updated_project_path is not None:
                reconcile_after_project_update(
                    project_paths,
                    updated_project_path,
                    previous_version,
                    reason=reason,
                )
            else:
                reconcile_runtime_pool(project_paths, reason=reason)
        except Exception:  # noqa: BLE001 - 后台维护，失败只记日志
            logger.opt(exception=True).warning(f"MFW 运行池后台回收失败（{reason}）")

    threading.Thread(
        target=_run, name=f"maafw-pool-reconcile:{reason}", daemon=True
    ).start()


__all__ = [
    "collect_live_project_paths",
    "previous_maafw_version",
    "reconcile_after_project_update",
    "reconcile_in_background",
    "reconcile_runtime_pool",
    "runtime_pool_root",
    "script_config_loaded_intact",
]
