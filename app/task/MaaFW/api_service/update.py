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

"""``/maafw/update`` 背后的业务：手动检查 / 应用 MFW 项目更新；另有 ``/maafw/mirror-cdk``
查 Mirror 酱 CDK 状态（编辑页 CDK 输入框下的小字）。

应用走与运行前 / 运行后自动更新同一条 ``view_update.run_view_update``（一个组只更新
一次，参数经 ``update_session.UpdateSession`` 组装），区别只在：整段持本视图预约、拿谱系锁
限时、不读预检备忘（手动即强制重试）。入口 :func:`update_project` 拆成「解析请求 → 检查 /
应用」几步，面板推送收在 ``_UpdatePanel``。
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.models.config import MaaFWConfig as RuntimeMaaFWConfig
from app.models.schema import (
    MaaFWMirrorCdkData,
    MaaFWProjectUpdateData,
    WSMaaFWProjectUpdateProgressData,
)
from app.services.common.update import transport as _service_update_transport
from app.task.MaaFW.api_service.common import (
    MaaFWApiReply,
    logger,
    maafw_effective_root,
    maafw_group_members,
    maafw_script_config,
)
from app.task.MaaFW.api_service.update_job import (
    current_update_job,
    record_update_progress,
)
from app.task.MaaFW.tools.core.agent_env.env import DETAIL_LOG_PREFIX
from app.task.MaaFW.tools.core.interface.loader import (
    MaaFWInterfaceLoadError,
    load_interface_model_cached,
)
from app.task.MaaFW.tools.core.project_update import (
    ALERT_LOG_PREFIX,
    MaaFWProjectUpdateError,
    can_check_project_update,
    discover_maafw_project_update,
    update_maafw_project_if_needed,
)
from app.task.MaaFW.tools.core.project_update.progress import UpdateProgressEvent
from app.task.MaaFW.tools.core.project_update.updater import (
    _public_package_source,
)
from app.task.MaaFW.tools.embedded.embedded_project import (
    EmbeddedProjectError,
    follow_source_enabled,
    is_source_form,
    resolve_maafw_project_root,
    shell_hint_from_report,
)
from app.task.MaaFW.tools.embedded.project_path import (
    begin_project_updating,
    end_project_updating,
    is_project_updating,
    release_project_path,
    try_reserve_project_path,
)
from app.task.MaaFW.tools.embedded.update_credentials import (
    resolve_update_credentials,
    resolve_update_proxy_url,
)
from app.task.MaaFW.tools.embedded.update_progress import (
    MaaFWUpdateProgressTracker,
)
from app.task.MaaFW.tools.embedded.update_session import UpdateProxy, UpdateSession
from app.utils import get_logger, sanitize_log_message

UPDATE_SCRIPT_BUSY = "脚本正在运行，运行结束后再更新项目"
UPDATE_PROJECT_UPDATING = "该项目正在更新，请等当前更新完成"
# 预约被占、又不是在更新：编辑页准备运行环境、兄弟脚本的更新切过来后确认环境、导入 / 克隆、
# 启动期迁移都会短暂持有。分不清是哪一个，只说被占用，不说「正在运行」误导用户。
UPDATE_PROJECT_OCCUPIED = "项目正被占用（在准备运行环境或切换版本），请稍后再试"
UPDATE_FOLLOW_SOURCE = (
    "已开启「跟随来源目录（开发者模式）」，以来源目录为准、不做项目更新："
    "要换版本请直接更新来源目录（下次运行前自动重新导入），或先关掉开发者模式"
)
UPDATE_SOURCE_FORM = (
    "这是按源码形态导入的项目（interface 在 assets/、Agent 在源码目录），始终跟随来源目录、"
    "不做项目更新：直接改来源目录即可（下次运行前或点「立即同步」重新导入）；要用发行版请导入发行包"
)
# 没声明 rid、又不满足「下载源选 GitHub + interface 声明了 github 仓库」（那样就只看
# GitHub Release）时，MAS 没法检查这个项目的更新；判据见 can_check_project_update。
UPDATE_NO_MIRRORCHYAN_RID = (
    "该项目没有接入 Mirror 酱（interface.json 缺少 mirrorchyan_rid），"
    "MAS 无法检查它的更新"
)
# 这两种 CDK 状态不需要额外提示：ok 是正常，absent 在选 GitHub 源时本就无关。
_MAAFW_CDK_QUIET_STATUSES = frozenset({"ok", "absent"})
_maafw_update_logger = get_logger("MaaFW 项目更新")
# 手动更新拿项目锁的限时：另一次自动更新 / 预检正持有时回 409，不让同步请求
# 跟着等几分钟。自动路径不限时。
_MAAFW_MANUAL_UPDATE_LOCK_TIMEOUT_SECONDS = 5.0


def describe_update_busy(root_path: Path, *, script_running: bool) -> str:
    """现在不能手动更新的原因：正在更新 > 脚本在运行 > 项目被别的事占着。

    「正在更新」看 ``project_path`` 的更新登记（``run_view_update`` 持谱系锁那段与手动更新
    整段都会登记）；运行前 / 运行后自动更新时脚本也算在运行，但此时说「正在更新」更准。
    """

    if is_project_updating(root_path):
        return UPDATE_PROJECT_UPDATING
    if script_running:
        return UPDATE_SCRIPT_BUSY
    return UPDATE_PROJECT_OCCUPIED


def _maafw_httpx_proxy(proxy_url: str | None) -> Any:
    """代理地址字符串 → ``httpx.Proxy``；没配或填错回 None（本次直连）。

    地址里可能有账号密码，报错时也只说类型，不回显地址。
    """

    return UpdateProxy.parse(proxy_url, warn=_maafw_update_logger.warning).client


def _maafw_update_extra_fields(result: Any) -> dict[str, Any]:
    """按核心包约定的属性名读取 CDK / 版本附加字段，缺字段一律 None。

    核心包返回对象（discovery 或 result）带 ``version_name`` / ``source`` /
    ``cdk_status`` / ``cdk_message`` / ``cdk_expired_time`` / ``skipped_reason``；
    此处用 ``getattr(..., None)`` 读取，核心包尚未补齐时也能返回。
    """

    def _text(name: str) -> str | None:
        value = getattr(result, name, None)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    expired_raw = getattr(result, "cdk_expired_time", None)
    expired_time: int | None
    if isinstance(expired_raw, bool) or expired_raw is None:
        expired_time = None
    else:
        try:
            expired_time = int(expired_raw)
        except (TypeError, ValueError):
            expired_time = None

    return {
        "versionName": _text("version_name"),
        "cdkStatus": _text("cdk_status"),
        "cdkMessage": _text("cdk_message"),
        "cdkExpiredTime": expired_time,
        "skippedReason": _text("skipped_reason"),
    }


def _maafw_update_message_with_cdk(message: str, extra: dict[str, Any]) -> str:
    """CDK 状态异常时把提示原文附到摘要里。

    仍按成功返回（HTTP 200）：CDK 有问题只是这次装不了，脚本本身照常能跑，
    用户看到原因后可以去续期或改用 GitHub 源。
    """

    status = extra.get("cdkStatus")
    cdk_message = extra.get("cdkMessage")
    if status and status not in _MAAFW_CDK_QUIET_STATUSES and cdk_message:
        return f"{message}（{cdk_message}）"
    return message


def _maafw_update_source_config(script_config: RuntimeMaaFWConfig) -> dict[str, str]:
    """组装 MaaFW 项目更新实现所需的 source_config。

    只包含用户可配置的三项：``package_source``（脚本级 ``Update.Source``，
    Mirror 酱 / GitHub）、``mirror_cdk``、``channel``。三项**都只看脚本级、
    不做全局兜底**，与 ``tools/embedded/update_credentials.py`` 用的是同一个
    解析函数，保证手动更新与运行时自动更新的行为一致。

    仓库、tag、资产文件名等 GitHub 参数不再由用户填写，由核心包从
    ``interface.json`` 与目录名自行推断。

    额外注入 ``project_shell_hint``：GitHub 发行版常按 UI 外壳分包
    （如 M9A 同版本同时发 ``*-MFAA.zip`` 与 ``*-MXU.zip``），选包实现
    在项目名/平台收窄后需要外壳家族才能消歧。本 API 直连
    ``discover_maafw_project_update``，而该函数**自身不做兜底识别**
    （兜底在 ``update_maafw_project_if_needed`` 里），故必须在此补上。
    """

    # 三项都只看脚本级，不做全局兜底（与 embedded 侧的 resolve_update_credentials
    # 一致）：全局那两项服务的是 MAS 自身的更新，语义不同。
    credentials = resolve_update_credentials(script_config)
    config = {
        "mirror_cdk": credentials.cdk,
        "channel": credentials.channel,
        "package_source": credentials.package_source,
    }
    # 副本里没有 MFW.exe / maafw/ 可扫，外壳家族从导入报告取。
    shell_hint = shell_hint_from_report(script_config)
    if shell_hint:
        config["project_shell_hint"] = shell_hint
    return config


def _describe_group_ahead(version: str) -> str:
    return f"同项目的其他脚本已更新到 {version}，点「更新」即可切换（无需下载）"


def _group_ahead_version(root_path: Path, channel: str) -> str | None:
    """同项目、同更新通道的其他脚本已经更新到、比本脚本新的版本；没有为 None。

    只读视图标记与谱系记录（不联网）。本脚本运行中被跳过、随后又被停止时会落后于
    其他脚本；这时「更新」只是切过去，不用下载。
    """

    from app.task.MaaFW.tools.core.project_update.payloads import version_newer
    from app.task.MaaFW.tools.embedded.embedded_project import read_view_marker
    from app.task.MaaFW.tools.embedded.view_update import latest_entry

    marker = read_view_marker(root_path)
    if marker is None:
        return None
    entry = latest_entry(str(marker["lineage"]), channel)
    if entry is None or str(entry["id"]) == str(marker["payload"]):
        return None
    version = str(entry.get("version") or "")
    if not version_newer(version, str(marker.get("version") or "")):
        return None
    return version


async def _heal_projection(
    script_id: str,
    script_config: RuntimeMaaFWConfig,
    root_path: Path,
    *,
    channel: str,
    proxy: Any,
    proxy_url: str | None,
    shell_hint: str,
    send_log: Any,
) -> None:
    """手动检查更新前，旧投影规则建的载荷按当前规则补齐一次（与运行前同一条路，同组只查
    一次）。运行中、项目被占用或同项目正在更新时这次不查；失败只记日志，不影响检查。"""

    from app.task.MaaFW.tools.core.runtime_pool.architecture import (
        SUPPORTED_ARCHITECTURE,
        host_architecture,
    )
    from app.task.MaaFW.tools.embedded.view_heal import (
        heal_projection,
        projection_heal_due,
    )

    if getattr(script_config, "is_locked", False):
        return
    if host_architecture() != SUPPORTED_ARCHITECTURE:
        # 只支持 x64：补齐要按本机架构取发行包，非 x64 上注定失败；架构提示由后面的检查给出。
        _maafw_update_logger.info(
            f"本机架构是 {host_architecture()}，不是 {SUPPORTED_ARCHITECTURE}，"
            f"跳过旧规则载荷的补齐检查: {script_id}"
        )
        return
    if not await asyncio.to_thread(projection_heal_due, script_id, channel):
        return
    reservation = await try_reserve_project_path(root_path)
    if reservation is None:
        return
    try:
        await heal_projection(
            script_id,
            channel=channel,
            members=lambda: maafw_group_members(script_id),
            reservation_held=True,
            send_log=send_log,
            proxy=proxy,
            proxy_url=proxy_url,
            shell_hint=shell_hint,
            script_name=str(script_config.Info.Name or script_id[:8]),
            lock_timeout=_MAAFW_MANUAL_UPDATE_LOCK_TIMEOUT_SECONDS,
        )
    finally:
        await release_project_path(reservation)


class _UpdatePanel:
    """编辑页「更新过程」面板：阶段、下载 / 覆盖进度与逐行日志全程推给前端（每次请求一个）。

    更新实现的回调既会从事件循环里来（下载在协程里跑），也会从工作线程里来（新版本的构建 /
    预检 / 登记跑在 to_thread 里），统一跨回循环再发。必须在事件循环上构造。
    """

    def __init__(self, script_id: str) -> None:
        from app.core import Publisher
        from app.core.ws import protocol as ws_protocol

        self._publisher = Publisher
        self._message_type = ws_protocol.MAAFW_PROJECT_UPDATE_PROGRESS
        self.script_id = script_id
        self.tracker = MaaFWUpdateProgressTracker()
        self._loop = asyncio.get_running_loop()
        # 这次请求若是后台手动更新（update_job）就记下是哪一次；检查更新为 None。
        # 在这里取而不是推送时取：核心包的回调线程不一定带着上下文。
        self._job = current_update_job()

    def publish(self, data: WSMaaFWProjectUpdateProgressData | None) -> None:
        if data is None:
            return
        # 后台手动更新记一份过程，页面刷新后据此还原面板；只记这次应用自己的事件
        record_update_progress(self._job, data)
        asyncio.run_coroutine_threadsafe(
            self._publisher.send(id=self.script_id, type=self._message_type, data=data),
            self._loop,
        )

    def finished(
        self, *, success: bool, message: str, package_kind: str | None = None
    ) -> None:
        """调用方自己收尾的那条结论（检查路径没有核心包的 completed 事件）。"""

        self.publish(
            self.tracker.finished(
                success=success, message=message, package_kind=package_kind
            )
        )

    def send_update_log(self, line: str) -> None:
        """更新日志一行：后端日志 + 面板。"""

        # 写日志前先打码，避免 CDK 等敏感值落盘；WS 通道走同一份打码结果。
        text = sanitize_log_message(str(line))
        if text.startswith(ALERT_LOG_PREFIX):
            # 要用户留意的行（项目发错版本号）：去掉前缀，面板里整行标红
            text = text.removeprefix(ALERT_LOG_PREFIX)
            _maafw_update_logger.warning(text)
            self.publish(self.tracker.log(text, alert=True))
            return
        _maafw_update_logger.info(text)
        if text.startswith(DETAIL_LOG_PREFIX):
            # 详情行（预检里健康检查的完整 traceback）只进后端日志，不上更新面板
            return
        self.publish(self.tracker.log(text))

    def report(self, event: UpdateProgressEvent) -> None:
        """核心包的一条进度事件（``UpdateSession.progress`` 出口）。"""

        # events() 而不是 event()：解压开始前要多发一条旧前端（v5.6.0）能认的过渡消息。
        for data in self.tracker.events(event):
            self.publish(data)


@dataclass
class _UpdateRequest:
    """一次 ``/maafw/update`` 请求解析出的上下文（参数已校验、interface 已读）。"""

    script_id: str
    action: str
    script_config: Any
    root_path: Path
    interface: Any
    source_config: dict[str, Any]
    proxy: UpdateProxy
    panel: _UpdatePanel

    @property
    def current_version(self) -> str:
        return str(self.interface.version or "")

    @property
    def channel(self) -> str:
        return self.source_config["channel"]

    @property
    def can_check(self) -> bool:
        return can_check_project_update(self.interface, self.source_config)


async def update_project(script_id: str, action: str) -> MaaFWApiReply:
    """按脚本 ``Update.*`` 配置检查（``check``）或应用（``apply``）项目更新。"""

    request = await _open_update_request(script_id, action)
    if isinstance(request, MaaFWApiReply):
        return request
    if action == "check":
        return await _check_project_update(request)
    return await _apply_project_update(request)


async def _open_update_request(
    script_id: str, action: str
) -> _UpdateRequest | MaaFWApiReply:
    """校验脚本与项目目录、读 interface、解析下载源与代理；不能更新时直接给出回复。"""

    try:
        script_config = maafw_script_config(script_id)
    except (KeyError, ValueError, TypeError) as exc:
        return MaaFWApiReply.error(400, f"MFW 脚本无效: {exc}")
    if follow_source_enabled(script_config):
        # 开发者模式以来源目录为准：检查与应用都不做，别把开发者的改动换成发行版；源码形态
        # 本来就没有发行包可更新。
        return MaaFWApiReply.error(
            400,
            UPDATE_SOURCE_FORM
            if is_source_form(script_config)
            else UPDATE_FOLLOW_SOURCE,
        )

    root_path, error = await maafw_effective_root(script_id, "")
    if root_path is None:
        return MaaFWApiReply.error(400, error)
    if not root_path.is_dir():
        # 有效根是 MAS 管理的项目副本，不是 Info.Path，别让用户去查配置键。
        return MaaFWApiReply.error(
            400,
            "找不到项目文件。请关闭本页后重新打开，MAS 会尝试自动修复；"
            "仍不行就新建脚本重新导入",
        )

    try:
        interface = await asyncio.to_thread(load_interface_model_cached, root_path)
    except MaaFWInterfaceLoadError as exc:
        return MaaFWApiReply.error(400, f"MFW interface 读取失败: {exc}")
    except Exception as exc:
        logger.opt(exception=True).warning(
            f"update_maafw_project失败: {type(exc).__name__}: {exc}"
        )
        return MaaFWApiReply.error(500, f"MFW interface 读取失败: {exc}")

    source_config = _maafw_update_source_config(script_config)
    # 代理按脚本级解析（留空跟随全局），与运行前自动更新同一口径；地址可能带
    # user:pw，不进日志，也不走 ``Config.proxy``（它每次访问都记一行地址）。地址填错时
    # 下载已按直连，预检的 uv / pip 也整条直连（``url`` 成空串），别把一个 httpx 都不认的
    # 串再塞进子进程环境变量。
    proxy = UpdateProxy.parse(
        resolve_update_proxy_url(script_config), warn=_maafw_update_logger.warning
    )
    # CDK 值绝不进日志：只记录「有没有」。
    _maafw_update_logger.info(
        f"MFW 项目更新({action}): script={script_id} "
        f"channel={source_config['channel']} "
        f"cdk={'已配置' if source_config['mirror_cdk'] else '未配置'}"
    )
    return _UpdateRequest(
        script_id=script_id,
        action=action,
        script_config=script_config,
        root_path=root_path,
        interface=interface,
        source_config=source_config,
        proxy=proxy,
        panel=_UpdatePanel(script_id),
    )


# ---------------------------------------------------------------- 检查


async def _check_project_update(req: _UpdateRequest) -> MaaFWApiReply:
    """``check``：先补齐旧规则载荷，再只问远端有没有新版本（不换下载地址、不扣 CDK 额度）。"""

    req.panel.publish(req.panel.tracker.checking())
    await _heal_projection(
        req.script_id,
        req.script_config,
        req.root_path,
        channel=req.channel,
        proxy=req.proxy.client,
        proxy_url=req.proxy.url,
        shell_hint=str(req.source_config.get("project_shell_hint") or ""),
        send_log=req.panel.send_update_log,
    )
    # 组里已有比本脚本新的版本时，以它为准问远端（与应用时第 1 步组同步之后一致），
    # 远端没有更新的就提示「点更新即可切换」，别引导用户去配 CDK 或等下次运行。
    try:
        group_version = await asyncio.to_thread(
            _group_ahead_version, req.root_path, req.channel
        )
    except Exception as exc:  # noqa: BLE001 - 读不了就按视图版本检查
        _maafw_update_logger.warning(f"读取同项目已更新的版本失败: {exc}")
        group_version = None

    if not req.can_check:
        # 查不了时核心包只记一行「跳过更新检查」、返回 None，过去被当成「已是最新」。
        if group_version:
            return _reply_group_ahead(req, group_version)
        _maafw_update_logger.info(f"{UPDATE_NO_MIRRORCHYAN_RID}: {req.script_id}")
        req.panel.finished(success=False, message=UPDATE_NO_MIRRORCHYAN_RID)
        return MaaFWApiReply(
            message=UPDATE_NO_MIRRORCHYAN_RID,
            data=MaaFWProjectUpdateData(
                checked=False,
                currentVersion=req.current_version,
                skippedReason=UPDATE_NO_MIRRORCHYAN_RID,
            ),
        )
    discovered = await _discover_update(req, group_version)
    if isinstance(discovered, MaaFWApiReply):
        return discovered
    discovery, skipped = discovered
    if discovery is None:
        return _reply_nothing_discovered(req, group_version, skipped)
    return _reply_discovered(req, discovery, group_version)


def _reply_group_ahead(req: _UpdateRequest, group_version: str) -> MaaFWApiReply:
    """远端没有更新的（或查不了），但同项目其他脚本已有更新的版本：「更新」即可切过去。"""

    message = _describe_group_ahead(group_version)
    req.panel.finished(success=True, message=message)
    return MaaFWApiReply(
        message=message,
        data=MaaFWProjectUpdateData(
            checked=True,
            updateAvailable=True,
            installable=True,
            currentVersion=req.current_version,
            latestVersion=group_version,
            versionName=group_version,
        ),
    )


async def _discover_update(
    req: _UpdateRequest, group_version: str | None
) -> tuple[Any, list[str]] | MaaFWApiReply:
    """问远端（``version_only``）。返回 ``(discovery, 没查成的原因)``；出错时直接给出回复。"""

    skipped: list[str] = []
    try:
        discovery = await discover_maafw_project_update(
            req.interface,
            current_version=group_version or req.current_version,
            source_config=req.source_config,
            proxy=req.proxy.client,
            send_log=req.panel.send_update_log,
            # 只问有没有新版本：带 CDK 去换下载地址会扣一次今日额度，
            # 而用户可能只是随手点了下「检查更新」。真更新时再取。
            version_only=True,
            on_skipped=skipped.append,
            # 项目发错的高主版本号只在手动更新时拉回；检查时就告诉用户点「更新」会回退。
            allow_misnumbered_rollback=True,
        )
    except MaaFWProjectUpdateError as exc:
        message = f"MFW 更新检查失败: {exc}"
        req.panel.finished(success=False, message=message)
        return MaaFWApiReply.error(400, message)
    except Exception as exc:
        logger.opt(exception=True).warning(
            f"update_maafw_project失败: {type(exc).__name__}: {exc}"
        )
        message = f"MFW 更新检查失败: {exc}"
        req.panel.finished(success=False, message=message)
        return MaaFWApiReply.error(500, message)
    return discovery, skipped


def _reply_nothing_discovered(
    req: _UpdateRequest, group_version: str | None, skipped: list[str]
) -> MaaFWApiReply:
    """远端没有新版本：组里更新的优先，其次「没查成」，最后才是「已是最新」。"""

    if group_version:
        return _reply_group_ahead(req, group_version)
    if skipped:
        # 没查成（只看 GitHub 时连不上、没有可用的 Release）不是「已是最新」。
        message = skipped[0]
        req.panel.finished(success=False, message=message)
        return MaaFWApiReply(
            message=message,
            data=MaaFWProjectUpdateData(
                checked=False,
                currentVersion=req.current_version,
                skippedReason=message,
            ),
        )
    message = f"MFW 项目已是最新版本: {req.current_version or '未知'}"
    req.panel.finished(success=True, message=message)
    return MaaFWApiReply(
        message=message,
        data=MaaFWProjectUpdateData(checked=True, currentVersion=req.current_version),
    )


def _reply_discovered(
    req: _UpdateRequest, discovery: Any, group_version: str | None
) -> MaaFWApiReply:
    """远端有新版本：版本、下载来源、能不能装、CDK 状态。"""

    extra = _maafw_update_extra_fields(discovery)
    candidate = getattr(discovery, "candidate", None)
    # discovery.source 是版本元数据来源（恒标 Mirror 酱，GitHub 源取了 GitHub 上
    # 更新的版本时也一样）；响应里的 source
    # 要回答「会从哪里下载」：优先候选包来源，其次核心包的 package_source。
    # 一律用对外名（mirrorchyan / github）：candidate.source 是核心包的内部
    # 名（github_release），直接回给前端会让「下载来源」显示成 github_release。
    candidate_source = _public_package_source(
        (getattr(candidate, "source", None) if candidate is not None else None)
        or getattr(discovery, "package_source", None)
        or getattr(discovery, "source", None)
    )
    installable = bool(getattr(discovery, "installable", False))
    latest_version = getattr(discovery, "version", None) or extra["versionName"]
    extra["versionName"] = extra["versionName"] or latest_version
    message = (
        f"发现 MFW 项目新版本: {req.current_version or '未知'} -> {latest_version}"
    )
    unavailable_reason = getattr(discovery, "unavailable_reason", "")
    if not installable and unavailable_reason:
        message = f"{message}（暂无可安装更新包: {unavailable_reason}）"
        if group_version:
            # 远端的装不了，但同项目其他脚本已有更新的版本：「更新」能先切过去。
            message = f"{message}；{_describe_group_ahead(group_version)}"
            installable = True
    req.panel.finished(
        success=True,
        message=_maafw_update_message_with_cdk(message, extra),
        package_kind=(
            getattr(candidate, "package_type", None) if candidate is not None else None
        ),
    )
    return MaaFWApiReply(
        message=_maafw_update_message_with_cdk(message, extra),
        data=MaaFWProjectUpdateData(
            checked=True,
            updateAvailable=True,
            installable=installable,
            currentVersion=req.current_version,
            latestVersion=latest_version,
            source=candidate_source,
            **extra,
        ),
    )


# ---------------------------------------------------------------- 应用


async def _apply_project_update(req: _UpdateRequest) -> MaaFWApiReply:
    """``apply``：与运行前 / 运行后自动更新同一条 ``run_view_update``，整段持本视图预约。

    手动更新后跑不起来和自动更新是同一种坏：登记前同样在新版本上真建一次运行环境，建不出来
    就丢掉新版本（预检失败也按谱系写备忘，但手动路径不读备忘——它就是强制重试）。
    """

    # 只查版本随时可以；真切换要等运行结束（与 dev 一致，运行中的手动更新不支持）：
    # 运行中的脚本只经兄弟脚本的更新被动 pending，跑完后切。
    if getattr(req.script_config, "is_locked", False):
        return MaaFWApiReply.error(
            400, describe_update_busy(req.root_path, script_running=True)
        )
    # 下载 + 构建 + 预检要几分钟，锁只在这一刻查过一次：整段持有本视图的项目预约，
    # 运行前检查看到预约就按「正在更新」跳过；切换与之后的运行环境确认都在这段预约里。
    apply_reservation = await try_reserve_project_path(req.root_path)
    if apply_reservation is None:
        return MaaFWApiReply.error(
            400, describe_update_busy(req.root_path, script_running=False)
        )
    # 整段登记为「正在更新」（含切换后的环境确认），这期间再点更新说的是「正在更新」。
    updating_key = begin_project_updating(req.root_path)
    try:
        applied = await _run_apply(req)
        if isinstance(applied, MaaFWApiReply):
            return applied
    except MaaFWProjectUpdateError as exc:
        if exc.project_lock_busy:
            # 占着谱系锁的可能是同项目另一个脚本的手动 / 自动更新或补齐，原文已说清是谁。
            return MaaFWApiReply.error(409, str(exc))
        return MaaFWApiReply.error(400, f"MFW 项目更新失败: {exc}")
    except Exception as exc:
        logger.opt(exception=True).warning(
            f"update_maafw_project失败: {type(exc).__name__}: {exc}"
        )
        return MaaFWApiReply.error(500, f"MFW 项目更新失败: {exc}")
    finally:
        end_project_updating(updating_key)
        await release_project_path(apply_reservation)

    outcome, previous_version = applied
    await _after_apply(outcome, req.root_path, previous_version)
    return _apply_reply(req, outcome)


async def _run_apply(req: _UpdateRequest) -> tuple[Any, str | None] | MaaFWApiReply:
    """预约与「正在更新」登记里的那一段：更新、切换、确认运行环境、面板收尾。

    返回 ``(ViewUpdateOutcome, 更新前钉定的 maafw 版本)``；触发脚本还没采纳时直接给出回复。
    其余异常原样抛出，由 :func:`_apply_project_update` 映射成 HTTP 错误。
    """

    # 这几个模块会拉起 runtime_pool 与 agent_env，只在真要用时导入。
    from app.task.MaaFW.tools.core.runtime_pool import MaaFWRuntimePoolService
    from app.task.MaaFW.tools.embedded.env_confirm import (
        confirm_switched_environment,
    )
    from app.task.MaaFW.tools.embedded.pool_reconcile import previous_maafw_version
    from app.task.MaaFW.tools.embedded.runtime_route import (
        runtime_pool_route_from_service,
    )

    route = await asyncio.to_thread(
        lambda: runtime_pool_route_from_service(MaaFWRuntimePoolService())
    )
    # 记下更新前钉定的 maafw 版本：切换后若换了版本，旧 runtime 不必再等宽限。
    previous_version = await asyncio.to_thread(previous_maafw_version, req.root_path)
    session = UpdateSession(
        req.script_id,
        channel=req.channel,
        # 登记之后（持谱系锁、事件循环上）再抄同组候选，别用等锁 / 下载前的快照。
        members=lambda: maafw_group_members(req.script_id),
        reservation_held=True,
        send_log=req.panel.send_update_log,
        script_name=str(req.script_config.Info.Name or req.script_id[:8]),
        # 同步 HTTP 请求不该跟着同项目另一次自动更新 / 预检等几分钟。
        lock_timeout=_MAAFW_MANUAL_UPDATE_LOCK_TIMEOUT_SECONDS,
        proxy=req.proxy,
        progress=req.panel.report,
    )
    try:
        outcome = await session.run(_apply_core_call(req, session, route.root))
    except EmbeddedProjectError as exc:
        return MaaFWApiReply.error(400, f"MFW 项目更新失败: {exc}")
    if outcome.updated:
        # 切完就在自己这段预约里确认一次运行环境再放手：前端随后那次 prepare 会被
        # 「环境已就绪」短路（页面记的路径没变），不能指望它接。
        await confirm_switched_environment(
            req.root_path, req.panel.send_update_log, proxy_url=req.proxy.url
        )
    if outcome.updated and not outcome.registered_id:
        # 第 1 步组同步就切到了同项目其他脚本已有的版本，核心包随后的收尾说的是远端
        # （「已是最新」或「没有可安装的更新包」，后者按失败显示）：结论以切换为准。
        req.panel.finished(
            success=True, message=str(getattr(outcome.result, "message", "") or "")
        )
    elif not outcome.updated and not req.can_check:
        req.panel.finished(success=False, message=UPDATE_NO_MIRRORCHYAN_RID)
    return outcome, previous_version


def _apply_core_call(
    req: _UpdateRequest, session: UpdateSession, pool_root: str | Path
) -> Any:
    """手动更新的核心那一步：下载 / staging 构建 / 预检 / 登记（``run_view_update`` 的
    ``core_call``）。不读预检备忘（手动即强制重试），项目发错的高主版本号允许拉回。"""

    from app.task.MaaFW.tools.embedded.update_mirrors import (
        github_release_mirror_urls,
    )
    from app.task.MaaFW.tools.embedded.view_update import memo_path_factory

    async def core_call(view_path: Path, target: Any, after_register: Any) -> Any:
        view_interface = await asyncio.to_thread(
            lambda: load_interface_model_cached(view_path, force_reload=True)
        )
        memo_path_for = memo_path_factory(target.lineage)
        # 进度出口不交给环境准备：它的收尾事件 completed / failed 会被进度跟踪器当成
        # 更新终态，而此时还在 post_validating。预检里的 uv / pip 子进程也走脚本级代理。
        post_validate = session.precheck(
            pool_root=pool_root,
            failure={},
            previous_version=str(view_interface.version or ""),
            project_name=getattr(view_interface, "name", None),
            memo_path_for=memo_path_for,
            cancel_event=threading.Event(),
        )
        # 仓库、tag、资产名等 GitHub 参数不再传入：核心包从 interface.json 与
        # 目录名自行推断。**source_config 必须传**：它带着用户选定的下载源，
        # 漏了就会退回缺省的 GitHub——check 说走 Mirror 酱、apply 却从 GitHub
        # 下载，正是本次设计要禁掉的静默换源。
        # 检查 / 下载 / 构建 / 预检的收尾事件（completed / failed）由更新实现
        # 自己经 progress 发出，这里不再补发。
        return await update_maafw_project_if_needed(
            view_path,
            view_interface,
            mirror_cdk=req.source_config["mirror_cdk"],
            channel=req.channel,
            source_config=req.source_config,
            proxy=session.proxy.client,
            send_log=session.send_log,
            progress=session.core_progress(),
            post_validate=post_validate,
            projection=True,
            # 手动更新与运行前自动更新用同一套加速镜像，否则「手动快、自动慢」。
            github_mirror_urls=github_release_mirror_urls,
            payload=target,
            after_register=after_register,
            # 项目发错的高主版本号只在手动更新时拉回，运行前 / 运行后自动更新不回退。
            allow_misnumbered_rollback=True,
        )

    return core_call


async def _after_apply(
    outcome: Any, root_path: Path, previous_version: str | None
) -> None:
    """放掉预约之后：作废这个版本的预检备忘、新旧 runtime 对账（都只记日志、不影响回复）。"""

    from app.task.MaaFW.tools.core.project_update import clear_runtime_precheck
    from app.task.MaaFW.tools.embedded.pool_reconcile import reconcile_in_background
    from app.task.MaaFW.tools.embedded.view_update import memo_path_factory

    result = outcome.result
    if outcome.registered_id:
        # 登记成功即预检建出了环境，这个版本上次运行前更新留下的备忘（若有）作废。
        try:
            await asyncio.to_thread(
                clear_runtime_precheck,
                memo_path_factory(outcome.lineage)(
                    str(getattr(result, "latest_version", "") or "")
                ),
            )
        except Exception as exc:  # noqa: BLE001
            _maafw_update_logger.warning(f"清理运行环境预检备忘失败: {exc}")
    if bool(getattr(result, "updated", False)):
        # 新版本的 runtime 预检时已建好；旧版本的那份在谱系里最后一个视图离开后才可能无人引用。
        reconcile_in_background(
            "manual-update",
            updated_project_path=root_path,
            previous_version=previous_version,
        )


def _apply_reply(req: _UpdateRequest, outcome: Any) -> MaaFWApiReply:
    result = outcome.result
    extra = _maafw_update_extra_fields(result)
    message = str(getattr(result, "message", "") or "") or "MFW 项目更新完成"
    if not outcome.updated and not req.can_check:
        message = UPDATE_NO_MIRRORCHYAN_RID
    return MaaFWApiReply(
        message=_maafw_update_message_with_cdk(message, extra),
        data=MaaFWProjectUpdateData(
            checked=bool(getattr(result, "checked", True)),
            updated=bool(getattr(result, "updated", False)),
            updateAvailable=bool(getattr(result, "update_available", False)),
            installable=bool(getattr(result, "installable", False)),
            currentVersion=(
                getattr(result, "current_version", None)
                or getattr(result, "previous_version", None)
                or req.current_version
            ),
            latestVersion=getattr(result, "latest_version", None)
            or extra["versionName"],
            source=getattr(result, "source", None),
            **extra,
        ),
    )


async def query_mirror_cdk(script_id: str, cdk: str) -> MaaFWApiReply:
    """``/maafw/mirror-cdk``：编辑页 CDK 输入框下那行小字要的 CDK 状态与到期时间。

    CDK 用请求里的值（输入框当前值，失焦后保存可能还没落盘）；渠道与代理按脚本级
    ``Update.*``，与手动更新同一口径。项目根按脚本取视图，但**不**像 ``/maafw/update``
    那样先补建视图——这只是一行提示，不该在打开页面时触发导入；视图不在、interface 读不了
    都按 ``unsupported`` 返回，界面上什么都不显示。查不到（网络等）同样按成功返回
    ``error``，不报红字。
    """

    try:
        script_config = maafw_script_config(script_id)
    except (KeyError, ValueError, TypeError) as exc:
        return MaaFWApiReply.error(400, f"MFW 脚本无效: {exc}")

    rid = ""
    status = "unsupported"
    expired_time: int | None = None
    root_path = resolve_maafw_project_root(script_id, script_config)
    try:
        interface = (
            await asyncio.to_thread(load_interface_model_cached, root_path)
            if root_path.is_dir()
            else None
        )
    except Exception:  # noqa: BLE001 - 读不了就是不支持，不让这行提示报错
        interface = None
    if interface is not None:
        rid = str(interface.mirrorchyan_rid or "").strip()
    if rid:
        status = "absent"
        if cdk.strip():
            from app.task.MaaFW.tools.core.runtime_pool.architecture import (
                supported_architecture_target,
            )

            try:
                target = supported_architecture_target()
                result = await _service_update_transport.query_mirror_cdk_status(
                    rid,
                    cdk=cdk,
                    channel=resolve_update_credentials(script_config).channel,
                    # 代理地址可能带 user:pw，不进日志，也不走 ``Config.proxy``
                    proxy=_maafw_httpx_proxy(resolve_update_proxy_url(script_config)),
                    platform_os=target.mirrorchyan_os,
                    platform_arch=target.mirrorchyan_arch,
                    timeout=30,
                )
                status = result.status
                expired_time = result.expired_time
            except Exception as error:  # 查询失败不影响编辑页，也不泄露请求 URL。
                status = "error"
                _maafw_update_logger.warning(
                    f"MFW CDK 状态查询失败: {type(error).__name__}"
                )
    # CDK 一个字符都不进日志
    _maafw_update_logger.info(
        f"MFW CDK 状态查询: script={script_id} rid={rid or '无'} status={status}"
    )
    return MaaFWApiReply(
        data=MaaFWMirrorCdkData(status=status, expiredTime=expired_time)
    )
