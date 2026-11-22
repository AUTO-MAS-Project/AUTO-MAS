"""一个脚本一轮的项目会话：打开项目、按需更新、确认运行环境、收尾项目、预下载（项目更新一侧）。

将来是项目更新这一块对外的「打开项目（拿预约、补视图、按需更新，返回租约）/ 收尾项目」与「发现
更新、预下载」，通用 MFW、M9A、MSS 三个专项各自的流程都调它。现在还是内置代码，先把接缝切出来：

- **只收普通数据**（:class:`MaaFWProjectRequest`）：托管 uid 与名字、来源路径、更新渠道与时机、
  是否开发者模式、更新代理、Mirror CDK 等现在从脚本配置里读的值，由调用方取好传进来。这里不读
  脚本配置对象、不导入任务类。
- **不写配置**：导入 / 重建之后要写回的项目记录作为普通数据（:class:`MaaFWProjectRecordUpdate`）
  随结局交给调用方，由调用方照原来的时机写回；要弹的任务通知同样作为返回值
  （:class:`MaaFWProjectNotice`）交回。
- **结局明确**：打开项目的结局是打开成功 / 良性跳过（项目正在切换版本、正在更新、被占用，
  调用方据此把脚本记成「跳过」）/ 失败 / 已停止，都是返回值，良性跳过不用异常表达。
- **过程输出只经一个事件出口**（:data:`MaaFWProjectSink`，做法同 ``plan_run.MaaFWPlanRunSink``）：
  一行项目更新日志（:class:`MaaFWProjectLog`）、一个运行进度点（:class:`MaaFWProjectPoint`，名字与
  取值同 ``app.task.run_flow``，由调用方以自己为 owner 上报）、预下载的字节进度
  （:class:`MaaFWProjectDownload`）。日志与进度点在事件循环线程里同步调用（工作线程里来的日志先经
  ``call_soon_threadsafe`` 转回事件循环），下载进度在下载回调所在处同步调用；出口自己不要抛异常。
  不往事件里塞对象或回调，出口窄到以后能换成「开始 / 取事件和结果 / 停止」。

内置形态下还留着三处临时做法，属主登记（下一步）之后去掉：

1. 同组候选（``members``）与按脚本 id 查名字（``display_name``）是构造时交进来的两个现取函数：
   候选要在拿到谱系锁、登记之后才抄（拿的是切换那一刻的运行状态），以后改成现取属主服务。
2. ``embedded_project`` / ``update_credentials`` 里的辅助函数还按属性读「脚本配置形状」的对象，
   这里用请求现摆一个只读的形状交给它们（:func:`_config_shape`），不回写。
3. 打开项目时调用方要在预约里接着做自己的事（写回项目记录、补默认队列、拿配置 X 锁），而且用户
   停止时这些也得做完再交回预约：所以预约在 :meth:`MaaFWProjectSession.reserve` 拿、
   :meth:`MaaFWProjectSession.release` 放，调用方把「补视图 + 自己的那几步」包成一个任务交给
   :meth:`MaaFWProjectSession.hold` 等，停止时的宽限与「等不到就把释放交给任务完成回调」都在这里。
"""

from __future__ import annotations

import asyncio
import functools
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Literal, TypeVar

from app.task.MaaFW.tools.core.file_lockers import describe_lockers_async
from app.task.MaaFW.tools.core.project_update.payloads import (
    lineage_info_from_interface,
)
from app.task.MaaFW.tools.embedded.embedded_project import (
    EmbeddedProjectError,
    GroupMember,
    effective_channel,
    embedded_project_dir,
    ensure_embedded_copy,
    env_confirm_pending,
    follow_source_enabled,
    is_source_form,
    read_view_marker,
    resolve_maafw_project_root,
    shell_hint_from_report,
    switch_or_confirm_in_progress,
)
from app.task.MaaFW.tools.embedded.project_path import (
    is_project_updating,
    release_project_path,
    release_project_path_sync,
    try_reserve_project_path,
)
from app.task.MaaFW.tools.embedded.update_credentials import (
    AutoUpdateMode,
    MaaFWUpdateCredentials,
    describe_cdk,
    describe_proxy,
    resolve_auto_update_mode,
    resolve_update_credentials,
    resolve_update_proxy_url,
)
from app.task.MaaFW.tools.embedded.view_heal import heal_projection
from app.utils import get_logger, sanitize_log_message
from app.utils.common.process.scope import current_process_scope

if TYPE_CHECKING:  # pragma: no cover
    from app.models.schema import DownloadRequest
    from app.task.MaaFW.tools.embedded.update_session import UpdateProxy
    from app.task.run_flow import PointState, RunStage

# 与管理器同一个名字：后端日志里这段流程的行照旧记在「MFW 内置运行」下
logger = get_logger("MFW 内置运行")

_T = TypeVar("_T")

# 取消运行环境准备（以及打开项目时停止）后等线程收尾的上限，与 ``plan_run`` 里那条准备路径的
# ``_PREPARE_ENVIRONMENT_CANCEL_GRACE_SECONDS`` 取同一个值（那边导入即打开 maa DLL，不为一个
# 常数把它拉进来）。
_ENV_PREPARE_CANCEL_GRACE_SECONDS = 2.0
# 取消项目更新后等收尾的上限。下载完成之后新版本在 staging 里构建、预检（真建
# 运行环境），取消令牌要等预检里的 uv / pip 子进程退出、staging 删掉；登记之后
# 不再响应取消，要等切换做完。等不到才放手（staging 残留由启动期清理）。
_UPDATE_CANCEL_GRACE_SECONDS = 60.0
# 还停在下载阶段时取消的宽限：令牌在两个 chunk 之间就生效，
# ``.partial`` 与断点原样留着下次续传，等不到就放手。
_UPDATE_DOWNLOAD_CANCEL_GRACE_SECONDS = 5.0
_BYTES_PER_MB = 1024 * 1024
# 运行前投影补齐等谱系锁的上限：同项目正在更新（兄弟脚本的运行前更新可能要几分钟）就
# 这次不查，不让运行前检查跟着等。
_PROJECTION_HEAL_LOCK_TIMEOUT_SECONDS = 1.0
# CDK 距到期不足这些天时提醒用户续费
CDK_EXPIRY_WARNING_DAYS = 7

_UPDATE_SOURCE_ZH = {"mirrorchyan": "Mirror 酱", "github": "GitHub"}
# 核心包没给 cdk_message 时的兜底文案；正常情况下以核心包的原文为准
# 不再说「改用 GitHub」：下载源是用户选的，CDK 有问题时不会自动换源。
_CDK_STATUS_FALLBACK_ZH = {
    "expired": "Mirror 酱 CDK 已过期",
    "invalid": "Mirror 酱 CDK 无效",
    "quota": "Mirror 酱 CDK 今日下载次数已用尽",
    "mismatched": "Mirror 酱 CDK 类型与该资源不匹配",
    "blocked": "Mirror 酱 CDK 已被封禁",
}

# 运行前检查拿不到本视图预约时的整脚本跳过：项目被同项目的更新 / 编辑页操作暂时占着，
# 不是故障，脚本记「跳过」、发 warning（与调度层「已被其他任务调度器锁定」同一口径）。
SKIP_SWITCHING = (
    "同项目的另一个脚本刚更新了项目，本托管正在切换到新版本，已跳过本次启动，"
    "稍后重新开始即可"
)
SKIP_UPDATING = (
    "这个脚本的项目正在更新（可能是编辑页里的操作），已跳过本次启动，完成后重新开始即可"
)
SKIP_OCCUPIED = (
    "这个脚本的项目正在更新或准备运行环境（可能是编辑页里的操作），已跳过本次启动，"
    "完成后重新开始即可"
)
BENIGN_SKIPS = frozenset({SKIP_SWITCHING, SKIP_UPDATING, SKIP_OCCUPIED})

NoticeLevel = Literal["info", "warning"]
SkipReason = Literal["switching", "updating", "occupied"]


# ---------------------------------------------------------------------------
# 入参、事件与结局（都是普通数据）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MaaFWProjectSibling:
    """同来源的其它托管（视图和来源都没了时，从它的项目重建）。字段是它配置里的原值。"""

    script_id: str
    name: Any
    source_path: Any
    report: Any
    source_version: Any


