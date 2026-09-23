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

"""``/maafw/embedded/*`` 端点背后的业务：副本状态、导入 / 重导、克隆、候选来源。

导入与克隆之后的两步也在这里：按项目换脚本类型（``_apply_project_flavor``），
把同项目同渠道的空闲脚本切到组当前版本（``_propagate_view_to_group``）。
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from app.core import Config
from app.models.config import MaaFWConfig as RuntimeMaaFWConfig
from app.models.schema import (
    MaaFWEmbeddedProjection,
    MaaFWEmbeddedSourceItem,
    MaaFWEmbeddedStatusData,
    WSMaaFWEnvPrepareProgressData,
)
from app.task.MaaFW.api_service.common import (
    MaaFWApiReply,
    logger,
    maafw_group_members,
    maafw_script_config,
)
from app.task.MaaFW.tools.core.automas_maafw_interface.loader import (
    load_interface_model_cached,
)
from app.task.MaaFW.tools.core.automas_maafw_interface.preview import (
    interface_display_name,
)
from app.task.MaaFW.tools.embedded.embedded_project import (
    EmbeddedProjectError,
    clone_embedded_copy,
    copy_is_healthy,
    embedded_project_dir,
    embedded_status,
    import_embedded_project,
    inherit_embedded_record,
    read_interface_version,
    read_view_marker,
)
from app.task.MaaFW.tools.embedded.flavor import (
    decide_project_config_class,
    user_config_type_transform,
)
from app.task.MaaFW.tools.embedded.project_path import (
    release_project_path,
    try_reserve_project_path,
)

EMBEDDED_SCRIPT_BUSY = "脚本正在运行，运行结束后再操作内嵌"
EMBEDDED_COPY_BUSY = "该 MFW 项目正在更新或准备环境，请稍后重试"


async def embedded_status_data(
    script_id: str, script_config: Any
) -> MaaFWEmbeddedStatusData:
    # 来源目录的 is_dir 可能是断开的网络盘，别在事件循环上做。
    status = await asyncio.to_thread(embedded_status, script_id, script_config)
    report = status.get("report") or {}
    return MaaFWEmbeddedStatusData(
        copyPath=str(status["copyPath"]),
        copyHealthy=bool(status["copyHealthy"]),
        sourcePath=str(status["sourcePath"]),
        sourceExists=bool(status["sourceExists"]),
        sourceVersion=str(status["sourceVersion"]),
        importedAt=str(status["importedAt"]),
        report=MaaFWEmbeddedProjection(**_pick_projection_fields(report))
        if report
        else None,
    )


def _pick_projection_fields(report: Mapping[str, Any]) -> dict[str, Any]:
    keys = MaaFWEmbeddedProjection.model_fields.keys()
    return {key: report[key] for key in keys if key in report}


def _embedded_busy_reason(script_config: Any) -> str:
    """运行中不许动副本：换树会让正在跑的 worker 失去资源，写配置也会被锁拒绝。"""

    return EMBEDDED_SCRIPT_BUSY if getattr(script_config, "is_locked", False) else ""


async def _embed_from_source(script_id: str, source_path: str) -> tuple[None, str]:
    """导入副本并把报告写回配置。失败时原因原样带出——闸门理由就是用户要看的东西。

    副本路径与 `/maafw/update`、`/agent-env/prepare` 共用同一把项目锁：更新落地或
    环境准备进行到一半时换树，两边都会坏。
    """

    try:
        channel = str(
            maafw_script_config(script_id).get("Update", "Channel") or "stable"
        )
    except (KeyError, ValueError, TypeError):
        channel = "stable"
    reservation = await try_reserve_project_path(embedded_project_dir(script_id))
    if reservation is None:
        return None, EMBEDDED_COPY_BUSY
    publish = _embedded_import_publisher(script_id)
    try:
        # 扫目录、建计划这一段没有进度，先把阶段告诉页面，别让进度条一直是 0
        publish("importing", "running", "正在扫描项目目录", None)
        imported = await asyncio.to_thread(
            import_embedded_project,
            script_id,
            source_path,
            progress=_embedded_import_progress(publish),
            channel=channel,
        )
        publish("imported", "success", "导入完成", 100.0)
    except EmbeddedProjectError as exc:
        return None, str(exc)
    except Exception as exc:  # noqa: BLE001 - 文件系统异常也要原样给用户
        return None, f"{type(exc).__name__}: {exc}"
    finally:
        await release_project_path(reservation)
    await Config.update_script(
        script_id,
        {
            "Embedded": {
                "Report": json.dumps(imported["report"], ensure_ascii=False),
                "SourceVersion": imported["sourceVersion"],
                "ImportedAt": imported["importedAt"],
            }
        },
    )
    await _apply_project_flavor(script_id)
    await _propagate_view_to_group(script_id, channel)
    return None, ""


async def _propagate_view_to_group(script_id: str, channel: str) -> None:
    """导入之后，把同项目同渠道里还挂在别的版本上的空闲脚本切到组当前版本（§3.5「本地
    导入并组」）。运行中 / 被占用的跳过，它们下次运行前自己对齐。失败只记日志。"""

    view = embedded_project_dir(script_id)
    marker = await asyncio.to_thread(read_view_marker, view)
    if marker is None:
        return
    # 遍历脚本表必须在事件循环线程上做（工作线程里遍历会撞 dict changed size）
    members = maafw_group_members(script_id)
    try:
        source_name = str(
            maafw_script_config(script_id).get("Info", "Name") or script_id[:8]
        )
    except (KeyError, ValueError, TypeError):
        source_name = script_id[:8]
    # 切换只把文件摆好：被切的兄弟各自在后台确认一次运行环境，别把 isolated_venv 的
    # 重建留到它们下一次运行、游戏已经起来的时候（§3.1 第 8 步）。切换时拿的预约直接
    # 交给确认线程，两步之间不留空档。
    from app.task.MaaFW.tools.embedded.view_update import propagate_and_confirm

    try:
        result = await asyncio.to_thread(
            propagate_and_confirm,
            str(marker["lineage"]),
            channel,
            str(marker["payload"]),
            members,
            switched_by={"scriptId": script_id, "name": source_name},
        )
    except Exception as exc:  # noqa: BLE001 - 同步兄弟失败不影响本次导入
        logger.opt(exception=True).warning(f"导入后同步同项目脚本失败：{exc}")
        return
    if result.switched or result.skipped or result.failed:
        logger.info(
            f"MFW 脚本 {script_id} 导入后同步同项目脚本：已切换 {result.switched}，"
            f"跳过 {result.skipped}，失败 {result.failed}"
        )


_EmbeddedImportPublish = Callable[[str, str, str, float | None], None]


def _embedded_import_publisher(script_id: str) -> _EmbeddedImportPublish:
    """导入进度走运行环境准备那条 WS 通道（同一个脚本 id）：页面早就订着它，
    两件事不会同时发生，用 ``stage=importing / imported`` 区分。"""

    from app.core.ws import protocol as ws_protocol
    from app.core.ws.publisher import Publisher

    loop = asyncio.get_running_loop()

    def publish(stage: str, status: str, message: str, percent: float | None) -> None:
        data = WSMaaFWEnvPrepareProgressData(
            stage=stage, status=status, message=message, percent=percent
        )
        # 导入跑在工作线程里，回调要跨回事件循环才能发 WS
        asyncio.run_coroutine_threadsafe(
            Publisher.send(
                id=script_id,
                type=ws_protocol.MAAFW_ENV_PREPARE_PROGRESS,
                data=data,
            ),
            loop,
        )

    return publish


def _embedded_import_progress(
    publish: _EmbeddedImportPublish,
) -> Callable[[int, int], None]:
    """把投影的字节进度节流成百分比事件：至少涨 1 个点或隔 0.5 秒才推一次，满了必推。"""

    last_percent = -1.0
    last_at = 0.0

    def on_progress(done: int, total: int) -> None:
        nonlocal last_percent, last_at
        percent = min(100.0, done * 100 / total) if total > 0 else 100.0
        now = time.monotonic()
        if percent < 100 and percent - last_percent < 1 and now - last_at < 0.5:
            return
        last_percent, last_at = percent, now
        publish(
            "importing",
            "running",
            f"正在复制项目文件 {percent:.0f}%",
            round(percent, 1),
        )

    return on_progress


async def _apply_project_flavor(script_id: str) -> None:
    """导入完成后按项目决定脚本类型：特调项目 → 特调类型，否则通用 MaaFW；uid 不变。

    类型由项目决定、双向自动：M9A 目录导进通用 MaaFW 脚本会变成 M9A，M9A 脚本换成别的项目
    会变回 MaaFW。数据一个字段不动（两类同形），只换 ``instances[].type``。
    """

    try:
        script_uid = uuid.UUID(str(script_id))
        script_config = Config.ScriptConfig[script_uid]
    except (KeyError, ValueError):
        return
    try:
        interface = await asyncio.to_thread(
            lambda: load_interface_model_cached(
                embedded_project_dir(script_id), force_reload=True
            )
        )
    except Exception as exc:  # noqa: BLE001 - 识别失败就保持原类型
        logger.warning(f"导入后识别项目类型失败，保持原类型：{exc}")
        return
    target = decide_project_config_class(interface)
    if type(script_config) is target:
        return
    try:
        await Config.ScriptConfig.retype(
            script_uid, target, user_config_type_transform(target)
        )
    except Exception as exc:  # noqa: BLE001 - 换类型失败不该让导入失败
        logger.warning(f"按项目切换脚本类型失败，保持原类型：{exc}")
        return
    logger.info(f"脚本 {script_id} 按项目识别为 {target.__name__}，已原地切换类型")
    script_name = str(script_config.get("Info", "Name") or str(script_id)[:8])
    if issubclass(target, RuntimeMaaFWConfig) and target is not RuntimeMaaFWConfig:
        await Config.push_system_notice(
            level="warning",
            title=f"脚本「{script_name}」已按项目识别为 {target.__name__.removesuffix('Config')}",
            lines=[
                "运行时会自动补上启动 / 关闭游戏；官服用户的「账号」会用于自动切换账号，"
                "如果那一栏原来只是备注，请改掉或清空",
            ],
        )
    else:
        await Config.push_system_notice(
            level="info",
            title=f"脚本「{script_name}」已变回通用 MFW 脚本",
            lines=[
                "不再自动补启动 / 关闭 / 切换账号；用户与运行设置保留，任务队列请按新项目重排"
            ],
        )


async def get_embedded_status(script_id: str) -> MaaFWApiReply:
    """``/maafw/embedded/status``：脚本内嵌副本的状态。"""

    try:
        script_config = maafw_script_config(script_id)
    except (KeyError, ValueError, TypeError) as exc:
        return MaaFWApiReply.error(400, f"MFW 脚本无效: {exc}")
    return MaaFWApiReply(data=await embedded_status_data(script_id, script_config))


async def reimport_embedded(script_id: str, source_path: str | None) -> MaaFWApiReply:
    """``/maafw/embedded/reimport``：第一次是导入，之后是换来源或按当前来源重导。

    导入成功才把来源写进 Info.Path；失败时旧副本与旧来源都原样不动。
    """

    try:
        script_config = maafw_script_config(script_id)
    except (KeyError, ValueError, TypeError) as exc:
        return MaaFWApiReply.error(400, f"MFW 脚本无效: {exc}")
    if busy := _embedded_busy_reason(script_config):
        return MaaFWApiReply.error(400, busy)
    source = str(source_path or "").strip()
    copy_dir = embedded_project_dir(script_id)
    # 换树前记下旧副本钉定的 maafw 版本：重导后版本换了，旧 binding 不必再等宽限
    previous_version = await _previous_maafw_version(copy_dir)
    _failed, error = await _embed_from_source(script_id, source)
    if error:
        return MaaFWApiReply.error(400, f"重新导入失败: {error}")
    # 导入成功才把来源写进 Info.Path：失败时旧副本与旧来源都原样不动。
    await Config.update_script(script_id, {"Info": {"Path": source}})
    _reconcile_pool_after_copy_change("reimport", copy_dir, previous_version)
    data = await embedded_status_data(script_id, maafw_script_config(script_id))
    # 副本、来源、省了多少这些细节只进运行环境日志（见 embedded_summary_lines），
    # 页面上就是一句「项目已导入」
    return MaaFWApiReply(message="项目已导入", data=data)


async def _previous_maafw_version(copy_dir: Path) -> str | None:
    """副本换树（重导 / 克隆覆盖）之前它钉定的 maafw 精确版本；没有副本或读不出为 None。"""

    from app.task.MaaFW.tools.embedded.pool_reconcile import previous_maafw_version

    if not copy_dir.is_dir():
        return None
    return await asyncio.to_thread(previous_maafw_version, copy_dir)


def _reconcile_pool_after_copy_change(
    reason: str, copy_dir: Path, previous_version: str | None
) -> None:
    """D7 的「reimport / clone 后」触发点：副本换了树，旧版本的 binding 可能已无人引用。

    与手动更新提交后同一条路（``reconcile_in_background``，后台线程），版本换了就把
    旧版本作为 replaced 传给回收豁免宽限；权威集合按副本目录算，新副本自己在集合里。
    """

    from app.task.MaaFW.tools.embedded.pool_reconcile import reconcile_in_background

    reconcile_in_background(
        reason, updated_project_path=copy_dir, previous_version=previous_version
    )


def _format_bytes(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if number < 1024 or unit == "GB":
            return f"{number:.0f} {unit}" if unit == "B" else f"{number:.1f} {unit}"
        number /= 1024
    return ""


def embedded_summary_lines(script_id: str) -> list[str]:
    """运行环境日志开头那两行：项目跑在哪份副本上、从哪导入的、省了多少。

    界面上的目录字段只显示副本位置，「内嵌」这件事只在这里体现；没有副本
    （老脚本、导入失败）就一行都不写。
    """

    try:
        script_config = maafw_script_config(script_id)
        status = embedded_status(script_id, script_config)
    except Exception:  # noqa: BLE001 - 日志装饰，读不出来就不写
        return []
    if not status.get("copyHealthy"):
        return []
    report = status.get("report") or {}
    if not isinstance(report, dict):
        report = {}

    origin: list[str] = []
    if status.get("sourcePath"):
        origin.append(f"来源 {status['sourcePath']}")
        if not status.get("sourceExists"):
            origin.append("来源目录已不存在，副本照常运行与更新")
    # 记的是导入那一刻来源目录的版本；副本之后自己更新过的话，界面表头显示的才是现在的版本
    if status.get("sourceVersion"):
        origin.append(f"导入时版本 {status['sourceVersion']}")
    imported_at = str(status.get("importedAt") or "")
    if imported_at:
        origin.append(f"导入于 {imported_at[:19].replace('T', ' ')}")
    lines = [
        f"项目已导入到 AUTO-MAS 目录 {status['copyPath']}"
        + (f"（{'，'.join(origin)}）" if origin else "")
    ]

    details: list[str] = []
    payload_size = _format_bytes(report.get("payloadSizeBytes"))
    source_size = _format_bytes(report.get("sourceSizeBytes"))
    if payload_size and source_size:
        details.append(f"副本 {payload_size}，来源 {source_size}")
    shared = report.get("sharedBytes")
    if shared:
        details.append(f"与其它副本共用 {_format_bytes(shared)}")
    families = report.get("shellFamilies")
    if isinstance(families, list) and families:
        details.append(f"外壳 {' / '.join(str(f) for f in families)} 未带入")
    bundled: list[str] = []
    if report.get("bundledMaaFWVersion"):
        bundled.append(f"MaaFramework {report['bundledMaaFWVersion']}")
    if report.get("bundledPythonVersion"):
        bundled.append(f"Python {report['bundledPythonVersion']}")
    if bundled:
        details.append(f"项目自带 {'、'.join(bundled)}")
    current = str(status.get("version") or "")
    if current:
        siblings = int(status.get("siblingCount") or 0)
        details.append(
            f"当前版本 {current}（与 {siblings} 个脚本共用）"
            if siblings
            else f"当前版本 {current}"
        )
    if details:
        lines.append("；".join(details))
    return lines


def _embedded_source_project(script_id: str) -> tuple[str, str]:
    """副本 interface 里的项目显示名与版本；读不出就空串，不影响列表。"""

    copy_dir = embedded_project_dir(script_id)
    try:
        interface = load_interface_model_cached(copy_dir)
        return interface_display_name(copy_dir, interface), str(interface.version or "")
    except Exception:  # noqa: BLE001 - 坏 interface 只影响这一项的显示名，不能拖垮整张表
        pass
    try:
        return "", read_interface_version(copy_dir)
    except Exception:  # noqa: BLE001 - 非 UTF-8 / 被占用的文件同上
        return "", ""


async def list_embedded_sources(excluded_script_id: str | None) -> MaaFWApiReply:
    """``/maafw/embedded/sources``：有健康副本的 MFW / M9A 脚本，排除 ``excluded_script_id``。"""

    excluded = str(excluded_script_id or "").strip()

    def _collect() -> list[MaaFWEmbeddedSourceItem]:
        items: list[MaaFWEmbeddedSourceItem] = []
        for uid, config in Config.ScriptConfig.items():
            script_id = str(uid)
            if script_id == excluded or not isinstance(config, RuntimeMaaFWConfig):
                continue
            if not copy_is_healthy(embedded_project_dir(script_id)):
                continue
            project_name, version = _embedded_source_project(script_id)
            items.append(
                MaaFWEmbeddedSourceItem(
                    scriptId=script_id,
                    name=str(config.get("Info", "Name") or ""),
                    type=type(config).__name__.removesuffix("Config"),
                    projectName=project_name,
                    version=version,
                    busy=bool(getattr(config, "is_locked", False)),
                )
            )
        return items

    return MaaFWApiReply(data=await asyncio.to_thread(_collect))


async def clone_embedded(script_id: str, source_script_id: str) -> MaaFWApiReply:
    """``/maafw/embedded/clone``：从源脚本挂着的载荷物化本脚本的视图。

    载荷 + 视图口径：新视图从源脚本挂着的载荷物化（大文件与载荷共用，源的运行期状态
    不带），源脚本运行中也能建，只预约目标。``Info.Path`` 与 ``Embedded.*`` 沿用源脚本
    的记录；类型随项目（M9A 项目 → M9A）。
    """

    try:
        script_config = maafw_script_config(script_id)
        source_config = maafw_script_config(source_script_id)
    except (KeyError, ValueError, TypeError) as exc:
        return MaaFWApiReply.error(400, f"MFW 脚本无效: {exc}")
    if script_id == source_script_id:
        return MaaFWApiReply.error(400, "不能从脚本自己克隆")
    if busy := _embedded_busy_reason(script_config):
        return MaaFWApiReply.error(400, busy)

    target_dir = embedded_project_dir(script_id)
    # 老脚本换项目：目标原有副本钉定的版本在克隆后可能就没人用了
    previous_version = await _previous_maafw_version(target_dir)
    # 只预约目标：源脚本挂的是不可变载荷（正在切换就取 journal 的目标），物化不读源视图，
    # 源在运行 / 更新 / 准备环境都不影响。目标正被别的入口导入时不能同时写。
    target_reservation = await try_reserve_project_path(target_dir)
    if target_reservation is None:
        return MaaFWApiReply.error(400, EMBEDDED_COPY_BUSY)
    try:
        # 目标已有视图（老脚本换项目）在新视图建好后原子换掉，失败时原样不动。
        cloned = await asyncio.to_thread(
            clone_embedded_copy, source_script_id, script_id
        )
    except EmbeddedProjectError as exc:
        return MaaFWApiReply.error(400, f"克隆失败: {exc}")
    except Exception as exc:  # noqa: BLE001 - 文件系统异常也要原样给用户
        return MaaFWApiReply.error(400, f"克隆失败: {type(exc).__name__}: {exc}")
    finally:
        await release_project_path(target_reservation)
    if not cloned:
        return MaaFWApiReply.error(400, "源脚本没有可用的副本，先在它那边导入项目")

    inherited = inherit_embedded_record(source_config, script_id)
    await Config.update_script(
        script_id,
        {
            "Info": {"Path": str(source_config.get("Info", "Path") or "")},
            "Embedded": {
                "Report": json.dumps(inherited["report"], ensure_ascii=False),
                "SourceVersion": inherited["sourceVersion"],
                "ImportedAt": inherited["importedAt"],
            },
        },
    )
    await _apply_project_flavor(script_id)
    # 放在 retype 之后：权威集合在调用线程上按当前脚本表算，要看到换过类型的配置
    _reconcile_pool_after_copy_change("clone", target_dir, previous_version)
    data = await embedded_status_data(script_id, maafw_script_config(script_id))
    source_name = str(source_config.get("Info", "Name") or source_script_id[:8])
    return MaaFWApiReply(
        message=f"已复用「{source_name}」的项目，运行时与模型文件共用，不另占空间",
        data=data,
    )
