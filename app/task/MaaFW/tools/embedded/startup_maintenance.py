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

"""MFW 启动期维护：老副本一次性迁移成「载荷 + 视图」，以及各项回收。

入口仍是 ``Config`` 上的同名方法（``main.py`` 的后台启动任务按固定顺序调：迁移 →
隔离 venv → 副本与载荷 → 共用库 → 更新包缓存 → 运行池），这里是它们的实现。判定都
依赖「当前全部脚本配置」这个全局状态，只有真实启动时它才可信，所以只在启动期跑。

``started_at`` 是本进程的启动时刻（``app.core.config._PROCESS_STARTED_AT``）：后台
初始化时 API 已经在服务，比它新的半成品、journal、流水都可能正在进行，一律不碰。
"""

from __future__ import annotations

import asyncio
import json
import shutil
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from app.utils import get_logger
from app.utils import io as _utils_io

if TYPE_CHECKING:
    from app.core.config import AppConfig

# 沿用搬家前的模块名：这些日志一直记在「配置管理」下，排查时按它检索。
logger = get_logger("配置管理")

# 孤儿 venv 的宽限期：刚动过的一律不碰，避免与正在准备环境的运行抢。
MAAFW_AGENT_VENV_GRACE_SECONDS = 60 * 60


async def clean_maafw_agent_venvs(app_config: AppConfig) -> None:
    """清掉已无脚本引用的 MFW agent 隔离 venv。

    这些 venv 每个几十到上百 MB，此前没有任何回收——只有「同一项目依赖变了
    就重建」那一条。用户删脚本、改项目路径、或项目升级换了目录，旧 venv 都会
    永远留着。

    放在启动清理里而不是运行前：判定依赖「当前全部脚本配置」这个全局状态，
    只有真实启动时它才可信。挂在 check() 上曾把测试替身当成真配置，
    把开发者磁盘上的真 venv 删掉了。

    判定不读目录内的清单：目录名就是项目路径的哈希，凡不属于任何存活脚本的
    即孤儿；再加一道保护——刚动过的一律不碰，避免与正在准备环境的运行抢。
    """

    from app.models.config import MaaFWConfig
    from app.task.MaaFW.tools.core.agent_env.planner import (
        collect_orphan_agent_venvs,
    )
    from app.task.MaaFW.tools.embedded.embedded_project import (
        resolve_maafw_project_root,
    )

    root = Path.cwd() / "config" / "maafw_agent_venvs"
    if not root.is_dir():
        return

    # 按有效根算存活集合：内嵌脚本的 venv 是按副本路径哈希的，拿来源目录去算
    # 会把副本的 venv 当孤儿删掉。
    live_paths = [
        path
        for uid, config in app_config.ScriptConfig.items()
        if isinstance(config, MaaFWConfig)
        and (path := str(resolve_maafw_project_root(str(uid), config)).strip())
    ]

    # 有效根都是本机 data/ 下的副本：不存在只说明这个脚本还没导入过（新建未选目录、
    # 升级后没打开过），它名下不可能有 venv，从存活集合里去掉即可；不能像路径模式
    # 那样「一个不可达就整轮弃权」，否则任何一个空脚本都会永久关掉回收。
    missing = [path for path in live_paths if not Path(path).exists()]
    if missing:
        logger.debug(f"MFW 隔离 venv 清理：{len(missing)} 个脚本还没有副本，不计入存活")
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
            shutil.rmtree(venv_path)
        except OSError as exc:
            logger.warning(f"MFW 隔离 venv 清理失败: {venv_path} - {exc}")
            continue
        logger.info(f"已清理无人引用的 MFW 隔离 venv: {venv_path}")