@dataclass(frozen=True)
class MaaFWProjectRequest:
    """一个托管做项目操作要用的值，都是调用方从脚本配置里取好的原值。

    - ``script_id``：托管 uid；``name``：托管名（``Info.Name``）；``script_name``：运行树里脚本
      节点的名字（日志里「同项目的脚本「X」正在更新」用它）。
    - ``source_path``：来源目录（``Info.Path``）；``report`` / ``source_version``：导入报告与来源
      版本（``Embedded.Report`` / ``Embedded.SourceVersion``）；``follow_source``：开发者模式开关
      （``Embedded.FollowSource``，源码形态由报告判断）。
    - ``update_source`` / ``channel`` / ``mirror_cdk`` / ``auto_update_mode`` / ``package_mode``：
      ``Update.Source`` / ``Channel`` / ``MirrorChyanCDK`` / ``AutoUpdateMode`` / ``PackageMode``；
      ``proxy_address``：托管级更新代理（``Update.ProxyAddress``，留空跟随全局）。
    - ``siblings``：同来源重建的候选（只有打开项目要）；``prefetch_paths``：任务参数里队列预下载
      交来的路径映射；``round_started_at``：本轮开始时刻（收尾只清在它之前轮转出的原生日志备份）。
    """

    script_id: str
    name: Any = ""
    script_name: str = ""
    source_path: Any = ""
    report: Any = ""
    source_version: Any = ""
    follow_source: Any = False
    update_source: Any = ""
    channel: Any = ""
    # CDK 明文与可能带 ``user:pw@`` 的代理地址：不进 repr，免得请求被打进日志时露出来
    mirror_cdk: Any = field(default="", repr=False)
    auto_update_mode: Any = ""
    package_mode: Any = ""
    proxy_address: Any = field(default="", repr=False)
    siblings: tuple[MaaFWProjectSibling, ...] = ()
    prefetch_paths: Any = field(default_factory=dict)
    round_started_at: float = 0.0


@dataclass(frozen=True, slots=True)
class MaaFWProjectLog:
    """一行项目更新日志（调用方写进脚本日志与账号日志，详情前缀的行只进后端日志）。"""

    message: str


@dataclass(frozen=True, slots=True)
class MaaFWProjectPoint:
    """一个运行进度点：``stage`` / ``state`` / ``key`` 与 ``app.task.run_flow.point`` 同义。"""

    stage: RunStage
    state: PointState = "entered"
    key: str = ""


@dataclass(frozen=True, slots=True)
class MaaFWProjectDownload:
    """预下载的字节进度（只发下载阶段）。"""

    downloaded: int
    total: int


MaaFWProjectEvent = MaaFWProjectLog | MaaFWProjectPoint | MaaFWProjectDownload
MaaFWProjectSink = Callable[[MaaFWProjectEvent], None]


@dataclass(frozen=True)
class MaaFWProjectRecordUpdate:
    """导入 / 重建之后要写回托管的项目记录：导入报告、来源版本、导入时间。"""

    report: Mapping[str, Any]
    source_version: str
    imported_at: str


@dataclass(frozen=True)
class MaaFWProjectLease:
    """打开成功后调用方要用的东西：视图（有效项目根）、interface 位置、视图挂的版本。"""

    script_id: str
    view_path: Path
    interface_path: Path
    version: str


@dataclass(frozen=True)
class MaaFWProjectOpenOutcome:
    """打开项目的结局。

    - ``opened``：视图就绪，``lease`` 有值；
    - ``skipped``：良性跳过（``skip`` 说是哪种，``reason`` 是给用户的一句话），脚本记「跳过」；
    - ``failed``：``reason`` 是给用户的一句话，脚本记「异常」；
    - ``stopped``：用户停止了，后面的步骤没再做。

    ``record`` 不论结局都要先写回（导入做完了、后面一步才失败或被停止时也有）。
    ``env_confirm_needed``：视图标记显示还欠一次运行环境确认（``envConfirmedFor`` ≠ 当前载荷）。
    """

    kind: Literal["opened", "skipped", "failed", "stopped"]
    reason: str = ""
    skip: SkipReason | None = None
    lease: MaaFWProjectLease | None = None
    record: MaaFWProjectRecordUpdate | None = None
    env_confirm_needed: bool = False


@dataclass(frozen=True)
class MaaFWProjectNotice:
    """要弹给用户的一条任务通知（调用方发）。"""

    level: Literal["info", "warning", "error"]
    message: str


@dataclass(frozen=True)
class MaaFWProjectCloseOutcome:
    """收尾项目的结局：``env_confirm_needed`` = 收尾组同步切了版本，还欠一次运行环境确认。"""

    env_confirm_needed: bool = False


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------


def _config_shape(request: MaaFWProjectRequest) -> SimpleNamespace:
    """把请求摆成 ``embedded_project`` / ``update_credentials`` 辅助函数认的「脚本配置形状」。

    它们按 ``Info.Path``、``Update.Channel``、``Embedded.Report`` 这样的属性读；这里只给它们读，
    不回写，也碰不到真的配置对象。属主登记之后让这些辅助函数直接收字段，再去掉它。
    """

    return SimpleNamespace(
        Info=SimpleNamespace(Path=request.source_path, Name=request.name),
        Update=SimpleNamespace(
            Source=request.update_source,
            Channel=request.channel,
            MirrorChyanCDK=request.mirror_cdk,
            AutoUpdateMode=request.auto_update_mode,
            PackageMode=request.package_mode,
            ProxyAddress=request.proxy_address,
        ),
        Embedded=SimpleNamespace(
            Report=request.report,
            FollowSource=request.follow_source,
            SourceVersion=request.source_version,
        ),
    )


def _sibling_shape(sibling: MaaFWProjectSibling) -> SimpleNamespace:
    return SimpleNamespace(
        Info=SimpleNamespace(Path=sibling.source_path, Name=sibling.name),
        Embedded=SimpleNamespace(
            Report=sibling.report, SourceVersion=sibling.source_version
        ),
    )


def _update_proxy(shape: Any) -> UpdateProxy:
    """本托管更新要用的代理：给子进程的字符串与给核心包的 ``httpx.Proxy``。

    托管级 ``Update.ProxyAddress`` 优先，留空跟随全局。地址可能带
    ``user:pw@``，**一个字符都不进日志**——要说明用了哪一层，
    看 ``describe_proxy``。填错了只警告一句并按直连跑，不让更新直接崩。
    没配（托管级与全局都空）一律给 None。填错时字符串给空串而不是 None：None 在
    运行环境准备里的意思是「没解析过，沿用全局」，那会变成下载直连、装依赖却走全局代理——
    同一份配置两种行为。填错就整条直连。
    """

    from app.task.MaaFW.tools.embedded.update_session import UpdateProxy

    return UpdateProxy.parse(
        resolve_update_proxy_url(shape) or None, warn=logger.warning
    )


def _load_interface_model(project_path: Path, *, force_reload: bool = False):
    """读 interface（走核心包的内存/磁盘缓存）；``force_reload`` 用于更新后失效缓存。"""

    from app.task.MaaFW.tools.core.interface import load_interface_model_cached

    return load_interface_model_cached(project_path, force_reload=force_reload)


def _runtime_pool_route():
    """解析 Runtime Pool 路由（root + poolId）。

    **只在工作线程里调**（``asyncio.to_thread``）：构造服务要拿进程级的池锁，
    别的线程正持锁建 base venv / 装解释器 / 回收时会等上几秒到几分钟，放在事件
    循环上整个后端都跟着停住。
    """

    from app.task.MaaFW.tools.core.runtime_pool import MaaFWRuntimePoolService
    from app.task.MaaFW.tools.embedded.runtime_route import (
        runtime_pool_route_from_service,
    )

    return runtime_pool_route_from_service(MaaFWRuntimePoolService())


def _release_after_work(key: str, task: asyncio.Task[Any]) -> None:
    """停止后交出去的预约：工作线程收完再放；顺手取走异常，免得报「never retrieved」。"""

    if not task.cancelled():
        task.exception()
    release_project_path_sync(key)


def _format_at(value: Any) -> str:
    text = str(value or "")
    return text[:16].replace("T", " ") if text else "未知时间"


def _result_field(result: Any, name: str, *fallbacks: str) -> Any:
    """按契约字段名读更新结果；dataclass 与 dict 都要能取到，缺字段当 None。

    允许给备选名，是为了兼容核心包里同义的旧字段（如 ``current_version`` 之于
    ``previous_version``），不是为了容忍字段缺失。
    """

    for key in (name, *fallbacks):
        value = getattr(result, key, None)
        if value is None and isinstance(result, Mapping):
            value = result.get(key)
        if value is not None:
            return value
    return None


