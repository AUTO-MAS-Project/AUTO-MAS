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

"""``/maafw/update`` 背后的业务：手动检查 / 应用 MFW 项目更新。

应用走与运行前 / 运行后自动更新同一条 ``view_update.run_view_update``（一个组只更新
一次），区别只在：整段持本视图预约、拿谱系锁限时、不读预检备忘（手动即强制重试）。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from app.models.config import MaaFWConfig as RuntimeMaaFWConfig
from app.models.schema import MaaFWProjectUpdateData, WSMaaFWProjectUpdateProgressData
from app.task.MaaFW.api_service.common import (
    MaaFWApiReply,
    logger,
    maafw_effective_root,
    maafw_group_members,
    maafw_script_config,
)
from app.task.MaaFW.tools.core.automas_maafw_interface.loader import (
    MaaFWInterfaceLoadError,
    load_interface_model_cached,
)
from app.task.MaaFW.tools.core.automas_maafw_project_update import (
    MaaFWProjectUpdateError,
    discover_maafw_project_update,
    update_maafw_project_if_needed,
)
from app.task.MaaFW.tools.core.automas_maafw_project_update.updater import (
    _public_package_source,
)
from app.task.MaaFW.tools.embedded.embedded_project import (
    EmbeddedProjectError,
    shell_hint_from_report,
)
from app.task.MaaFW.tools.embedded.project_path import (
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
from app.utils import get_logger
from app.utils.security import sanitize_log_message

UPDATE_SCRIPT_BUSY = "脚本正在运行，运行结束后再更新项目"
# 这两种 CDK 状态不需要额外提示：ok 是正常，absent 在选 GitHub 源时本就无关。
_MAAFW_CDK_QUIET_STATUSES = frozenset({"ok", "absent"})
_maafw_update_logger = get_logger("MaaFW 项目更新")
# 手动更新拿项目锁的限时：另一次自动更新 / 预检正持有时回 409，不让同步请求
# 跟着等几分钟。自动路径不限时。
_MAAFW_MANUAL_UPDATE_LOCK_TIMEOUT_SECONDS = 5.0


def _maafw_httpx_proxy(proxy_url: str | None) -> Any:
    """代理地址字符串 → ``httpx.Proxy``；没配或填错回 None（本次直连）。

    地址里可能有账号密码，报错时也只说类型，不回显地址。
    """

    if not proxy_url:
        return None
    import httpx

    try:
        return httpx.Proxy(proxy_url)
    except Exception as exc:  # noqa: BLE001 - 代理填错不该让整次更新 500
        _maafw_update_logger.warning(
            f"MFW 项目更新代理地址无效（{type(exc).__name__}），本次直连"
        )
        return None


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


async def update_project(script_id: str, action: str) -> MaaFWApiReply:
    """按脚本 ``Update.*`` 配置检查（``check``）或应用（``apply``）项目更新。"""

    try:
        script_config = maafw_script_config(script_id)
    except (KeyError, ValueError, TypeError) as exc:
        return MaaFWApiReply.error(400, f"MFW 脚本无效: {exc}")

    root_path, error = await maafw_effective_root(script_id, "")
    if root_path is None:
        return MaaFWApiReply.error(400, error)
    if not root_path.is_dir():
        return MaaFWApiReply.error(400, "MFW 项目路径不是有效目录，请检查 Info.Path")

    try:
        interface = await asyncio.to_thread(load_interface_model_cached, root_path)
    except MaaFWInterfaceLoadError as exc:
        return MaaFWApiReply.error(400, f"MFW interface 读取失败: {exc}")
    except Exception as exc:
        logger.opt(exception=True).warning(
            f"update_maafw_project失败: {type(exc).__name__}: {exc}"
        )
        return MaaFWApiReply.error(500, f"MFW interface 读取失败: {exc}")

    current_version = str(interface.version or "")
    source_config = _maafw_update_source_config(script_config)
    # 代理按脚本级解析（留空跟随全局），与运行前自动更新同一口径；地址可能带
    # user:pw，不进日志，也不走 ``Config.proxy``（它每次访问都记一行地址）。
    proxy_url = resolve_update_proxy_url(script_config)
    proxy = _maafw_httpx_proxy(proxy_url)
    if proxy_url and proxy is None:
        # 地址填错：下载已按直连，预检的 uv / pip 也整条直连，别把一个
        # httpx 都不认的串再塞进子进程环境变量。
        proxy_url = ""
    # CDK 值绝不进日志：只记录「有没有」。
    _maafw_update_logger.info(
        f"MFW 项目更新({action}): script={script_id} "
        f"channel={source_config['channel']} "
        f"cdk={'已配置' if source_config['mirror_cdk'] else '未配置'}"
    )

    from app.core.ws import protocol as ws_protocol
    from app.core.ws.publisher import Publisher

    # 编辑页「更新过程」面板：阶段、下载 / 覆盖进度与逐行日志全程推给前端。
    # 更新实现的回调既会从事件循环里来（下载在协程里跑），也会从工作线程里来
    # （新版本的构建 / 预检 / 登记跑在 to_thread 里），统一跨回循环再发。
    tracker = MaaFWUpdateProgressTracker()
    loop = asyncio.get_running_loop()

    def publish_progress(data: WSMaaFWProjectUpdateProgressData | None) -> None:
        if data is None:
            return
        asyncio.run_coroutine_threadsafe(
            Publisher.send(
                id=script_id,
                type=ws_protocol.MAAFW_PROJECT_UPDATE_PROGRESS,
                data=data,
            ),
            loop,
        )

    def send_update_log(line: str) -> None:
        # 写日志前先打码，避免 CDK 等敏感值落盘；WS 通道走同一份打码结果。
        text = sanitize_log_message(str(line))
        _maafw_update_logger.info(text)
        publish_progress(tracker.log(text))

    def report_progress(event: dict[str, Any]) -> None:
        publish_progress(tracker.event(event))

    if action == "check":
        publish_progress(tracker.checking())
        try:
            discovery = await discover_maafw_project_update(
                interface,
                current_version=current_version,
                source_config=source_config,
                proxy=proxy,
                send_log=send_update_log,
                # 只问有没有新版本：带 CDK 去换下载地址会扣一次今日额度，
                # 而用户可能只是随手点了下「检查更新」。真更新时再取。
                version_only=True,
            )
        except MaaFWProjectUpdateError as exc:
            message = f"MFW 更新检查失败: {exc}"
            publish_progress(tracker.finished(success=False, message=message))
            return MaaFWApiReply.error(400, message)
        except Exception as exc:
            logger.opt(exception=True).warning(
                f"update_maafw_project失败: {type(exc).__name__}: {exc}"
            )
            message = f"MFW 更新检查失败: {exc}"
            publish_progress(tracker.finished(success=False, message=message))
            return MaaFWApiReply.error(500, message)

        if discovery is None:
            message = f"MFW 项目已是最新版本: {current_version or '未知'}"
            publish_progress(tracker.finished(success=True, message=message))
            return MaaFWApiReply(
                message=message,
                data=MaaFWProjectUpdateData(
                    checked=True, currentVersion=current_version
                ),
            )

        extra = _maafw_update_extra_fields(discovery)
        candidate = getattr(discovery, "candidate", None)
        # discovery.source 是版本元数据来源（恒为 Mirror 酱）；响应里的 source
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
            f"发现 MFW 项目新版本: {current_version or '未知'} -> {latest_version}"
        )
        unavailable_reason = getattr(discovery, "unavailable_reason", "")
        if not installable and unavailable_reason:
            message = f"{message}（暂无可安装更新包: {unavailable_reason}）"
        publish_progress(
            tracker.finished(
                success=True,
                message=_maafw_update_message_with_cdk(message, extra),
                package_kind=(
                    getattr(candidate, "package_type", None)
                    if candidate is not None
                    else None
                ),
            )
        )
        return MaaFWApiReply(
            message=_maafw_update_message_with_cdk(message, extra),
            data=MaaFWProjectUpdateData(
                checked=True,
                updateAvailable=True,
                installable=installable,
                currentVersion=current_version,
                latestVersion=latest_version,
                source=candidate_source,
                **extra,
            ),
        )

    # 手动更新后跑不起来和自动更新是同一种坏：登记前同样在新版本上真建一次运行环境，
    # 建不出来就丢掉新版本（预检失败也按谱系写备忘，但手动路径不读备忘——它就是强制重试）。
    # 这几个模块会拉起 runtime_pool 与 agent_env，只在真要用时导入。
    import functools
    import threading

    from app.task.MaaFW.embedded_manager import MaaFWEmbeddedManager
    from app.task.MaaFW.tools.core.automas_maafw_project_update import (
        clear_runtime_precheck,
    )
    from app.task.MaaFW.tools.core.automas_maafw_runtime_pool import (
        MaaFWRuntimePoolService,
    )
    from app.task.MaaFW.tools.embedded.pool_reconcile import (
        previous_maafw_version,
        reconcile_in_background,
    )
    from app.task.MaaFW.tools.embedded.precheck import (
        build_precheck_validator,
        precheck_agent_root,
    )
    from app.task.MaaFW.tools.embedded.runtime_route import (
        runtime_pool_route_from_service,
    )
    from app.task.MaaFW.tools.embedded.update_mirrors import (
        github_release_mirror_urls,
    )
    from app.task.MaaFW.tools.embedded.view_update import (
        memo_path_factory,
        run_view_update,
    )

    # 只查版本随时可以；真切换要等运行结束（与 dev 一致，运行中的手动更新不支持）：
    # 运行中的脚本只经兄弟脚本的更新被动 pending，跑完后切。
    if getattr(script_config, "is_locked", False):
        return MaaFWApiReply.error(400, UPDATE_SCRIPT_BUSY)
    # 下载 + 构建 + 预检要几分钟，锁只在这一刻查过一次：整段持有本视图的项目预约，
    # 运行前检查看到预约就按「正在更新」跳过；切换与之后的运行环境确认都在这段预约里。
    apply_reservation = await try_reserve_project_path(root_path)
    if apply_reservation is None:
        return MaaFWApiReply.error(400, UPDATE_SCRIPT_BUSY)

    precheck_failure: dict[str, Any] = {}
    script_name = str(script_config.get("Info", "Name") or script_id[:8])
    try:
        route = await asyncio.to_thread(
            lambda: runtime_pool_route_from_service(MaaFWRuntimePoolService())
        )
        # 记下更新前钉定的 maafw 版本：切换后若换了版本，旧 runtime 不必再等宽限。
        previous_version = await asyncio.to_thread(previous_maafw_version, root_path)

        async def core_call(view_path: Path, target: Any, after_register: Any) -> Any:
            view_interface = await asyncio.to_thread(
                lambda: load_interface_model_cached(view_path, force_reload=True)
            )
            memo_path_for = memo_path_factory(target.lineage)
            # 不把 report_progress 交给环境准备：它的收尾事件 completed / failed 会被
            # 进度跟踪器当成更新终态，而此时还在 post_validating。
            post_validate = build_precheck_validator(
                # 预检里的 uv / pip 子进程也走脚本级代理；用 partial 绑上去，
                # ``PrepareProjectEnvironment`` 的签名不变。
                prepare=functools.partial(
                    MaaFWEmbeddedManager._prepare_project_environment_sync,
                    proxy_url=proxy_url,
                ),
                cancel_event=threading.Event(),
                send_log=send_update_log,
                agent_env_root=precheck_agent_root(route.root),
                failure=precheck_failure,
                previous_version=str(view_interface.version or ""),
                project_name=getattr(view_interface, "name", None),
                memo_path_for=memo_path_for,
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
                mirror_cdk=source_config["mirror_cdk"],
                channel=source_config["channel"],
                source_config=source_config,
                proxy=proxy,
                send_log=send_update_log,
                progress=report_progress,
                post_validate=post_validate,
                projection=True,
                # 手动更新与运行前自动更新用同一套加速镜像，否则「手动快、自动慢」。
                github_mirror_urls=github_release_mirror_urls,
                payload=target,
                after_register=after_register,
            )

        try:
            outcome = await run_view_update(
                script_id,
                channel=source_config["channel"],
                # 登记之后（持谱系锁、事件循环上）再抄同组候选，别用等锁 / 下载前的快照。
                members=lambda: maafw_group_members(script_id),
                reservation_held=True,
                send_log=send_update_log,
                core_call=core_call,
                script_name=script_name,
                # 同步 HTTP 请求不该跟着同项目另一次自动更新 / 预检等几分钟。
                lock_timeout=_MAAFW_MANUAL_UPDATE_LOCK_TIMEOUT_SECONDS,
            )
        except EmbeddedProjectError as exc:
            return MaaFWApiReply.error(400, f"MFW 项目更新失败: {exc}")
        result = outcome.result
        if outcome.updated:
            # 切完就在自己这段预约里确认一次运行环境再放手：前端随后那次 prepare 会被
            # 「环境已就绪」短路（页面记的路径没变），不能指望它接。
            send_update_log("正在确认新版本的运行环境")
            try:
                await asyncio.to_thread(
                    MaaFWEmbeddedManager._prepare_project_environment_sync,
                    root_path,
                    threading.Event(),
                    send_update_log,
                    proxy_url=proxy_url,
                )
                send_update_log("运行环境已就绪")
            except Exception as exc:  # noqa: BLE001 - 确认失败不算更新失败，运行前还会再备
                _maafw_update_logger.warning(f"更新后确认运行环境失败: {exc}")
                send_update_log(f"运行环境确认失败（运行前会再准备）: {exc}")
    except MaaFWProjectUpdateError as exc:
        if exc.project_lock_busy:
            return MaaFWApiReply.error(409, "MFW 项目正在自动更新/预检中，请稍后再试")
        return MaaFWApiReply.error(400, f"MFW 项目更新失败: {exc}")
    except Exception as exc:
        logger.opt(exception=True).warning(
            f"update_maafw_project失败: {type(exc).__name__}: {exc}"
        )
        return MaaFWApiReply.error(500, f"MFW 项目更新失败: {exc}")
    finally:
        await release_project_path(apply_reservation)

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

    extra = _maafw_update_extra_fields(result)
    message = str(getattr(result, "message", "") or "") or "MFW 项目更新完成"
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
                or current_version
            ),
            latestVersion=getattr(result, "latest_version", None)
            or extra["versionName"],
            source=getattr(result, "source", None),
            **extra,
        ),
    )