async def clean_maafw_embedded_copies(
    app_config: AppConfig, *, started_at: float
) -> None:
    """清掉内嵌副本目录下的两类垃圾：staging 半成品、脚本已不存在的副本。

    导入在 ``.staging/`` 里投影完再换入，进程中途退出会留下半成品；删脚本时
    副本删除失败（只读、被占用）也会留下孤儿。两者都是 MAS 自己铺的，不含用户
    内容，启动期没有任务在跑，直接清。目录名必须是副本目录名的形状才会被当作副本。
    """

    from app.models.config import MaaFWConfig
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
            lambda: recover_switches(started_at=started_at, reserve=True)
        )
    except Exception as exc:  # noqa: BLE001 - 恢复失败不该影响启动，journal 留着下次再试
        logger.warning(f"MFW 视图切换恢复失败: {exc}")
    staging = root / STAGING_DIR_NAME
    if staging.is_dir():
        for leftover in staging.iterdir():
            # 后台初始化时 API 已在服务，preview / reimport 可能正往 .staging 里写：
            # 本进程起来之后才出现的、或该脚本的副本路径正被预约的，都不是半成品。
            try:
                if leftover.stat().st_mtime >= started_at:
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
                logger.warning(f"MFW 内嵌 staging 半成品清理失败: {leftover} - {exc}")
                continue
            logger.info(f"已清理 MFW 内嵌导入半成品: {leftover}")
    # 存活的副本：脚本还在。删脚本时删副本可能因文件被占用而失败（与别的副本
    # 共用的库正被映射着），那份留下的副本也在这里收掉。
    # 但脚本表本身没加载起来（ScriptConfig.json 损坏时 _load_json_file 留下
    # .corrupt 副本后按空表继续）就不能扫：那会把所有副本当孤儿删光，来源目录
    # 已被用户清掉的项目从此没得修。
    if not _script_config_loaded_intact(app_config):
        logger.warning(
            "脚本配置文件非空但没有加载出任何脚本，疑似损坏，跳过 MFW 内嵌副本孤儿清理"
        )
        return
    live = {
        embedded_copy_dir_name(str(uid))
        for uid, config in app_config.ScriptConfig.items()
        if isinstance(config, MaaFWConfig)
    }
    for child in root.iterdir():
        if child.name == STAGING_DIR_NAME or not child.is_dir():
            continue
        if not is_embedded_copy_dir_name(child.name) or child.name in live:
            continue
        try:
            remove_tree(child)
        except OSError as exc:
            logger.warning(f"MFW 内嵌副本孤儿清理失败: {child} - {exc}")
            continue
        logger.info(f"已清理无脚本引用的 MFW 内嵌副本: {child}")
    # 视图没了的脚本（下次运行前要按载荷重建）：它的导入来源在事件循环线程上抄出来，
    # 回收据此保住对应的谱系。
    from app.task.MaaFW.tools.embedded.embedded_project import (
        embedded_project_dir,
        follow_source_enabled,
        imported_source_path,
        read_view_marker,
    )

    live_sources = [
        imported_source_path(config) or str(config.Info.Path or "")
        for uid, config in app_config.ScriptConfig.items()
        if isinstance(config, MaaFWConfig)
        and read_view_marker(embedded_project_dir(str(uid))) is None
    ]
    # 开着开发者模式的脚本：它们私有渠道的 latest 保住，其余私有渠道（关了开关、删了
    # 脚本）摘掉，留下的开发者载荷随后按普通规则回收。
    follow_views = [
        embedded_copy_dir_name(str(uid))
        for uid, config in app_config.ScriptConfig.items()
        if isinstance(config, MaaFWConfig) and follow_source_enabled(config)
    ]
    await asyncio.to_thread(
        _collect_unreferenced_payloads,
        live_sources,
        follow_views,
        started_at=started_at,
    )