def describe_update_result(
    result: Any, *, now: float | None = None
) -> list[tuple[NoticeLevel, str]]:
    """把核心包的更新结果翻成给用户看的几行话。

    只翻译，不判断要不要阻断——这一层从不阻断运行。返回 ``(级别, 文案)``，
    warning 只给 CDK 异常与即将到期，其余都是 info。
    """

    lines: list[tuple[NoticeLevel, str]] = []
    updated = bool(_result_field(result, "updated"))
    skipped_reason = _result_field(result, "skipped_reason")
    previous_version = _result_field(result, "previous_version", "current_version")
    version_name = _result_field(result, "version_name", "latest_version")
    source = _result_field(result, "source")
    message = _result_field(result, "message")

    if updated:
        source_zh = (
            _UPDATE_SOURCE_ZH.get(str(source).lower(), str(source))
            if source
            else "未知"
        )
        lines.append(
            (
                "info",
                f"MFW 项目已更新 {previous_version or '未知'} → "
                f"{version_name or '未知'}（来源：{source_zh}）",
            )
        )
    elif skipped_reason:
        lines.append(("info", f"MFW 项目更新已跳过：{skipped_reason}"))
    elif message:
        lines.append(("info", f"MFW 项目更新：{message}"))

    cdk_status = str(_result_field(result, "cdk_status") or "").strip().lower()
    cdk_message = str(_result_field(result, "cdk_message") or "").strip()
    if cdk_status and cdk_status not in ("ok", "absent"):
        lines.append(
            (
                "warning",
                cdk_message
                or _CDK_STATUS_FALLBACK_ZH.get(
                    cdk_status, f"Mirror 酱 CDK 状态异常（{cdk_status}）"
                ),
            )
        )
    elif cdk_message:
        lines.append(("info", cdk_message))

    expired_time = _result_field(result, "cdk_expired_time")
    if expired_time is not None:
        try:
            expired_at = float(expired_time)
        except (TypeError, ValueError):
            expired_at = None
        if expired_at is not None:
            current = time.time() if now is None else now
            days_left = (expired_at - current) / 86400
            if days_left <= CDK_EXPIRY_WARNING_DAYS:
                expired_date = (
                    datetime.fromtimestamp(expired_at).astimezone().strftime("%Y-%m-%d")
                )
                if days_left < 0:
                    lines.append(("warning", f"Mirror 酱 CDK 已于 {expired_date} 到期"))
                else:
                    lines.append(
                        (
                            "warning",
                            f"Mirror 酱 CDK 将于 {expired_date} 到期"
                            f"（剩余 {max(int(days_left), 0)} 天）",
                        )
                    )
    return lines


def describe_precheck_failure(phase_zh: str, failure: Mapping[str, Any]) -> str:
    """预检失败给用户看的一句话；按 ``kind`` 分文案。"""

    from app.task.MaaFW.tools.core.agent_env.import_check import (
        KIND_AGENT_MODULE_MISSING,
    )
    from app.task.MaaFW.tools.core.project_update.precheck_memo import (
        KIND_BINDING_UNAVAILABLE,
    )

    name = str(failure.get("projectName") or "MFW 项目").strip()
    target = str(failure.get("targetVersion") or "新版本").strip()
    previous = str(failure.get("previousVersion") or "当前版本").strip()
    if failure.get("kind") == KIND_AGENT_MODULE_MISSING:
        # 原因本身就是整句（缺哪个模块、哪里引用、继续用哪个版本），不再套一层
        reason = str(failure.get("reason") or "").strip().splitlines()
        if reason:
            return f"MFW 项目{phase_zh}更新（{name} {target}）：{reason[0]}"
    if failure.get("kind") == KIND_BINDING_UNAVAILABLE:
        requirement = str(failure.get("requirement") or "maafw").strip()
        return (
            f"MFW 项目{phase_zh}更新：{name} {target} 需要 "
            f"{requirement.replace('==', ' ')}，无法从 PyPI / GitHub 获取，"
            f"本次不升级，继续 {previous}"
        )
    reason = str(failure.get("reason") or "").strip()
    summary = next(
        (line.strip() for line in reason.splitlines() if line.strip()), "无原因"
    )
    if len(summary) > 120:
        summary = summary[:119] + "…"
    return (
        f"MFW 项目{phase_zh}更新：运行环境预检失败（{summary}），"
        f"本次不升级，继续 {previous}"
    )


def describe_open_failure(script_id: str, exc: BaseException) -> str:
    """打开项目时出错给用户的一句话；不是 ``EmbeddedProjectError`` 的连同堆栈记一行告警。"""

    if isinstance(exc, EmbeddedProjectError):
        return str(exc)
    logger.opt(exception=exc).warning(f"MFW 项目导入失败（{script_id}）：{exc}")
    return f"MFW 项目导入失败：{exc}"


def _source_config(credentials: MaaFWUpdateCredentials, shape: Any) -> dict[str, Any]:
    """发现更新 / 预下载给核心包的来源配置。"""

    return {
        "package_source": credentials.package_source,
        "mirror_cdk": credentials.cdk,
        "channel": credentials.channel,
        "project_shell_hint": shell_hint_from_report(shape),
    }


async def discover_prefetch(request: MaaFWProjectRequest) -> list[DownloadRequest]:
    """按项目更新模式和凭据发现可用更新，跳过跟随源码的项目并返回发行文件下载需求。"""

    from app.models.schema import DownloadRequest
    from app.task.MaaFW.tools.core.project_update.updater import (
        discover_maafw_project_update,
    )

    shape = _config_shape(request)
    if resolve_auto_update_mode(shape) == "Off" or follow_source_enabled(shape):
        return []
    credentials = resolve_update_credentials(shape)
    project = resolve_maafw_project_root(request.script_id, shape).resolve()
    source = _source_config(credentials, shape)
    proxy = _update_proxy(shape).client
    from app.task.MaaFW.tools.core.interface import load_interface_model_cached

    interface = await asyncio.to_thread(load_interface_model_cached, project)
    marker = await asyncio.to_thread(read_view_marker, project)
    if marker is None or not marker.get("lineage"):
        # No trustworthy lineage: leave update discovery to the normal
        # startup path, which can recover and revalidate project metadata.
        return []
    discovery = await discover_maafw_project_update(
        interface,
        source_config=source,
        proxy=proxy,
        prefer_full_package=True,
    )
    if (
        discovery is None
        or discovery.candidate is None
        or not discovery.candidate.download_url
    ):
        return []
    candidate = discovery.candidate
    return [
        DownloadRequest(
            url=candidate.download_url,
            rid=candidate.artifact_id or None,
            content_hash=candidate.sha256 or None,
            downloader="builtin" if candidate.source.lower() == "mirrorchyan" else None,
        )
    ]


# ---------------------------------------------------------------------------
# 项目会话
# ---------------------------------------------------------------------------


