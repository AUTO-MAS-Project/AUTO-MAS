#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""MFW 宿主维护；配置事实由宿主提供，资源规则留在引擎宿主接缝。"""

from __future__ import annotations

import asyncio
import shutil
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from app.config import ConfigEntry
from app.models.config import MaaFWConfig
from app.utils import get_logger

logger = get_logger("MFW 维护")

# 刚动过的 venv 不碰，避免与正在准备环境的运行抢。
MAAFW_AGENT_VENV_GRACE_SECONDS = 60 * 60


class MaaFWMaintenanceService:
    """维护 MAS 管理的 MFW 资源，不接收公共 Config 或宿主容器。"""

    def __init__(
        self,
        *,
        script_configs: Callable[[], Sequence[tuple[str, ConfigEntry]]],
        scripts_loaded_intact: Callable[[], bool],
        retention_days: Callable[[], int],
        process_started_at: float,
    ) -> None:
        self._script_configs = script_configs
        self._scripts_loaded_intact = scripts_loaded_intact
        self._retention_days = retention_days
        self._process_started_at = process_started_at

    def _scripts(self) -> list[tuple[str, MaaFWConfig]]:
        """在事件循环上取当前脚本快照，不把宿主集合交给工作线程。"""
        return [
            (uid, config)
            for uid, config in self._script_configs()
            if isinstance(config, MaaFWConfig)
        ]

    async def migrate_embedded_copies_to_payloads(self) -> None:
        """在依赖终态布局的资源维护之前，把老副本采纳为载荷与视图。"""

        from .migration import migrate_embedded_copies_to_payloads

        if not self._scripts_loaded_intact():
            logger.warning("脚本配置未完整加载，跳过 MFW 副本迁移")
            return
        await migrate_embedded_copies_to_payloads(
            script_configs=self._scripts, process_started_at=self._process_started_at
        )

    async def clean_agent_venvs(self) -> None:
        """清掉已无脚本引用的 MFW agent 隔离 venv。

        这些 venv 每个几十到上百 MB，此前没有任何回收——只有「同一项目依赖变了
        就重建」那一条。用户删脚本、改项目路径、或项目升级换了目录，旧 venv 都会
        永远留着。

        放在启动清理里而不是运行前：判定依赖「当前全部脚本配置」这个全局状态，
        只有真实启动时它才可信。挂在 check() 上曾把测试替身当成真配置，
        把开发者磁盘上的真 venv 删掉了。

        隔离 venv 按依赖清单 + maafw 版本 + 宿主身份跨视图共用，目录名不再由项目路径推出：
        存活集合按各存活脚本的引用记录（准备时写在 ``.refs/`` 下）、建计划时会算出的目录、
        以及还没准备过的脚本升级前按路径建的老目录算，不读 venv 目录内的清单；存活脚本的
        引用记录读不出来就整轮不回收（见 ``agent_env.planner.collect_orphan_agent_venvs``）。
        再加两道保护——刚动过的一律不碰；正被准备（锁文件被占）的也不碰，避免与正在
        准备环境的运行抢。不属于任何存活脚本的引用记录一并删掉。
        """

        from app.task.MaaFW.tools.core.agent_env.planner import (
            collect_orphan_agent_venvs,
        )
        from app.task.MaaFW.tools.core.agent_env.venv_share import (
            collect_stale_venv_refs,
            discard_venv_lock_file,
            isolated_venv_guard,
        )
        from app.task.MaaFW.tools.embedded.embedded_project import (
            resolve_maafw_project_root,
        )

        root = Path.cwd() / "config" / "maafw_agent_venvs"
        if not root.is_dir():
            return
        if not self._scripts_loaded_intact():
            logger.warning("脚本配置未完整加载，跳过 MFW 隔离 venv 孤儿清理")
            return

        # 按有效根算存活集合：引用记录和建计划都按副本（视图）路径算，拿来源目录去算
        # 会把副本引用的 venv 当孤儿删掉。
        live_paths = [
            path
            for uid, config in self._scripts()
            if (path := str(resolve_maafw_project_root(uid, config)).strip())
        ]

        # 有效根都是本机 data/ 下的副本：不存在只说明这个脚本还没导入过（新建未选目录、
        # 升级后没打开过），它名下不可能有 venv，从存活集合里去掉即可；不能像路径模式
        # 那样「一个不可达就整轮弃权」，否则任何一个空脚本都会永久关掉回收。
        missing = [path for path in live_paths if not Path(path).exists()]
        if missing:
            logger.debug(
                f"MFW 隔离 venv 清理：{len(missing)} 个脚本还没有副本，不计入存活"
            )
            live_paths = [path for path in live_paths if Path(path).exists()]

        try:
            orphans = collect_orphan_agent_venvs(root, live_paths)
        except Exception as exc:
            logger.warning(f"MFW 隔离 venv 孤儿扫描失败: {exc}")
            return

        cutoff = time.time() - MAAFW_AGENT_VENV_GRACE_SECONDS
        for venv_path in orphans:
            try:
                if venv_path.stat().st_mtime > cutoff:
                    continue  # 刚动过，可能有运行正在用它
                with isolated_venv_guard(venv_path, blocking=False) as locked:
                    if not locked:
                        logger.info(
                            f"MFW 隔离 venv 正在被准备，本次不清理: {venv_path}"
                        )
                        continue
                    shutil.rmtree(venv_path)
            except OSError as exc:
                logger.warning(f"MFW 隔离 venv 清理失败: {venv_path} - {exc}")
                continue
            # 锁文件出了锁才删得掉（Windows 上开着的文件删不了）
            discard_venv_lock_file(venv_path)
            logger.info(f"已清理无人引用的 MFW 隔离 venv: {venv_path}")

        try:
            stale_refs = collect_stale_venv_refs(root, live_paths)
        except Exception as exc:
            logger.warning(f"MFW 隔离 venv 引用记录扫描失败: {exc}")
            return
        for ref_path in stale_refs:
            try:
                ref_path.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning(f"MFW 隔离 venv 引用记录清理失败: {ref_path} - {exc}")
                continue
            logger.debug(f"已清理无主的 MFW 隔离 venv 引用记录: {ref_path}")

    async def clean_embedded_copies(self) -> None:
        """清掉内嵌副本目录下的两类垃圾：staging 半成品、脚本已不存在的副本。

        导入在 ``.staging/`` 里投影完再换入，进程中途退出会留下半成品；删脚本时
        副本删除失败（只读、被占用）也会留下孤儿。两者都是 MAS 自己铺的，不含用户
        内容，按进程启动时刻与视图预约避开后台并发。目录名必须是副本目录名的形状。
        """

        from app.task.MaaFW.tools.embedded.embedded_project import (
            STAGING_DIR_NAME,
            embedded_copy_dir_name,
            embedded_projects_root,
            is_embedded_copy_dir_name,
            recover_switches,
            remove_tree,
            switch_root,
        )
        from app.task.MaaFW.tools.embedded.project_path import (
            release_project_path,
            try_reserve_project_path,
        )

        root = embedded_projects_root()
        if not root.is_dir():
            return
        # 先按 journal 收尾被打断的视图切换：切换的 old / staging 都在 .staging 里，
        # 不先恢复的话下面的半成品清理会把「rename 了一半」时暂存的原视图当垃圾删掉。
        try:
            # 本进程起来之后才写的 journal、拿不到视图预约的（正在切换 / 运行）不碰：
            # 后台初始化时 API 已经在服务，可能正有一次切换在建 staging。
            await asyncio.to_thread(
                recover_switches, started_at=self._process_started_at, reserve=True
            )
        except Exception as exc:  # noqa: BLE001 - 恢复失败不该影响启动，journal 留着下次再试
            logger.warning(f"MFW 视图切换恢复失败: {exc}")
        staging = root / STAGING_DIR_NAME
        if staging.is_dir():
            for leftover in staging.iterdir():
                # 后台初始化时 API 已在服务，preview / reimport 可能正往 .staging 里写：
                # 本进程起来之后才出现的、或该脚本的副本路径正被预约的，都不是半成品。
                try:
                    if leftover.stat().st_mtime >= self._process_started_at:
                        continue
                except OSError:
                    continue
                # 半成品叫 <副本目录名>-<8 位随机>、<副本目录名>-old-/-sw-<8 位随机>
                # 或 payload-<谱系>-<8 位随机>
                prefix = leftover.name.split("-", 1)[0]
                if (switch_root() / f"{prefix}.json").exists():
                    # 恢复没收尾的切换：它的 old 目录可能就是原视图，留着待查
                    continue
                reservation = await try_reserve_project_path(root / prefix)
                if reservation is None:
                    continue
                await release_project_path(reservation)
                try:
                    remove_tree(leftover)
                except OSError as exc:
                    logger.warning(
                        f"MFW 内嵌 staging 半成品清理失败: {leftover} - {exc}"
                    )
                    continue
                logger.info(f"已清理 MFW 内嵌导入半成品: {leftover}")
        # 存活的副本：脚本还在。删脚本时删副本可能因文件被占用而失败（与别的副本
        # 共用的库正被映射着），那份留下的副本也在这里收掉。
        # 脚本表未完整加载时不能用它判孤儿；来源已被用户清掉的项目可能只剩这份副本。
        if not self._scripts_loaded_intact():
            logger.warning(
                "脚本配置文件非空但没有加载出任何脚本，疑似损坏，跳过 MFW 内嵌副本孤儿清理"
            )
            return
        live = {embedded_copy_dir_name(uid) for uid, _config in self._scripts()}
        for child in root.iterdir():
            if child.name == STAGING_DIR_NAME or not child.is_dir():
                continue
            if not is_embedded_copy_dir_name(child.name) or child.name in live:
                continue
            # 后台维护期间可能正有导入或运行，沿用 staging 的进程与预约保护。
            try:
                if child.stat().st_mtime >= self._process_started_at:
                    continue
            except OSError:
                continue
            if (switch_root() / f"{child.name}.json").exists():
                continue
            reservation = await try_reserve_project_path(child)
            if reservation is None:
                continue
            try:
                remove_tree(child)
            except OSError as exc:
                logger.warning(f"MFW 内嵌副本孤儿清理失败: {child} - {exc}")
                continue
            finally:
                await release_project_path(reservation)
            logger.info(f"已清理无脚本引用的 MFW 内嵌副本: {child}")
        # 视图没了的脚本（下次运行前要按载荷重建）：它的导入来源在事件循环线程上抄出来，
        # 回收据此保住对应的谱系。
        from app.task.MaaFW.tools.embedded.embedded_project import (
            collect_payload_garbage,
            embedded_project_dir,
            follow_source_enabled,
            imported_source_path,
            read_view_marker,
        )

        live_sources = [
            imported_source_path(config) or str(config.Info.Path or "")
            for uid, config in self._scripts()
            if read_view_marker(embedded_project_dir(uid)) is None
        ]
        # 开着开发者模式的脚本：它们私有渠道的 latest 保住，其余私有渠道（关了开关、删了
        # 脚本）摘掉，留下的开发者载荷随后按普通规则回收。
        follow_views = [
            embedded_copy_dir_name(str(uid))
            for uid, config in self._scripts()
            if follow_source_enabled(config)
        ]
        # 引用包括视图、未完成 journal 的目标与仍存活渠道的 latest；本进程新建的不收。
        # 先删无引用载荷，再由下一步共用库回收释放只剩库内硬链接的 blob。
        try:
            report = await asyncio.to_thread(
                collect_payload_garbage,
                started_at=self._process_started_at,
                live_sources=live_sources,
                follow_source_views=follow_views,
            )
        except Exception as exc:  # noqa: BLE001 - 回收失败不影响启动
            logger.warning(f"MFW 载荷回收失败: {exc}")
            return
        if not (report.payloads or report.lineages):
            return
        parts = []
        if report.payloads:
            parts.append(f"{report.payloads} 个无人引用的项目版本（载荷）")
        if report.lineages:
            parts.append(
                f"{len(report.lineages)} 个不再有脚本使用的项目（整个谱系: "
                + ", ".join(report.lineages)
                + "）"
            )
        # 与共用库共享的大文件由紧接着的共用库回收释放（那一行另报 MB）。
        logger.info(
            f"已回收 MFW {'、'.join(parts)}，释放 {report.freed_bytes / 2**20:.1f} MB"
        )

    async def clean_runtime_blobs(self) -> None:
        """回收没有任何内嵌副本引用的共用运行时文件（只剩库里这一个硬链接的）。

        放在副本清理之后：副本删掉，它引用的 blob 才会变成孤儿。
        """

        from app.task.MaaFW.tools.core.project_update.blob_store import (
            RuntimeBlobStore,
        )

        try:
            report = RuntimeBlobStore.default().collect_garbage()
        except Exception as exc:  # noqa: BLE001 - 回收失败不该影响启动
            logger.warning(f"MFW 共用运行时库回收失败: {exc}")
            return
        if report.removed_blobs or report.removed_temps:
            logger.info(
                f"已回收 MFW 共用运行时库: {report.removed_blobs} 个文件、"
                f"{report.removed_bytes / 2**20:.1f} MB，半成品 {report.removed_temps} 个"
            )

    async def clean_update_cache(self) -> None:
        """回收 7 天没人碰过的 MFW 项目更新包缓存。

        下载好的包留在 ``data/maafw_update_cache`` 里给同一项目的其它副本命中，
        一份 200 MB 的全量包只下一次；但此前从不回收，每个下过的版本都永久留着。
        正在下载 / 落地的条目持有文件锁，会被跳过。
        """

        from app.task.MaaFW.tools.core.project_update.transport import (
            prune_update_cache,
        )

        try:
            report = await asyncio.to_thread(prune_update_cache)
        except Exception as exc:  # noqa: BLE001 - 回收失败不该影响启动
            logger.warning(f"MFW 更新包缓存回收失败: {exc}")
            return
        if report.removed_artifacts:
            logger.info(
                f"已回收 MFW 更新包缓存: {report.removed_artifacts} 个、"
                f"{report.removed_bytes / 2**20:.1f} MB"
            )

    async def clean_runtime_pool(self) -> None:
        """按引用对账回收 MFW 运行池里无人引用的共享 runtime。

        与 ``clean_agent_venvs`` 同一个道理放在启动清理里：判定依赖「当前
        全部脚本配置」这个全局状态，只有真实启动时它才可信。规则与保守条件见
        ``tools/embedded/pool_reconcile.py``；这里只负责把权威集合（全部 MaaFW 类
        脚本的项目目录）交过去，并在脚本表疑似没加载起来时弃权。
        """

        from app.task.MaaFW.tools.embedded.pool_reconcile import (
            collect_live_project_paths,
            reconcile_runtime_pool,
            runtime_pool_root,
        )

        if not (runtime_pool_root() / "runtimes").is_dir():
            return
        if not self._scripts_loaded_intact():
            logger.warning(
                "脚本配置文件非空但没有加载出任何脚本，疑似损坏，跳过 MFW 运行池回收"
            )
            return
        try:
            await asyncio.to_thread(
                reconcile_runtime_pool,
                collect_live_project_paths(self._scripts()),
                reason="startup",
            )
        except Exception as exc:  # noqa: BLE001 - 回收失败不该影响启动
            logger.warning(f"MFW 运行池回收失败: {exc}")

    async def clean_native_debug_logs(self) -> None:
        """清掉 MFW 项目里过期的 MaaFramework 原生日志备份。

        MaaFramework 把 ``debug/maafw.log`` 写到一定大小就整体挪成
        ``debug/maafw.bak.<时间戳>.log`` 再开新的，但从不回收旧的——一个每天跑
        的项目几天就能堆出几百 MB。每次运行的完整内容已经另存进历史记录的
        ``*.maafw.log``，所以这里只删备份，正在写的 ``maafw.log`` 不动。
        保留时长沿用历史记录的保留天数设置。

        配置快照与必要导入在事件循环上完成，文件清理仍在工作线程执行。
        """

        # 保留设置只读一次，路径在事件循环上解析；工作线程不遍历 live 配置。
        retention_days = self._retention_days()
        if retention_days == 0:
            logger.info("原生日志永久保留, 跳过 MFW 原生日志备份清理")
            return

        from app.task.MaaFW.tools.embedded.embedded_project import (
            resolve_maafw_project_root,
        )

        project_paths = [
            resolve_maafw_project_root(uid, config) for uid, config in self._scripts()
        ]
        await asyncio.to_thread(
            self._clean_native_debug_logs,
            project_paths,
            retention_days=retention_days,
        )

    @staticmethod
    def _clean_native_debug_logs(
        project_paths: list[Path], *, retention_days: int
    ) -> None:
        cutoff = time.time() - retention_days * 86400
        deleted_count = 0
        for project_path in project_paths:
            debug_folder = project_path / "debug"
            if not debug_folder.is_dir():
                continue
            # 备份文件名由 MaaFramework 决定，与 runner_task 里
            # _iter_rotated_native_debug_logs 认的是同一套。
            for file in debug_folder.glob("maafw.bak.*.log"):
                try:
                    if file.stat().st_mtime >= cutoff:
                        continue
                    file.unlink()
                except OSError as exc:
                    logger.warning(f"MFW 原生日志备份清理失败: {file} - {exc}")
                    continue
                deleted_count += 1
        if deleted_count:
            logger.success(f"清理完成: {deleted_count} 个过期 MFW 原生日志备份")