def _collect_unreferenced_payloads(
    live_sources: list[str], follow_views: list[str], *, started_at: float
) -> None:
    """删掉没人引用的载荷；谱系里一个视图都不剩（最后一个脚本已删）时整个谱系一起删
    （§3.1 第 10 步，``embedded_project.collect_payload_garbage``）。

    引用集 = 所有视图标记的 ``payload`` ∪ 未完成 journal 的 ``to``；``latest[*]`` 只在
    谱系还有视图时算引用（开发者模式的私有渠道只在脚本还开着开关时算）。本进程起来
    之后才建的不收。载荷删掉之后，它独有的 blob 只剩库里一个链接，紧接着的
    ``clean_maafw_runtime_blobs`` 收走。
    """

    from app.task.MaaFW.tools.embedded.embedded_project import (
        collect_payload_garbage,
    )

    try:
        report = collect_payload_garbage(
            started_at=started_at,
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


async def migrate_maafw_embedded_copies_to_payloads(
    app_config: AppConfig, *, started_at: float
) -> None:
    """启动期一次性迁移：把没有标记的老副本采纳成「载荷 + 视图」（附录 B）。

    逐副本持视图预约、各自失败隔离（不写标记、日志点名、下次启动再试）。**全部采纳完
    再统一决定同版本的 latest**（``settle_adopted_latest``：有更新器清单的、文件集合是
    超集的、文件多的优先，与脚本顺序无关），然后每个谱系每个渠道统一到 latest（附录 B
    第 8 条），切过的视图连同预约交给后台确认运行环境。之后收掉老的原地更新留下的清单、
    预检备忘与作废的更新流水（还有没采纳的副本时留着它们要用的那部分）。配置一个字段
    都不写；脚本表没加载起来（疑似损坏）整轮弃权。

    迁移在后台跑、不挡主定时器：期间拿不到视图预约的运行在运行前检查里按「正在切换
    版本」跳过一次（``embedded_project.migration_active``）。
    """

    from app.task.MaaFW.tools.embedded.embedded_project import set_migration_active

    set_migration_active(True)
    try:
        await _migrate_maafw_embedded_copies(app_config, started_at=started_at)
    finally:
        set_migration_active(False)


async def _migrate_maafw_embedded_copies(
    app_config: AppConfig, *, started_at: float
) -> None:
    from app.models.config import MaaFWConfig
    from app.task.MaaFW.tools.embedded.embedded_project import (
        GroupMember,
        adopt_view,
        copy_is_healthy,
        effective_channel,
        embedded_project_dir,
        imported_source_path,
        read_view_marker,
        settle_adopted_latest,
    )
    from app.task.MaaFW.tools.embedded.project_path import (
        release_project_path,
        try_reserve_project_path,
    )
    from app.task.MaaFW.tools.embedded.update_credentials import (
        resolve_update_proxy_url,
    )

    if not _script_config_loaded_intact(app_config):
        logger.warning(
            "脚本配置文件非空但没有加载出任何脚本，疑似损坏，跳过 MFW 副本迁移"
        )
        return
    entries: list[tuple[str, str, str, str, str | None]] = []
    for uid, config in app_config.ScriptConfig.items():
        if not isinstance(config, MaaFWConfig):
            continue
        entries.append(
            (
                str(uid),
                effective_channel(str(uid), config),
                imported_source_path(config) or str(config.Info.Path or ""),
                str(config.Info.Name or str(uid)[:8]),
                resolve_update_proxy_url(config) or None,
            )
        )
    pending = [
        entry
        for entry in entries
        if copy_is_healthy(embedded_project_dir(entry[0]))
        and read_view_marker(embedded_project_dir(entry[0])) is None
    ]
    if not pending:
        # 没有待采纳的副本：老的原地更新留下的清单与更新记录都没用了（每次启动都收，
        # 不只在「刚迁移完且全部成功」那一次）。
        await asyncio.to_thread(
            _discard_legacy_update_state,
            keep_adoption_baseline=False,
            started_at=started_at,
        )
        return
    started = time.monotonic()
    adopted: list[str] = []
    failed: list[str] = []
    for script_id, channel, source, name, _proxy in pending:
        view = embedded_project_dir(script_id)
        key = await try_reserve_project_path(view)
        if key is None:
            failed.append(name)
            logger.warning(f"MFW 副本迁移：脚本「{name}」的副本正被占用，下次启动再试")
            continue
        began = time.monotonic()
        try:
            if await asyncio.to_thread(read_view_marker, view) is not None:
                # 迁移在后台跑：它自己开跑时的运行前检查已经就地采纳过了。
                continue
            result = await asyncio.to_thread(
                lambda sid=script_id, ch=channel, src=source: adopt_view(
                    sid, channel=ch, source=src
                )
            )
            adopted.append(script_id)
            logger.info(
                f"MFW 副本迁移：脚本「{name}」已登记为 {result.version}（{result.payload_id}），"
                f"私有文件 {result.carried} 个，采纳用时 {time.monotonic() - began:.1f} s"
            )
        except Exception as exc:  # noqa: BLE001 - 逐副本隔离，下次启动再试
            failed.append(name)
            logger.opt(exception=True).warning(
                f"MFW 副本迁移：脚本「{name}」采纳失败，下次启动再试：{exc}"
            )
        finally:
            await release_project_path(key)
    # 全部登记完才定同版本的 latest（登记本身是「同版本保留先来的」），再统一切换。
    await asyncio.to_thread(settle_adopted_latest)
    switched, held = await _unify_maafw_views_to_group(app_config, entries)
    logger.info(
        f"MFW 副本迁移完成：采纳 {len(adopted)} 个、失败 {len(failed)} 个、"
        f"统一到组版本 {len(switched)} 个，用时 {time.monotonic() - started:.1f} s"
    )
    from app.task.MaaFW.tools.embedded.view_update import (
        confirm_environments_in_background,
    )

    # 切换时拿的预约直接交给确认线程（两步之间不留空档）；没切的不确认。
    confirm_environments_in_background(
        [
            GroupMember(sid, channel, name=name, proxy_url=proxy)
            for sid, channel, _src, name, proxy in entries
            if sid in set(switched)
        ],
        held=held,
    )
    # 采纳失败的副本下次启动还要靠老的更新清单（committed 记录 + 状态目录里的包内
    # 清单）认出哪些文件没改过，那部分留着；其余作废记录照收。
    await asyncio.to_thread(
        _discard_legacy_update_state,
        keep_adoption_baseline=bool(failed),
        started_at=started_at,
    )


async def _unify_maafw_views_to_group(
    app_config: AppConfig, entries: list[tuple[str, str, str, str, str | None]]
) -> tuple[list[str], dict[str, str]]:
    """附录 B 第 8 条：每个视图切到它所在组（谱系 + 渠道）的 latest。

    返回（切过的脚本, 它们还没放的预约）：预约交给环境确认线程放。
    """

    from app.task.MaaFW.tools.embedded.embedded_project import (
        MIGRATION_SWITCHED_BY,
        embedded_project_dir,
    )
    from app.task.MaaFW.tools.embedded.project_path import (
        release_project_path,
        try_reserve_project_path,
    )
    from app.task.MaaFW.tools.embedded.view_update import sync_view_to_group

    switched: list[str] = []
    held: dict[str, str] = {}
    for script_id, channel, _source, name, _proxy in entries:
        # 迁移在后台跑、主定时器已经起来：运行中的脚本在「运行前检查结束 → 第一个用户」
        # 与用户之间不持视图预约，只看预约会在空档里把它切走（同一轮前后用户跑不同版本、
        # 下一个用户被「同一路径正在运行」跳过）。与其它传播路径同一口径：脚本配置锁着
        # （is_locked）就跳过，留给它的收尾同步或下次运行前检查。在事件循环上查。
        try:
            config = app_config.ScriptConfig[uuid.UUID(script_id)]
        except (KeyError, ValueError):
            continue
        if getattr(config, "is_locked", False):
            logger.info(
                f"MFW 副本迁移：脚本「{name}」正在运行，统一到组版本留给它跑完后再做"
            )
            continue
        key = await try_reserve_project_path(embedded_project_dir(script_id))
        if key is None:
            continue
        if getattr(config, "is_locked", False):
            # 等预约的那一下它开跑了（锁在预约之后才上，这里再看一眼）。
            await release_project_path(key)
            continue
        result = None
        try:
            result = await sync_view_to_group(
                script_id,
                channel,
                reservation_held=True,
                # 记下是迁移切的：确认期间它开跑会在运行前检查里得到「正在切换版本」，
                # 下次运行打一行「启动期迁移时统一到 vX」。
                switched_by=MIGRATION_SWITCHED_BY,
            )
        except Exception as exc:  # noqa: BLE001 - 留在原版本，下次运行前再同步
            logger.warning(f"MFW 副本迁移：脚本「{name}」统一到组版本失败：{exc}")
        finally:
            if result is None:
                await release_project_path(key)
        if result is not None:
            switched.append(script_id)
            held[script_id] = key
            logger.info(
                f"MFW 副本迁移：脚本「{name}」{result.from_payload} → {result.payload_id}"
            )
    return switched, held


def _discard_legacy_update_state(
    *, keep_adoption_baseline: bool, started_at: float
) -> None:
    """收掉更新留下的作废记录。

    - ``data/maafw_update_operations``：本进程起来之前写的记录。新流程里它只是一次
      下载 + 登记的流水（登记后标 ``registered``，失败 / 取消各有终态），没有谁再读，
      一律删；老的原地更新留下的 ``committed`` 除外——还有没采纳的老副本时
      （``keep_adoption_baseline``），采纳要靠它找包内清单。
    - ``data/maafw_project_state`` 各视图状态目录里除 ``local-modified`` 之外的文件
      （老的包内清单、预检备忘）：同样只在不再需要采纳基线时删。
    """

    operations = Path.cwd() / "data" / "maafw_update_operations"
    if operations.is_dir():
        for record in operations.iterdir():
            state_file = record / "state.json"
            try:
                if state_file.stat().st_mtime >= started_at:
                    continue
                status = json.loads(state_file.read_text(encoding="utf-8")).get(
                    "status"
                )
            except (OSError, ValueError, AttributeError):
                continue
            if status == "committed" and keep_adoption_baseline:
                continue
            try:
                shutil.rmtree(record)
            except OSError as exc:
                logger.warning(f"清理作废的更新记录失败: {record} - {exc}")
    if keep_adoption_baseline:
        return
    state_root = Path.cwd() / "data" / "maafw_project_state"
    if state_root.is_dir():
        for state_dir in state_root.iterdir():
            if not state_dir.is_dir():
                continue
            for child in state_dir.iterdir():
                if child.name == "local-modified":
                    continue
                try:
                    if child.is_dir():
                        shutil.rmtree(child)
                    else:
                        child.unlink()
                except OSError as exc:
                    logger.warning(f"清理老的更新状态失败: {child} - {exc}")


def _script_config_loaded_intact(app_config: AppConfig) -> bool:
    """脚本表是空的时候，看配置文件本身是不是真的空：解析失败或文件里明明有
    脚本却一个都没加载出来，都算没加载起来。"""

    if len(app_config.ScriptConfig) > 0:
        return True
    path = app_config.ScriptConfig.persist_path
    if path is None or not path.is_file():
        return True
    try:
        data = _utils_io.read_dict_file(path, allow_empty=True)
    except (OSError, ValueError):
        return False
    return not bool(data.get("order"))


async def clean_maafw_runtime_blobs() -> None:
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


async def clean_maafw_update_cache() -> None:
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


async def clean_maafw_runtime_pool() -> None:
    """按引用对账回收 MFW 运行池里无人引用的共享 runtime。

    与 ``clean_maafw_agent_venvs`` 同一个道理放在启动清理里：判定依赖「当前
    全部脚本配置」这个全局状态，只有真实启动时它才可信。规则与保守条件见
    ``tools/embedded/pool_reconcile.py``；这里只负责把权威集合（全部 MaaFW 类
    脚本的项目目录）交过去，并在脚本表疑似没加载起来时弃权。
    """

    from app.task.MaaFW.tools.embedded.pool_reconcile import (
        collect_live_project_paths,
        reconcile_runtime_pool,
        runtime_pool_root,
        script_config_loaded_intact,
    )

    if not (runtime_pool_root() / "runtimes").is_dir():
        return
    if not script_config_loaded_intact():
        logger.warning(
            "脚本配置文件非空但没有加载出任何脚本，疑似损坏，跳过 MFW 运行池回收"
        )
        return
    try:
        await asyncio.to_thread(
            reconcile_runtime_pool,
            collect_live_project_paths(),
            reason="startup",
        )
    except Exception as exc:  # noqa: BLE001 - 回收失败不该影响启动
        logger.warning(f"MFW 运行池回收失败: {exc}")


__all__ = [
    "clean_maafw_agent_venvs",
    "clean_maafw_embedded_copies",
    "clean_maafw_runtime_blobs",
    "clean_maafw_runtime_pool",
    "clean_maafw_update_cache",
    "migrate_maafw_embedded_copies_to_payloads",
]