class MaaFWProjectSession:
    """一个脚本一轮的项目会话（管理器一份）。

    - 打开项目：:meth:`reserve` 拿预约 → 调用方把 :meth:`prepare` 与自己在预约里的那几步包成
      任务交给 :meth:`hold` → :meth:`release` 交回预约；
    - 运行前更新：:meth:`update` + :meth:`confirm_environment`；
    - 收尾项目：:meth:`close`（组同步、写穿巡检、清原生日志备份），切了版本再
      :meth:`confirm_environment`；
    - 预下载：:meth:`prefetch` / :meth:`discard_prefetch`（发现更新是模块函数
      :func:`discover_prefetch`，不要会话）；预下载的候选留在会话里，:meth:`update` 按项目身份
      核对后用。
    - :meth:`stop`：收尾期间用户点了停止（外层取消被基类挡在收尾外面）：运行后更新 / 环境确认
      按停止处理。
    """

    def __init__(
        self,
        emit: MaaFWProjectSink,
        *,
        members: Callable[[], Sequence[GroupMember]],
        display_name: Callable[[str], str],
    ) -> None:
        self._emit = emit
        self._members = members
        self._display_name = display_name
        # 打开项目拿到的本视图预约；交给任务完成回调去放之后为 None。
        self._open_key: str | None = None
        # 打开项目期间用户停止时置位的令牌：正在跑的那一步做完，后面的步骤不再开始。
        self._open_stop = threading.Event()
        # 收尾期间的停止（见 :meth:`stop`）。
        self._stop_requested = asyncio.Event()
        # 更新进度的最近一次事件；用户点停止时据此选文案与宽限时长。
        self._update_stage: str | None = None
        self._update_downloaded: int | None = None
        self._update_total: int | None = None
        # 队列预下载的候选：(项目身份, (下载时的项目版本, 发现结果))。
        self._prefetched_project_update: tuple[str, Any] | None = None
        self._prefetched_project_identity: tuple[Any, ...] | None = None

    # ------------------------------------------------------------------ 出口

    def _log(self, message: str) -> None:
        self._emit(MaaFWProjectLog(message))

    def _point(
        self, stage: RunStage, state: PointState = "entered", key: str = ""
    ) -> None:
        self._emit(MaaFWProjectPoint(stage, state, key))

    def _threadsafe_log(self) -> Callable[[str], None]:
        """给会在工作线程里回调的下游用的日志入口：转回事件循环线程再发事件。

        更新与环境准备都把 ``send_log`` 交给 ``asyncio.to_thread`` 里的同步代码；调用方的出口
        会碰事件循环上的对象（写脚本日志会 ``create_task`` 推 WS），在别的线程里直接调会
        ``RuntimeError: no running event loop``，异常还会被上层的容错吞掉。
        """

        loop = asyncio.get_running_loop()

        def send_log(message: str) -> None:
            loop.call_soon_threadsafe(self._log, message)

        return send_log

    # ------------------------------------------------------------------ 停止

    def stop(self) -> None:
        """收尾期间用户点了停止：运行后更新 / 环境确认提前停下（见 :meth:`_await_or_stop`）。"""

        self._stop_requested.set()

    @property
    def stop_requested(self) -> bool:
        return self._stop_requested.is_set()

    @property
    def stopping(self) -> bool:
        """打开项目期间用户停止了（:meth:`hold` 被取消）：调用方在预约里的后续步骤不再开始。"""

        return self._open_stop.is_set()

    async def _await_or_stop(self, task: asyncio.Future[Any]) -> bool:
        """等 ``task`` 完成，返回 True；收尾期用户点了停止就提前返回 False。

        与 ``asyncio.shield`` 一样不取消 ``task``；外层取消照常从这里抛
        ``CancelledError``。收尾里外层取消到不了（基类把它挡在 finalizer 外面），
        只能靠 :meth:`stop`。
        """

        if task.done():
            return True
        if self._stop_requested.is_set():
            return False
        stop_wait = asyncio.ensure_future(self._stop_requested.wait())
        try:
            await asyncio.wait({task, stop_wait}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            stop_wait.cancel()
        return task.done()

    # ------------------------------------------------------------------ 打开项目

    async def reserve(self, script_id: str) -> MaaFWProjectOpenOutcome | None:
        """拿本视图的项目预约；拿不到返回良性跳过的结局，拿到返回 None（之后必须 :meth:`release`）。

        导入期间持有项目预约（更新 / 准备正拿着就先不动副本）。
        """

        view = embedded_project_dir(script_id)
        key = await try_reserve_project_path(view)
        if key is None:
            if await asyncio.to_thread(switch_or_confirm_in_progress, script_id):
                # 视图正在换版本，或刚被兄弟脚本的更新切过去、后台还在确认运行环境
                # （预约在确认线程手里）：整个脚本一句话跳过，别让每个账号在
                # runner_task 里各报一遍「同一路径正在运行或更新」。
                return MaaFWProjectOpenOutcome(
                    "skipped", SKIP_SWITCHING, skip="switching"
                )
            if is_project_updating(view):
                # 编辑页的「执行更新」整段持本视图预约（下载可能几十分钟）：放行的话每个
                # 用户都拿不到预约、各自跳过，脚本却记成「完成」。
                return MaaFWProjectOpenOutcome(
                    "skipped", SKIP_UPDATING, skip="updating"
                )
            return MaaFWProjectOpenOutcome("skipped", SKIP_OCCUPIED, skip="occupied")
        self._open_key = key
        self._open_stop = threading.Event()
        return None

    async def prepare(self, request: MaaFWProjectRequest) -> MaaFWProjectOpenOutcome:
        """持预约补视图：缺视图就导入、组同步、投影补齐、读确认标记、看视图在不在。

        导入失败、同步之外的任何异常都翻成 ``failed`` 的结局（不抛）；用户停止时正在跑的那一步
        做完就返回 ``stopped``。导入做了的，``record`` 带着要写回的项目记录。
        """

        script_id = request.script_id
        stop = self._open_stop
        shape = _config_shape(request)
        record: MaaFWProjectRecordUpdate | None = None
        try:
            # 在工作线程里回调：必须走线程安全的转发。
            rebuilt = await asyncio.to_thread(
                ensure_embedded_copy,
                script_id,
                shape,
                send_log=self._threadsafe_log(),
                # 来源目录已删、副本又没了：可以从同来源的其它托管克隆
                siblings=[
                    (sibling.script_id, _sibling_shape(sibling))
                    for sibling in request.siblings
                ],
                # 开发者模式：比一次来源目录，变了就重新导入（日志一行说清）；
                # 刚关掉时回到 Update.Channel 的组。
                follow_source_check=True,
            )
            if rebuilt is not None:
                record = MaaFWProjectRecordUpdate(
                    report=rebuilt["report"],
                    source_version=rebuilt["sourceVersion"],
                    imported_at=rebuilt["importedAt"],
                )
            if stop.is_set():
                return MaaFWProjectOpenOutcome("stopped", record=record)
            # 组同步（§3.1 第 9 步）：组里已是别的版本（兄弟更新了、改了渠道）就在
            # 上锁之前切过去——配置一个字段都不写。切没切都看一眼标记：还欠确认
            # （本次切的、或此前哪条路径切完没确认上）就由调用方在账号任务前补。
            await self._sync_view_to_group(request, "运行前", reservation_held=True)
            if stop.is_set():
                return MaaFWProjectOpenOutcome("stopped", record=record)
            # 旧投影规则建的载荷按当前规则补齐（同组只查一次，从不抛）：补齐后本视图
            # 与同组空闲脚本切过去，下面的 envConfirmedFor 据此补一次运行环境确认。
            # 同项目正在更新时不等锁，这次不查。开发者模式下视图按当前规则从来源导入，
            # 也不做项目更新，不查。
            if not follow_source_enabled(shape):
                proxy = _update_proxy(shape)
                await heal_projection(
                    script_id,
                    channel=resolve_update_credentials(shape).channel,
                    members=self._members,
                    reservation_held=True,
                    send_log=self._threadsafe_log(),
                    proxy=proxy.client,
                    proxy_url=proxy.url,
                    shell_hint=shell_hint_from_report(shape),
                    script_name=request.script_name,
                    lock_timeout=_PROJECTION_HEAL_LOCK_TIMEOUT_SECONDS,
                    cancel_event=stop,
                )
            view = embedded_project_dir(script_id)
            marker = await asyncio.to_thread(read_view_marker, view)
            env_confirm_needed = env_confirm_pending(marker)
        except Exception as exc:  # noqa: BLE001 - OSError 之类也要给用户一句话
            return MaaFWProjectOpenOutcome(
                "failed", describe_open_failure(script_id, exc)
            )
        if not view.resolve().is_dir():
            return MaaFWProjectOpenOutcome(
                "failed",
                "请设置包含 interface.json 的 MFW 项目目录",
                record=record,
                env_confirm_needed=env_confirm_needed,
            )
        return MaaFWProjectOpenOutcome(
            "opened",
            lease=MaaFWProjectLease(
                script_id=script_id,
                view_path=view,
                interface_path=view / "interface.json",
                version=str((marker or {}).get("version") or ""),
            ),
            record=record,
            env_confirm_needed=env_confirm_needed,
        )

    async def hold(self, work: asyncio.Task[_T]) -> _T:
        """持着 :meth:`reserve` 的预约等 ``work``（:meth:`prepare` 加调用方在预约里的那几步）。

        导入 / 组同步 / 投影补齐都在工作线程里改视图：用户这时点停止，``await`` 会立刻抛出，
        线程却还在写 staging、换入视图。预约必须等线程收完再放，否则马上重开、编辑页准备环境或
        手动更新都能拿到预约，同时动同一棵视图。被取消时置位停止令牌（后面的步骤不再开始），
        在有限宽限内等 ``work`` 做完；等不到就把释放交给它的完成回调（:meth:`release` 那时
        什么都不做），再把取消抛出去。
        """

        process_scope = current_process_scope.get()
        if process_scope is not None:
            process_scope.retain_worker(work)
        try:
            return await asyncio.shield(work)
        except asyncio.CancelledError:
            self._open_stop.set()
            if process_scope is None or not process_scope.closed:
                with suppress(BaseException):
                    await asyncio.wait_for(
                        asyncio.shield(work),
                        timeout=_ENV_PREPARE_CANCEL_GRACE_SECONDS,
                    )
            if not work.done() and self._open_key is not None:
                key, self._open_key = self._open_key, None
                work.add_done_callback(functools.partial(_release_after_work, key))
            raise

    async def release(self) -> None:
        """交回 :meth:`reserve` 拿的预约（已交给任务完成回调、或没拿到时什么都不做）。"""

        key, self._open_key = self._open_key, None
        if key is not None:
            await release_project_path(key)

    # ------------------------------------------------------------------ 组同步

    async def _sync_view_to_group(
        self, request: MaaFWProjectRequest, phase_zh: str, *, reservation_held: bool
    ) -> bool:
        """§3.1 第 9 步：本视图挂的载荷 ≠ 组（谱系 + 渠道）的 latest 就切过去；返回是否切了。

        升级、兄弟更新后的被动 pending、改渠道后的降级都是这一条；一个配置字段都不写。
        被兄弟的更新立即切换过的，标记里有 ``switchedBy``：打一行日志再清掉（只在持有
        本视图预约时清）。切换失败只记日志（视图留在原版本、照常运行），下次再同步。
        """

        from app.task.MaaFW.tools.embedded.embedded_project import (
            clear_switched_by,
            read_view_marker,
        )
        from app.task.MaaFW.tools.embedded.view_update import (
            latest_entry,
            sync_view_to_group,
        )

        script_id = request.script_id
        view = embedded_project_dir(script_id)
        try:
            marker = await asyncio.to_thread(read_view_marker, view)
            switched_by = (marker or {}).get("switchedBy")
            if reservation_held and isinstance(switched_by, Mapping):
                at = _format_at(switched_by.get("at"))
                version = (marker or {}).get("version") or "新版本"
                if str(switched_by.get("scriptId") or "") == "迁移":
                    self._log(f"已于 {at} 在升级迁移时与同项目其他托管统一到 {version}")
                else:
                    name = str(switched_by.get("name") or "") or self._display_name(
                        str(switched_by.get("scriptId") or "")
                    )
                    self._log(f"已于 {at} 随脚本「{name}」的更新切换到 {version}")
                await asyncio.to_thread(clear_switched_by, view)
            # 开发者模式下组是本托管的私有渠道（latest 就是上次从来源导入的那份）。
            channel = effective_channel(script_id, _config_shape(request))
            entry_now = (
                await asyncio.to_thread(
                    latest_entry, str((marker or {}).get("lineage") or ""), channel
                )
                if marker is not None
                else None
            )
            previous_maafw: str | None = None
            if entry_now is not None and str(entry_now["id"]) != str(marker["payload"]):
                # 要切了：记下切之前钉定的 maafw 版本，切完它若已没有视图在用，运行池
                # 对账时豁免宽限（与更新提交后同一条路）。
                from app.task.MaaFW.tools.embedded.pool_reconcile import (
                    previous_maafw_version,
                )

                previous_maafw = await asyncio.to_thread(previous_maafw_version, view)
            result = await sync_view_to_group(
                script_id, channel, reservation_held=reservation_held
            )
        except Exception as exc:  # noqa: BLE001 - 同步失败不挡运行，视图留在原版本
            # 换视图被占用（rename 拒绝访问）时尽力点出占用者；查不到就什么都不加。
            lockers = await describe_lockers_async(exc)
            suffix = f"（{lockers}）" if lockers else ""
            logger.opt(exception=True).warning(
                f"MFW 组同步失败，本轮沿用当前版本：{exc}{suffix}"
            )
            self._log(f"切换到同组版本失败，本轮沿用当前版本：{exc}{suffix}")
            return False
        if result is None:
            return False
        if previous_maafw:
            # 组同步把本视图从旧版本切走：若它是最后一个离开旧 maafw 版本的视图，旧
            # runtime 不必再等 24 h 宽限（``reconcile_after_project_update`` 按全部视图判断
            # 旧版本还有没有人用）。后台线程跑，不拖运行。
            try:
                from app.task.MaaFW.tools.embedded.live_projects import (
                    reconcile_in_background,
                )

                reconcile_in_background(
                    "group-sync",
                    updated_project_path=view,
                    previous_version=previous_maafw,
                )
            except Exception as exc:  # noqa: BLE001 - 对账失败只影响回收时机
                logger.warning(f"MFW 组同步后的运行池对账未能启动：{exc}")
        entry = await asyncio.to_thread(latest_entry, result.lineage, channel)
        by = str((entry or {}).get("by") or "")
        if by == "迁移":
            origin = "升级迁移时统一"
        else:
            # 这个版本是谁怎么来的：更新得来的说「更新」，选目录导入的说「导入」。
            kind = str(((entry or {}).get("source") or {}).get("kind") or "")
            verb = "导入" if kind == "import" else "更新"
            origin = (
                f"由脚本「{self._display_name(by)}」"
                f"于 {_format_at((entry or {}).get('at'))} {verb}"
            )
        self._log(f"{phase_zh}已切到 {result.version}（{origin}）")
        with suppress(Exception):
            await asyncio.to_thread(_load_interface_model, view, force_reload=True)
        return True

    # ------------------------------------------------------------------ 更新

    def _build_update_progress_reporter(
        self, send_log: Callable[[str], None]
    ) -> Callable[[Any], None]:
        """把核心包的进度事件翻成项目更新日志行，顺带记下最近阶段。

        回调既会从事件循环里来（下载跑在协程里），也会从 apply 的工作线程里
        来，所以统一走 ``send_log``（:meth:`_threadsafe_log` 的转发），
        逐行**追加**、不做原地改写。

        阶段与字节数按**原始事件**记，不等翻译结果：翻译按 5% 吞掉绝大多数
        事件，只认翻译结果的话，取消时报出来的已下载量会落后一大截。

        收核心包的 dict 事件或已转好的 ``UpdateProgressEvent``（``UpdateSession`` 的
        ``progress`` 出口给的是后者）。
        """

        from app.task.MaaFW.tools.core.project_update.progress import (
            UpdateProgressEvent,
        )
        from app.task.MaaFW.tools.embedded.update_progress import (
            MaaFWUpdateTaskLogTranslator,
        )

        translator = MaaFWUpdateTaskLogTranslator()

        def report(raw_event: Any) -> None:
            event = UpdateProgressEvent.of(raw_event)
            stage = event.stage
            if stage:
                self._update_stage = stage
            if stage in {"downloading", "downloaded"}:
                downloaded = event.downloaded_bytes
                if downloaded is not None:
                    self._update_downloaded = downloaded
                total = event.total_bytes
                if total:
                    self._update_total = total
            try:
                line = translator.event(event)
            except Exception:  # noqa: BLE001 - 进度只是旁观，不能拖垮更新
                logger.opt(exception=True).warning("MFW 更新进度翻译失败")
                return
            if line:
                send_log(line)

        return report

    def _describe_update_cancel(self) -> tuple[str, float]:
        """按最近的更新阶段给「已中止」的文案和等收尾的上限。

        下载停得下来（令牌在两个 chunk 之间生效，断点留着下次续传），所以只
        等几秒；下载完成之后新版本在 staging 里构建 / 预检，停下就是丢 staging，
        但要等预检里的 uv / pip 子进程退出，给满宽限；登记之后不再响应取消。
        """

        stage = self._update_stage
        if stage in (None, "checking"):
            return "已中止更新检查", _UPDATE_DOWNLOAD_CANCEL_GRACE_SECONDS
        downloaded_bytes = self._update_downloaded or 0
        total = self._update_total
        if stage == "downloading" and not (total and downloaded_bytes >= total):
            downloaded = downloaded_bytes / _BYTES_PER_MB
            done = (
                f"已下载 {downloaded:.1f} / {total / _BYTES_PER_MB:.1f} MB"
                if total
                else f"已下载 {downloaded:.1f} MB"
            )
            return (
                f"已中止更新下载：{done}，下次运行从断点续传",
                _UPDATE_DOWNLOAD_CANCEL_GRACE_SECONDS,
            )
        if stage in ("committed", "completed"):
            # 新版本已登记：不再响应取消，切换约 2 s，做完再返回。
            return "新版本已就绪，正在切换，请稍候", _UPDATE_CANCEL_GRACE_SECONDS
        # 下载完成之后到登记之前（解压 extracting / 构建 / 预检 / 入库）都在 staging 上，
        # 取消 = 丢掉 staging，没有回滚。解压（条目检查每 500 条、写盘每个条目与每 1 MB 块）
        # 与并入共用库（每个文件）都查令牌，下一个检查点就停；之后删半截目录的耗时随已写出
        # 的文件数增长。宽限仍给满，是等预检里被令牌终止的 uv / pip 子进程退出。
        # 这段里再说「下次续传」就是生产上那次「提示与后台不一致」的翻版。
        return (
            "正在中止更新（丢弃未完成的新版本），请稍候",
            _UPDATE_CANCEL_GRACE_SECONDS,
        )

    async def _invoke_project_update(
        self,
        request: MaaFWProjectRequest,
        credentials: MaaFWUpdateCredentials,
        *,
        update_cancel: threading.Event | None = None,
        precheck_failure: dict[str, Any] | None = None,
        precheck_reminders: list[str] | None = None,
    ) -> Any:
        """谱系锁内：组同步 → 核心更新（下载 / staging 构建 / 预检 / 登记）→ 切本视图 →
        同步同组空闲脚本。返回 ``view_update.ViewUpdateOutcome``。

        会话层没有持本视图的内存预约（账号 inner task 才拿），切换时由
        ``run_view_update`` 自己拿，拿不到就本轮不切。

        ``update_cancel`` / ``precheck_failure`` / ``precheck_reminders`` 由 :meth:`update` 建：
        第一个是用户停止时置位的令牌，同时交给下载和预检回调里的 uv 安装；第二个是预检失败时
        回调写进来的 ``{targetVersion, requirement, kind, reason, …}``，调用方据此决定发
        warning 还是 error（D2）；第三个收预检备忘闸门「今天该提醒一次」的原因，调用方据此
        把这次跳过升成 warning。
        """

        from app.task.MaaFW.tools.core.project_update import (
            update_maafw_project_if_needed,
        )
        from app.task.MaaFW.tools.embedded.precheck_gate import build_precheck_gate
        from app.task.MaaFW.tools.embedded.update_mirrors import (
            github_release_mirror_urls,
        )
        from app.task.MaaFW.tools.embedded.update_session import UpdateSession
        from app.task.MaaFW.tools.embedded.view_update import memo_path_factory

        shape = _config_shape(request)
        send_log = self._threadsafe_log()
        source_config: dict[str, Any] = {
            "package_source": credentials.package_source,
            "package_mode": request.package_mode,
        }
        # 副本里没有 MFW.exe / maafw/ 可扫，外壳家族只能从导入报告取；不回填，
        # M9A 这种同版本同时发 -MXU.zip 与 -MFAA.zip 的项目会选错资产。
        shell_hint = shell_hint_from_report(shape)
        if shell_hint:
            source_config["project_shell_hint"] = shell_hint
        # 359MB 的包在直连 GitHub 下要几十分钟，一行日志都没有等于卡死；
        # 进度逐行追加进任务日志（#843 那块 WS 面板只有编辑页有）。
        progress = self._build_update_progress_reporter(send_log)
        # 与手动更新的 API 路径一致：用户配了代理，运行时更新也得走代理，
        # 否则受限网络下「手动能更、自动不能」。托管级优先，留空跟随全局；
        # 下载与预检都用触发脚本的这一份。
        proxy = _update_proxy(shape)
        route = await asyncio.to_thread(_runtime_pool_route)
        failure = precheck_failure if precheck_failure is not None else {}
        session = UpdateSession(
            request.script_id,
            channel=credentials.channel,
            # 在拿到谱系锁、登记之后（事件循环上）再抄一次同组候选：等锁 / 下载期间别的
            # 脚本可能开跑或跑完，用等锁之前的快照会切到正在跑的视图、或漏掉刚闲下来的。
            members=self._members,
            # 会话层没有持本视图的内存预约（账号 inner task 才拿），切换时现拿。
            reservation_held=False,
            send_log=send_log,
            script_name=request.script_name,
            # 等谱系锁时也能被停止打断；拿到锁后、联网之前再看一次，停过就不再检查。
            cancel_event=update_cancel,
            proxy=proxy,
            progress=progress,
        )

        async def core_call(view_path: Path, target: Any, after_register: Any) -> Any:
            """重新读取目标项目接口，按项目身份核对预备更新结果，然后调用核心项目更新入口。"""
            interface_model = await asyncio.to_thread(
                _load_interface_model, view_path, force_reload=True
            )
            prefetched = self._prefetched_project_update
            if prefetched is not None and self._prefetched_project_identity != (
                view_path.resolve(),
                target.lineage,
                lineage_info_from_interface(interface_model),
            ):
                # 同版重新导入可以保持 Report 不变却换了项目来源；在谱系锁内
                # 丢掉旧候选，按当前项目正常发现，不能把旧包登记到新谱系。
                prefetched = None
                self._prefetched_project_update = None
            memo_path_for = memo_path_factory(target.lineage)
            # 登记前在 staging 上真建运行环境：建不出来就丢掉新版本、继续跑当前版本。
            # isolated_venv 的 agent 建在池根下的预检目录，不写环境缓存（D6）。
            post_validate = session.precheck(
                pool_root=route.root,
                failure=failure,
                previous_version=getattr(interface_model, "version", None),
                project_name=getattr(interface_model, "name", None),
                memo_path_for=memo_path_for,
                cancel_event=update_cancel or threading.Event(),
            )
            # 上次预检失败的版本先轻探一下，拿不到就不再下包建池（D1：只有运行前 /
            # 运行后自动更新读备忘，手动更新不传即忽略）。
            gate = build_precheck_gate(
                memo_path_for,
                project_name=getattr(interface_model, "name", None),
                proxy=session.proxy.client,
                send_log=send_log,
                on_remind=(
                    precheck_reminders.append
                    if precheck_reminders is not None
                    else None
                ),
            )
            return await update_maafw_project_if_needed(
                view_path,
                interface_model,
                prefetch_full_package=bool(request.prefetch_paths),
                download_paths=request.prefetch_paths,
                prefetched=prefetched,
                mirror_cdk=credentials.cdk,
                channel=credentials.channel,
                proxy=session.proxy.client,
                # 下载源由用户显式选定，核心包不再自动分流。
                source_config=source_config,
                send_log=send_log,
                progress=session.core_progress(),
                post_validate=post_validate,
                precheck_gate=gate,
                projection=True,
                # 下载与预检共用同一个令牌：用户点停止，下载在一个 chunk 内停下。
                cancel_event=update_cancel,
                # GitHub 源先走加速镜像（全局 Update.GitHubMirror），全挂了回直连。
                github_mirror_urls=github_release_mirror_urls,
                payload=target,
                after_register=after_register,
            )

        return await session.run(core_call)

    async def update(
        self, request: MaaFWProjectRequest, phase: AutoUpdateMode
    ) -> MaaFWProjectNotice | None:
        """按时机更新项目目录；返回要弹的任务通知（没有为 None）。整个脚本只跑一次，在账号任务之外。

        **任何失败都只记日志 + 通知，不抛出**（取消除外）：更新失败不该让本来能跑的代理任务
        跑不了。耗时也天然不计入 ``Run.RunTimeLimit``——那个限时是
        ``plan_run.MaaFWPlanRun.run`` 用 ``asyncio.wait_for`` 套在单个账号的 MaaFW 运行上的，
        这里还没建（或已收尾）账号任务。
        """

        shape = _config_shape(request)
        phase_zh = "运行前" if phase == "BeforeRun" else "运行后"
        if follow_source_enabled(shape):
            # 开发者模式：以来源目录为准，运行前检查已按来源同步过；更新会把开发者的
            # 改动换成发行版，私有渠道也不该有更新登记进来。源码形态压根没有发行包可更新。
            mode = (
                "源码形态（始终跟随来源目录）"
                if is_source_form(shape)
                else "开发者模式（跟随来源目录）"
            )
            self._log(
                f"{mode}：跳过{phase_zh}自动更新，以来源目录为准；要更新请直接更新来源目录"
            )
            return None
        project_path = resolve_maafw_project_root(request.script_id, shape).resolve()

        credentials = resolve_update_credentials(shape)
        self._log(
            f"开始{phase_zh}检查 MFW 项目更新：下载源 {credentials.source}，"
            f"渠道 {credentials.channel}，Mirror 酱 CDK {describe_cdk(credentials)}，"
            f"代理 {describe_proxy(shape)}"
        )
        # 记下更新前钉定的 maafw 版本：提交后若换了版本，旧 runtime 不必再等宽限。
        from app.task.MaaFW.tools.embedded.live_projects import (
            reconcile_in_background,
        )
        from app.task.MaaFW.tools.embedded.pool_reconcile import (
            previous_maafw_version,
        )

        previous_version = await asyncio.to_thread(previous_maafw_version, project_path)

        # 用户点停止时 ``CancelledError`` 从 await 上抛出，但下游不会自己停：
        # 下载与预检期间的 uv 安装都靠同一个令牌终止，staging 随后丢弃。与
        # :meth:`confirm_environment` 同一套 shield + 有限宽限，只是宽限
        # 按阶段分——见 :meth:`_describe_update_cancel`。
        update_cancel = threading.Event()
        precheck_failure: dict[str, Any] = {}
        precheck_reminders: list[str] = []
        self._update_stage = None
        self._update_downloaded = None
        self._update_total = None
        self._point("script_update", key=phase)
        update_task = asyncio.create_task(
            self._invoke_project_update(
                request,
                credentials,
                update_cancel=update_cancel,
                precheck_failure=precheck_failure,
                precheck_reminders=precheck_reminders,
            )
        )

        async def abort_update() -> None:
            update_cancel.set()
            text, grace = self._describe_update_cancel()
            self._log(text)
            # 宽限内没等到也不再拖着关机；线程随子进程结束，其异常在这里
            # 主动取走，免得事件循环报「Task exception was never retrieved」。
            # 宽限之后还没停下的（比如还在等同项目另一次更新的谱系锁），令牌已置位，
            # ``run_view_update`` 拿到锁前后都会先看它，不会再去联网检查、取下载地址。
            update_task.add_done_callback(
                lambda task: None if task.cancelled() else task.exception()
            )
            process_scope = current_process_scope.get()
            if process_scope is None or not process_scope.closed:
                with suppress(BaseException):
                    await asyncio.wait_for(asyncio.shield(update_task), timeout=grace)

        try:
            finished = await self._await_or_stop(update_task)
        except asyncio.CancelledError:
            self._point("script_update", "cancelled", phase)
            await abort_update()
            raise
        if not finished:
            # 收尾里的运行后更新：外层取消被基类挡住，停止经 :meth:`stop` 传进来。
            self._point("script_update", "cancelled", phase)
            await abort_update()
            return None
        try:
            outcome = update_task.result()
            result = outcome.result
        except asyncio.CancelledError:
            self._point("script_update", "cancelled", phase)
            raise
        except Exception as exc:  # noqa: BLE001 - 更新失败不阻断运行
            reason = sanitize_log_message(str(exc)).strip() or type(exc).__name__
            if getattr(exc, "cancelled", False):
                # 令牌置位后核心包主动停下，而 ``CancelledError`` 没走到上面那个
                # 分支（取消发生在 shield 之外）：照样别把「已中止」说成失败。
                # 这里不复用 ``_describe_update_cancel``：那套文案是「正在停」，
                # 事已停下再说「正在中止」只会让人以为还在等。
                self._point("script_update", "cancelled", phase)
                logger.info(f"MFW 项目{phase_zh}更新已中止：{reason}")
                self._log("MFW 项目更新已中止")
                return None
            self._point("script_update", "failed", phase)
            if precheck_failure and getattr(exc, "post_validate_rejected", False):
                # 预检没过、新版本已丢弃：视图还是原样、照常能跑。这是「不升级」
                # 而不是事故，只发一次 warning（D2）；其它失败仍是 error。
                text = describe_precheck_failure(phase_zh, precheck_failure)
                logger.warning(f"{text}：{reason}")
                self._log(text)
                return MaaFWProjectNotice("warning", text)
            if getattr(exc, "check_unreachable", False):
                # 查版本时连不上更新源：与只看 GitHub 的项目同一口径，只记一行日志、
                # 不弹错误——否则断网期间每次运行都报一次。下载、应用阶段的失败与
                # CDK 之类要用户处理的错误不走这里。
                logger.warning(f"MFW 项目{phase_zh}更新检查失败，已跳过：{reason}")
                self._log(f"MFW 项目更新检查失败，已跳过本次更新：{reason}")
                return None
            logger.opt(exception=True).warning(
                f"MFW 项目{phase_zh}更新失败，任务继续：{reason}"
            )
            self._log(f"MFW 项目更新失败，任务继续：{reason}")
            return MaaFWProjectNotice(
                "error", f"MFW 项目{phase_zh}更新失败，任务继续：{reason}"
            )

        updated = bool(_result_field(result, "updated"))
        if updated:
            self._point("script_update", "succeeded", "updated")
        elif _result_field(result, "checked") and not _result_field(
            result, "update_available"
        ):
            self._point("script_update", "succeeded", "no_update")
        else:
            self._point("script_update", "skipped", phase)
        if outcome.registered_id:
            # 登记成功就意味着预检建出了环境，这个版本上次失败的备忘（若有）作废。
            try:
                from app.task.MaaFW.tools.core.project_update import (
                    clear_runtime_precheck,
                )
                from app.task.MaaFW.tools.embedded.view_update import (
                    memo_path_factory,
                )

                await asyncio.to_thread(
                    clear_runtime_precheck,
                    memo_path_factory(outcome.lineage)(
                        str(_result_field(result, "latest_version") or "")
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"清理运行环境预检备忘失败：{exc}")
        if updated:
            # 新版本的 runtime 预检时已建好；旧版本的那份在谱系里最后一个视图离开
            # 之后才可能无人引用（回收那边按全部视图判断）。
            reconcile_in_background(
                f"{phase.lower()}-update",
                updated_project_path=project_path,
                previous_version=previous_version,
            )
            # interface.json 已经变了：强制刷新缓存，否则本轮用户仍按旧版任务表跑。
            try:
                interface_model = await asyncio.to_thread(
                    _load_interface_model, project_path, force_reload=True
                )
                self._log(
                    "interface 缓存已刷新，当前版本："
                    f"{getattr(interface_model, 'version', None) or '未知'}"
                )
            except Exception as exc:  # noqa: BLE001
                logger.opt(exception=True).warning(
                    f"MFW 项目更新后刷新 interface 缓存失败：{exc}"
                )
                self._log(f"刷新 interface 缓存失败：{exc}")

        lines = describe_update_result(result)
        for _, text in lines:
            self._log(text)
        # 「已是最新 / 跳过」只留在日志里；真的更新了或 CDK 有问题才弹通知，
        # 免得每次运行都弹一条没信息量的提示。被预检备忘挡下的跳过例外：同一版本
        # 每天升成一次 warning（闸门按 remindedOn 决定），否则一直没更新也没人知道。
        has_warning = bool(precheck_reminders) or any(
            level == "warning" for level, _ in lines
        )
        if lines and (has_warning or updated):
            return MaaFWProjectNotice(
                "warning" if has_warning else "info",
                "；".join(text for _, text in lines),
            )
        return None

    # ------------------------------------------------------------------ 运行环境确认

    async def confirm_environment(
        self, request: MaaFWProjectRequest, phase: AutoUpdateMode
    ) -> MaaFWProjectNotice | None:
        """更新之后确认一次运行环境，别把建环境的成本留到账号任务里；返回要弹的通知。

        更新过就意味着 interface / requirements 变了，隔离 venv 得重建。不在
        这里做的话，重建会推迟到 runner 的 worker 子进程里——那时模拟器和游戏
        都已经起来了，用户看到的只是「任务卡住」。

        **任何失败都只记日志 + 通知，不抛出**（取消除外）：runner 本来就会按需准备，这里失败
        最多把成本推回运行时，不该让能跑的任务跑不了。
        """

        shape = _config_shape(request)
        phase_zh = "运行前" if phase == "BeforeRun" else "运行后"
        project_path = resolve_maafw_project_root(request.script_id, shape).resolve()

        # 更新已经放掉了项目锁。拿不到说明另有准备/运行在跑，那份准备一样管用。
        reservation_key = await try_reserve_project_path(project_path)
        if reservation_key is None:
            self._log("项目正被占用，跳过本次运行环境确认")
            return None

        # 准备可能要几分钟（首次要下 MaaFramework）。用户这时点停止，
        # ``task.cancel()`` 会在下面的 await 上抛出，但工作线程不会自己停——
        # 取消得靠令牌传进去，做法与 ``plan_run`` 的准备路径一致。
        cancel_event = threading.Event()
        # 装依赖走的代理与更新下载同一份：托管级优先，留空跟随全局。
        proxy_url = _update_proxy(shape).url
        health_warnings: list[str] = []
        from app.task.MaaFW.tools.embedded.env_confirm import (
            resolve_prepare_environment,
        )

        prepare_environment = resolve_prepare_environment()
        prepare_task = asyncio.create_task(
            asyncio.to_thread(
                prepare_environment,
                project_path,
                cancel_event,
                self._threadsafe_log(),
                proxy_url=proxy_url,
                # 运行时口径：自带 Python 检查没通过也照常跑（报错照跑）
                lenient_health_check=True,
                health_warnings_out=health_warnings,
            )
        )

        process_scope = current_process_scope.get()
        if process_scope is not None:
            process_scope.retain_worker(prepare_task)

        handed_off = False

        async def abort_prepare() -> None:
            # 置位后正在跑的 uv 子进程会被终止。只等有限时间：等到了就在放开
            # 项目锁之前收干净，等不到也不再拖着关机。
            nonlocal handed_off
            cancel_event.set()
            if process_scope is None or not process_scope.closed:
                with suppress(BaseException):
                    await asyncio.wait_for(
                        asyncio.shield(prepare_task),
                        timeout=_ENV_PREPARE_CANCEL_GRACE_SECONDS,
                    )
            if prepare_task.done():
                # 异常在这里取走，免得事件循环报「Task exception was never retrieved」。
                if not prepare_task.cancelled():
                    prepare_task.exception()
                return
            # 线程还没收完（agent venv 的准备有不认令牌的一段）：预约交给它的完成回调
            # 去放，不在 finally 里放——否则马上重开、编辑页准备环境或手动更新都能拿到
            # 预约，和这条线程同时写同一个项目。
            handed_off = True
            prepare_task.add_done_callback(
                functools.partial(_release_after_work, reservation_key)
            )

        try:
            if not await self._await_or_stop(prepare_task):
                # 收尾里的确认：外层取消被基类挡住，停止经 :meth:`stop` 传进来。
                await abort_prepare()
                self._log("已中止运行环境确认，下次运行前再确认")
                return None
            prepared = prepare_task.result()
        except asyncio.CancelledError:
            await abort_prepare()
            raise
        except Exception as exc:  # noqa: BLE001 - 准备失败不阻断运行
            reason = sanitize_log_message(str(exc)).strip() or type(exc).__name__
            logger.opt(exception=True).warning(
                f"MFW {phase_zh}运行环境确认失败，任务继续：{reason}"
            )
            self._log(f"运行环境确认失败，任务继续：{reason}")
            return MaaFWProjectNotice(
                "error", f"MFW {phase_zh}运行环境确认失败，任务继续：{reason}"
            )
        finally:
            if not handed_off:
                await release_project_path(reservation_key)

        # 没变化时只留一行日志，别为「什么都没做」弹通知。刚提交过更新时这里
        # 必然是「重新准备」：预检不写环境缓存（D6），提交后指纹必 miss，再走
        # 一遍 prepare 只是池命中 + 解释器 ABI 探针，几秒。
        if prepared and health_warnings:
            # 与准备里那行「检查没通过、按报错照跑放行」一致，不说「准备完成」
            message = f"{phase_zh}运行环境已重新准备（检查没通过，照常启动）"
        elif prepared:
            message = f"{phase_zh}运行环境已重新准备完成"
        else:
            message = "项目文件没有变化，运行环境沿用上次的准备结果"
        self._log(message)
        return None

    # ------------------------------------------------------------------ 收尾项目

    async def close(
        self, request: MaaFWProjectRequest, *, sync_group: bool
    ) -> MaaFWProjectCloseOutcome:
        """收尾：组同步（跑完回落，§3.1 第 9 步）、写穿巡检、原生日志备份清理。任何一步失败只记日志。

        ``sync_group`` 由调用方算：只在账号全部正常跑完、用户没要求停止时做——被停止 / 崩溃时
        收尾是受保护的，切了版本就得接着确认运行环境（可能几分钟），「停止」会被拖住；不切的话
        切换留给下一次运行前检查，那里持预约切、由 ``envConfirmedFor`` 驱动调用方在账号任务前
        确认。切了版本时 ``env_confirm_needed`` 为真：调用方放到代理结果推送之后再
        :meth:`confirm_environment`，没做成的，标记里 envConfirmedFor 仍欠着，下次运行前检查会补。
        """

        view = embedded_project_dir(request.script_id)
        switched = False
        if sync_group:
            switched = await self._sync_view_to_group(
                request, "运行后", reservation_held=False
            )
        try:
            from app.task.MaaFW.tools.embedded.view_audit import audit_view

            report = await asyncio.to_thread(audit_view, view)
            for line in report.messages:
                self._log(line)
        except Exception as exc:  # noqa: BLE001
            logger.opt(exception=True).warning(f"MFW 写穿巡检失败：{exc}")
        try:
            from app.task.MaaFW.tools.embedded.view_audit import (
                clean_native_log_backups,
            )

            removed = await asyncio.to_thread(
                clean_native_log_backups, view, request.round_started_at
            )
            if removed:
                logger.info(
                    f"已清理 {removed} 个 MaaFW 原生日志轮转备份（history 已有副本）"
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"清理 MaaFW 原生日志备份失败：{exc}")
        return MaaFWProjectCloseOutcome(env_confirm_needed=switched)

    # ------------------------------------------------------------------ 预下载

    async def prefetch(self, request: MaaFWProjectRequest) -> None:
        """队列预下载：发现完整包更新就下进核心的共享缓存，候选留在会话里给 :meth:`update` 用。"""

        from app.task.MaaFW.tools.core.project_update.progress import (
            UpdateProgressEvent,
        )
        from app.task.MaaFW.tools.core.project_update.transport import (
            download_resumable,
        )
        from app.task.MaaFW.tools.core.project_update.updater import (
            discover_maafw_project_update,
        )
        from app.task.MaaFW.tools.embedded.precheck_gate import build_precheck_gate
        from app.task.MaaFW.tools.embedded.update_mirrors import (
            github_release_mirror_urls,
        )
        from app.task.MaaFW.tools.embedded.view_update import memo_path_factory

        shape = _config_shape(request)
        # 增量依赖启动时的当前载荷，交给运行前更新，避免提前下载全量。
        if request.package_mode == "incremental":
            return
        if resolve_auto_update_mode(shape) == "Off" or follow_source_enabled(shape):
            return
        credentials = resolve_update_credentials(shape)
        project = resolve_maafw_project_root(request.script_id, shape).resolve()
        source = _source_config(credentials, shape)
        proxy = _update_proxy(shape).client
        interface = await asyncio.to_thread(_load_interface_model, project)
        marker = await asyncio.to_thread(read_view_marker, project)
        if marker is None or not marker.get("lineage"):
            # No trustworthy lineage: leave update discovery to the normal
            # startup path, which can recover and revalidate project metadata.
            return
        identity = (
            project,
            str(marker["lineage"]),
            lineage_info_from_interface(interface),
        )
        gate = build_precheck_gate(
            memo_path_factory(str(marker["lineage"])),
            project_name=getattr(interface, "name", None),
            proxy=proxy,
        )
        discovery = await discover_maafw_project_update(
            interface,
            source_config=source,
            proxy=proxy,
            prefer_full_package=True,
            precheck_gate=gate,
        )
        if (
            discovery is None
            or discovery.candidate is None
            or not discovery.candidate.download_url
        ):
            return
        candidate = discovery.candidate

        def report(event: dict[str, Any]) -> None:
            # 只转接下载器的公开进度，不改独立核心的传输和缓存逻辑。
            parsed = UpdateProgressEvent.of(event)
            if parsed.stage == "downloading":
                self._emit(
                    MaaFWProjectDownload(
                        parsed.downloaded_bytes or 0, parsed.total_bytes or 0
                    )
                )

        await download_resumable(
            source=candidate.source,
            version=candidate.to_version or candidate.version,
            download_url=candidate.download_url,
            expected_sha256=candidate.sha256,
            artifact_id=candidate.artifact_id,
            proxy=proxy,
            expected_size=candidate.size,
            progress=report,
            alternates=github_release_mirror_urls(candidate.download_url),
        )
        # 完整包留在核心的共享缓存，启动前按来源身份与版本基线复核后消费。
        self._prefetched_project_identity = identity
        self._prefetched_project_update = (str(interface.version or ""), discovery)

    def discard_prefetch(self) -> None:
        """撤销本次预下载候选的资格（重启客户端前），完整包仍由核心共享缓存维护。"""

        self._prefetched_project_update = None
        self._prefetched_project_identity = None


__all__ = [
    "BENIGN_SKIPS",
    "SKIP_OCCUPIED",
    "SKIP_SWITCHING",
    "SKIP_UPDATING",
    "MaaFWProjectCloseOutcome",
    "MaaFWProjectDownload",
    "MaaFWProjectEvent",
    "MaaFWProjectLease",
    "MaaFWProjectLog",
    "MaaFWProjectNotice",
    "MaaFWProjectOpenOutcome",
    "MaaFWProjectPoint",
    "MaaFWProjectRecordUpdate",
    "MaaFWProjectRequest",
    "MaaFWProjectSession",
    "MaaFWProjectSibling",
    "MaaFWProjectSink",
    "describe_open_failure",
    "describe_precheck_failure",
    "describe_update_result",
    "discover_prefetch",
]
