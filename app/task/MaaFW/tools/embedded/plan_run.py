"""把一份运行计划在一台设备上跑完：借运行环境、起 worker、收事件、落日志，默认带全部保护。

将来是运行这一块对外的「跑一份计划」（通用 MFW、M9A、MSS 三个专项各自的流程都调它）。
保护全在这里，专项不用自己做：worker 自停的整轮截止与单任务时限、原地打转检测（参数随 job
下发、由 worker 执行）、宿主硬杀兜底（截止之后再给 ``_RUN_DEADLINE_GRACE_SECONDS`` 宽限）、
强杀前的进程树清理、运行环境的借还、三份日志（``.worker.log``、``.maafw.log``、``.project.log``）
的增量复制与打码、原生报错行摘取、失败截图等附件的收集、ModAVD 的 MaaFramework 版本门槛。

**只收普通数据**（``MaaFWPlanRunRequest``）：不接收脚本配置、账号配置或任务类实例，也不回头碰
调用方的对象。打码的值分两组由调用方算好传进来（``run_secrets`` 进 worker 日志与原生日志，
``project_log_secrets`` 进项目日志）。过程中的输出只经一个事件出口交给调用方：一行账号日志
（``MaaFWPlanRunLog``）、一个运行进度点（``MaaFWPlanRunPoint``，名字与取值同 ``app.task.run_flow``，
由调用方以自己为 owner 上报）、一条 worker 推来的结构化运行记录事件（``MaaFWPlanRunRecord``）、
宿主这一侧的阶段变化（``MaaFWPlanRunStage``）。结果、附件清单与原生报错行经返回值
（``MaaFWPlanRunOutcome``）拿；运行抛异常时同样的东西留在运行对象上（``attachments`` /
``native_errors`` / ``agent_plans``），调用方在 ``finally`` 里取。事件出口在事件循环线程里同步调用，
出口自己不要抛异常。

这一步还不是服务：``run`` 是一次长的 await，``stop`` 结束正在跑的 worker。出口窄到以后能原样换成
「开始 / 取事件和结果 / 停止」的拉取模式。
"""

from __future__ import annotations

import asyncio
import json
import queue
import shutil
import threading
import time
import uuid
from collections.abc import AsyncIterator, Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import psutil

from app.task.MaaFW.tools.core.interface.agent_command import MaaFWAgentCommandPlan
from app.task.MaaFW.tools.core.runner.environment import (
    MaaFWRunnerEnvironment,
    worker_run_plan,
)
from app.task.MaaFW.tools.core.runner.models import (
    MaaFWDeviceConfig,
    MaaFWRunPlan,
    MaaFWRunResult,
)
from app.task.MaaFW.tools.core.runner.run_events import (
    RUN_RECORD_EVENT_TYPE,
    STAGE_ENVIRONMENT,
)
from app.task.MaaFW.tools.core.runner.service import MaaFWRunnerService
from app.task.MaaFW.tools.core.runner.worker_launch import (
    IMPORT_ROOT,
    WORKER_MODULE,
)
from app.task.MaaFW.tools.core.runtime_pool.host_environment import (
    subprocess_proxy_scope,
)
from app.task.MaaFW.tools.core.runtime_pool.installer import (
    install_process_factory_scope,
)
from app.task.MaaFW.tools.core.worker_protocol import (
    AUDIENCE_UI,
    UI_LOG_MAX_CHARS,
    WorkerEventServer,
    encode_job,
    event_audience,
    event_channel_supported,
    forwards_to_ui,
    strip_ansi,
)
from app.utils import get_logger
from app.utils import io as _utils_io
from app.utils.common.process.runner import create_subprocess
from app.utils.common.process.scope import current_process_scope

from .device_config import task_start_gate
from .project_logs import copy_project_log_delta, snapshot_project_logs
from .resource_failure import (
    MAX_NATIVE_ERROR_LINES,
    native_error_excerpt,
    read_native_error_lines,
)
from .run_redaction import redact_secret_text, secret_byte_pairs

if TYPE_CHECKING:
    from app.task.run_flow import PointState, RunStage

# 与任务类同一个名字：后端日志里这段流程的行照旧记在「MaaFW 插件自动代理」下
logger = get_logger("MaaFW 插件自动代理")

# 任务取消后等环境准备线程收尾的最长时间。Runtime 关机只给后端约 5 秒，
# 安装线程若还在等 uv 子进程退出，超过这个值就不再等它。
_PREPARE_ENVIRONMENT_CANCEL_GRACE_SECONDS = 2.0
# 放弃等待后仍让收尾任务在后台跑完（准备恰好成功时要释放租约），
# 这里持有强引用，免得任务对象被回收。
_ABANDONED_PREPARATION_CLEANUPS: set[asyncio.Task[None]] = set()

_SUBPROCESS_OUTPUT_ENCODINGS = ("utf-8", "gbk", "shift_jis", "utf-16")
# 与日志去向判定（worker_protocol.forwards_to_ui）用同一个上限
_FRAMEWORK_UI_LOG_MAX_CHARS = UI_LOG_MAX_CHARS
# worker 输出转发每处理这么多行（事件通道上是这么多条）就让出一次事件循环。取 50 是因为
# 原生诊断的洪峰约每秒几十行，这个粒度下让出频率约每秒一次，开销可忽略。
_RELAY_YIELD_EVERY_LINES = 50
# worker stdout / stderr 单行上限（字节）。更长的一行丢掉、记一句，读取继续。协议事件走独立的
# 事件通道、按帧传，不受它限制；stdout 上只剩原生诊断，以及事件通道建不起来时退回的旧格式事件。
WORKER_STREAM_LINE_LIMIT = 16 * 1024 * 1024
# worker 到点自己停任务、截图、回传结果需要一点时间；宿主的硬超时在此之后才到，
# 只兜 worker 没能停下来的情况（原生层卡死、agent 自定义动作不返回）。
_RUN_DEADLINE_GRACE_SECONDS = 90.0
# worker 把结果发回来之后还要收尾（断开 agent、结束 agent 进程）才退出。agent 卡死时
# 这一步可能拖很久，而结果已经在手里了：给有限时间，到点强杀，别让宽限期把已经
# 拿到的截图和进度一起作废。
_WORKER_EXIT_AFTER_RESULT_SECONDS = 30.0
# 旧版本的 worker 读完 job 就删，正常情况下 job 文件只在盘上待几秒；超过这么久还在的，
# 是宿主与 worker 一起被硬杀（断电、蓝屏、结束进程树）留下的。
_STALE_RUNNER_JOB_SECONDS = 3600.0

_STREAM_OVERRUN_NOTE = f"（worker 输出有一行超过 {WORKER_STREAM_LINE_LIMIT // (1024 * 1024)} MB，已丢弃该行）"


class MaaFWRunTimeoutError(RuntimeError):
    """worker 在宽限期内也没停下，宿主强杀了它。"""


class MaaFWTaskDeadlineExpired(RuntimeError):
    """``task_deadlines`` 里某个任务的截止时刻在下发 job 之前就过了；``task_name`` 是哪一个。"""

    def __init__(self, task_name: str) -> None:
        super().__init__(f"任务 {task_name} 的截止时刻已过")
        self.task_name = task_name


# ---------------------------------------------------------------------------
# 入参、事件与返回值（都是普通数据）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MaaFWPlanRunRequest:
    """跑一份计划要的全部输入。

    - ``run_time_limit_minutes``：整轮时限（分钟），截止时刻随 job 交给 worker，宿主在其后加宽限
      硬杀；运行环境租约的 TTL 也按它算（0 / 空按 120 分钟）。
    - ``task_time_limit_seconds`` / ``task_time_limit_overrides``：单任务时限（秒）与按任务名的覆盖。
    - ``task_deadlines``：按任务名给的单调时钟截止时刻。下发 job 时换算成剩余秒数，与该任务的
      时限取小（时限为 0 时就用剩余秒数）；已经过了就抛 ``MaaFWTaskDeadlineExpired``。
    - ``run_secrets``：本次运行要打码的写法（进 ``.worker.log``、``.maafw.log``、转发的 worker
      事件与原生诊断）；``project_log_secrets``：项目日志（``.project.log``）要打码的写法；
      ``redaction_notice``：写在 ``.worker.log`` 第一行的打码说明（没有就 None）。
    - ``game_started_at`` / ``game_start_disk_quiet`` / ``game_wait_seconds``：首任务闸门的输入
      （``device_config.task_start_gate``），在借到运行环境之后才算，借环境的耗时算在等待里。
    - ``agent_plans``：沿用的 agent 命令计划（同一账号这一轮的重试）；None 时用这次借环境算出的。
    - ``extra_env``：盖在运行环境变量上的进程环境（ModAVD 的 adb server 端口）。
    - ``desktop``：在桌面分身里跑时的目标（``desktop_process_target`` 的值），None 是普通子进程。
    - ``avd_emulator``：设备是 ModAVD 时给设备入口（``supports_maafw_adb_extra_version``），借到
      运行环境后按 MaaFramework 版本过门槛；其余设备 None。
    """

    project_path: Path
    plan: MaaFWRunPlan
    device_config: MaaFWDeviceConfig
    runtime_pool_root: Path | None
    runtime_pool_id: str
    lease_owner: str
    run_time_limit_minutes: int
    attachment_root: Path
    task_time_limit_seconds: int = 0
    task_time_limit_overrides: Mapping[str, int] = field(default_factory=dict)
    task_deadlines: Mapping[str, float] = field(default_factory=dict)
    loop_guard: bool = False
    run_secrets: Sequence[str] = ()
    project_log_secrets: Sequence[str] = ()
    redaction_notice: str | None = None
    game_started_at: float | None = None
    game_start_disk_quiet: bool = False
    game_wait_seconds: Any = 0
    #: worker 的导入根；默认是运行器按自己位置算出的 ``IMPORT_ROOT``（MAS 源码根）
    import_paths: Sequence[str | Path] = field(default_factory=lambda: [IMPORT_ROOT])
    proxy_url: str | None = None
    agent_plans: tuple[MaaFWAgentCommandPlan, ...] | None = None
    extra_env: Mapping[str, str] = field(default_factory=dict)
    desktop: Any | None = None
    avd_emulator: Any | None = None


@dataclass(frozen=True, slots=True)
class MaaFWPlanRunLog:
    """一行给用户看的账号日志；``warning`` 为真的是失败类的行（后端日志按 WARNING 记）。"""

    message: str
    warning: bool = False


@dataclass(frozen=True, slots=True)
class MaaFWPlanRunPoint:
    """一个运行进度点：``stage`` / ``state`` / ``key`` 与 ``app.task.run_flow.point`` 同义。"""

    stage: RunStage
    state: PointState = "entered"
    key: str = ""


@dataclass(frozen=True, slots=True)
class MaaFWPlanRunRecord:
    """worker 推来的一条结构化运行记录事件，``data`` 原样（形状见 ``run_events``）。"""

    data: Any


@dataclass(frozen=True, slots=True)
class MaaFWPlanRunStage:
    """宿主这一侧的阶段变化：``ok`` 为 None 是开始，真 / 假是结束时成没成。"""

    stage: str
    ok: bool | None = None


MaaFWPlanRunEvent = (
    MaaFWPlanRunLog | MaaFWPlanRunPoint | MaaFWPlanRunRecord | MaaFWPlanRunStage
)
MaaFWPlanRunSink = Callable[[MaaFWPlanRunEvent], None]


@dataclass(frozen=True, slots=True)
class MaaFWPlanRunAttachment:
    """一个要进历史的附件：日志（``kind="log"``）或失败截图（``kind="image"``）。"""

    path: Path
    kind: str
    role: str
    display_name: str


@dataclass(frozen=True)
class MaaFWPlanRunOutcome:
    """worker 回传了结果时的返回值。

    ``native_errors`` 是本次的原生 ERR 行（原生日志副本里的优先，没有就用 worker stdout / stderr
    上的），资源包加载失败时据此说出原因；``agent_plans`` 是这次下发用的 agent 命令计划。
    """

    result: MaaFWRunResult
    attachments: tuple[MaaFWPlanRunAttachment, ...]
    native_errors: tuple[str, ...]
    agent_plans: tuple[MaaFWAgentCommandPlan, ...] | None


# ---------------------------------------------------------------------------
# 跑一份计划
# ---------------------------------------------------------------------------


class MaaFWPlanRun:
    """一次「跑一份计划」。``run`` 只能调一次；``stop`` 随时可调（没有在跑的 worker 就什么都不做）。"""

    def __init__(self, request: MaaFWPlanRunRequest, emit: MaaFWPlanRunSink) -> None:
        self._request = request
        self._emit = emit
        self._process: Any | None = None
        #: 已收集的附件；运行抛异常时也照样有（收尾时收）。
        self.attachments: list[MaaFWPlanRunAttachment] = []
        #: 本次的原生 ERR 行，见 ``MaaFWPlanRunOutcome.native_errors``。
        self.native_errors: list[str] = []
        #: 这次下发用的 agent 命令计划；借环境之后、过了 ModAVD 门槛才有。
        self.agent_plans: tuple[MaaFWAgentCommandPlan, ...] | None = None

    def _log(self, message: str) -> None:
        self._emit(MaaFWPlanRunLog(message))

    def _point(self, stage: RunStage, state: PointState = "entered") -> None:
        self._emit(MaaFWPlanRunPoint(stage, state))

    @contextmanager
    def _operation(self, stage: RunStage) -> Iterator[None]:
        """同 ``run_flow.operation``：只包以异常表示失败的动作。"""

        self._point(stage)
        try:
            yield
        except asyncio.CancelledError:
            self._point(stage, "cancelled")
            raise
        except Exception:
            self._point(stage, "failed")
            raise
        else:
            self._point(stage, "succeeded")

    async def run(self) -> MaaFWPlanRunOutcome:
        """跑完这份计划；worker 回传了结果就返回，否则抛异常（整轮超时是 ``MaaFWRunTimeoutError``）。"""

        limit_minutes = self._request.run_time_limit_minutes
        timeout = limit_minutes * 60
        # 截止时刻交给 worker：到点它自己停任务、截图、把已完成的任务带回来。
        # 宿主这层只在 worker 没停下时才强杀，那时既没有截图也没有进度。
        run_deadline_at = time.time() + timeout
        try:
            result = await asyncio.wait_for(
                self._run_worker(run_deadline_at=run_deadline_at),
                timeout=timeout + _RUN_DEADLINE_GRACE_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            await self.stop()
            raise MaaFWRunTimeoutError(
                f"MaaFW 任务运行超时（限制 {limit_minutes} 分钟，worker 未能自行停止，已强制结束）"
            ) from exc
        except asyncio.CancelledError:
            await self.stop()
            raise
        return MaaFWPlanRunOutcome(
            result=result,
            attachments=tuple(self.attachments),
            native_errors=tuple(self.native_errors),
            agent_plans=self.agent_plans,
        )

    def _check_avd_runtime_version(self, maafw_version: str | None) -> None:
        """ModAVD 要 AVDExtras：运行环境的 MaaFramework 低于 5.7.0 时明确报错，不让它静默回落。"""

        emulator = self._request.avd_emulator
        if emulator is None:
            return
        supported = emulator.supports_maafw_adb_extra_version(maafw_version)
        if supported is False:
            raise RuntimeError(
                f"项目使用的 MaaFramework {maafw_version} 低于 5.7.0，不支持 ModAVD 的截图通道"
                "（AVDExtras）；请把项目更新到带 MaaFramework 5.7.0 以上的版本"
            )
        if supported is None:
            self._log(
                "认不出项目使用的 MaaFramework 版本，无法预先确认是否支持 ModAVD 截图通道"
                "（AVDExtras，5.7.0 起）；不支持时连接会直接失败"
            )

    async def _run_worker(self, *, run_deadline_at: float) -> MaaFWRunResult:
        request = self._request
        plan = request.plan
        emit_log = self._log
        project_path = request.project_path

        service = MaaFWRunnerService()
        loop = asyncio.get_running_loop()
        runtime_pool_root = request.runtime_pool_root
        runtime_pool_id = str(request.runtime_pool_id or "").strip()
        if runtime_pool_root is None or not runtime_pool_id:
            raise RuntimeError(
                "MaaFW 运行任务缺少由 maafw.runtime_pool.v1 注入的 root/poolId"
            )
        native_debug_log_path = project_path / "debug" / "maafw.log"
        (
            native_debug_log_offset,
            native_debug_log_rotations,
        ) = await asyncio.to_thread(
            _snapshot_native_debug_log_state, native_debug_log_path
        )
        # 项目 agent 自己写的日志（debug/custom、go-service …）同样记下起点，收尾时只另存本次新写的。
        try:
            project_log_marks = await asyncio.to_thread(
                snapshot_project_logs, project_path
            )
        except Exception as exc:
            project_log_marks = {}
            emit_log(f"MaaFW 项目日志起点记录失败，本次按全部新写处理: {exc}")

        def send_runner_log(message: str) -> None:
            loop.call_soon_threadsafe(self._emit, MaaFWPlanRunLog(message))

        # 密码字段（PI v2.10.0）的原文会随 override 进原生日志与 worker 输出：复制、转发、
        # 摘录失败原因前都换成占位（协议要求不得把原文写进日志）。
        secrets = list(request.run_secrets)
        stdout_native_errors: list[str] = []
        self.native_errors = []
        prepare_cancel_event = threading.Event()
        # 与运行前更新 / 预检同一份解析（调用方算好）：托管级代理优先，留空跟随全局。
        # 运行时装依赖也走它，否则「更新能走代理、真跑时装不上」。
        proxy_url = request.proxy_url
        process_scope = current_process_scope.get()

        def _prepare_environment_with_proxy() -> MaaFWRunnerEnvironment:
            # 代理作用域按线程登记，要在 to_thread 的目标函数体内进入：池的 uv /
            # pip 子进程、以及这里派生出的 worker 环境（worker 内的 agent pip 与
            # 项目 agent 再从它继承）都从 strip_host_python_environment 拿到代理变量。
            with (
                subprocess_proxy_scope(proxy_url),
                install_process_factory_scope(
                    process_scope.popen if process_scope is not None else None
                ),
            ):
                return service.prepare_environment(
                    project_path,
                    runtime_pool_root=runtime_pool_root,
                    runtime_pool_id=runtime_pool_id,
                    lease_owner=request.lease_owner,
                    lease_ttl_seconds=max(
                        600, int(request.run_time_limit_minutes or 120) * 60 + 600
                    ),
                    import_paths=list(request.import_paths),
                    send_log=send_runner_log,
                    cancel_event=prepare_cancel_event,
                    # agent 命令计划由 agent 环境在借环境时按声明算（见 agent_plans）
                    agents=plan.declaredAgents,
                )

        prepare_environment_task = asyncio.create_task(
            process_scope.run_update_worker(
                _prepare_environment_with_proxy,
                cancel=prepare_cancel_event.set,
                release_cancelled=service.release_environment,
            )
            if process_scope is not None
            else asyncio.to_thread(_prepare_environment_with_proxy)
        )
        try:
            self._emit(MaaFWPlanRunStage(STAGE_ENVIRONMENT))
            environment_ok = False
            try:
                runner_environment = await asyncio.shield(prepare_environment_task)
                environment_ok = True
            finally:
                self._emit(MaaFWPlanRunStage(STAGE_ENVIRONMENT, ok=environment_ok))
        except asyncio.CancelledError:
            # 取消要传进安装线程：置位令牌后正在跑的 uv/pip 子进程会被终止。
            # 然后只等有限时间——后端关机时 Runtime 只给几秒，等不到就放弃，
            # 租约释放交给后台任务或 TTL。
            prepare_cancel_event.set()
            await _abandon_environment_preparation(
                prepare_environment_task,
                release=service.release_environment,
                grace_seconds=_PREPARE_ENVIRONMENT_CANCEL_GRACE_SECONDS,
                send_log=emit_log,
            )
            raise
        history_dir = Path(request.attachment_root) / uuid.uuid4().hex
        await asyncio.to_thread(history_dir.mkdir, parents=True, exist_ok=True)
        history_stamp = "run"
        worker_id: str | None = None
        event_server: WorkerEventServer | None = None
        # 事件通道建不起来时的原因：worker.log 建好后写进去（这次运行退回 stdout 传事件）
        event_server_failure: str | None = None
        try:
            self._check_avd_runtime_version(runner_environment.maafw_version)
            # 同一账号这一轮只认第一次借环境时算出的 agent 命令计划，重试沿用（调用方传回
            # ``agent_plans``）。隔离 venv 的最终目录照旧由 worker 准备 agent 环境时按确切版本再定一次。
            agent_plans = (
                request.agent_plans
                if request.agent_plans is not None
                else runner_environment.agent_plans
            )
            self.agent_plans = agent_plans
            runner_plan = worker_run_plan(
                plan, runner_environment, agent_plans=agent_plans
            )
            start_gate = task_start_gate(
                started_at=request.game_started_at,
                disk_quiet=request.game_start_disk_quiet,
                wait_seconds=request.game_wait_seconds,
                log=emit_log,
            )
            payload = service.create_job_payload(
                runner_plan,
                request.device_config,
                # 失败截图和本次尝试的 .log / .maafw.log 放一起。
                failure_screenshot_dir=history_dir,
                failure_screenshot_prefix=history_stamp,
                task_start_not_before=start_gate.not_before,
                task_start_gate_mode=start_gate.mode,
                run_deadline_at=run_deadline_at,
                task_time_limit_seconds=request.task_time_limit_seconds,
                task_time_limit_overrides=dict(request.task_time_limit_overrides),
                loop_guard=request.loop_guard,
            )
            # job 经 worker 的 stdin 交过去、不再落盘；升级前的版本写过 job 文件，宿主与 worker
            # 一起被硬杀时会留在盘上（里面可能有解密后的密码选项），照旧清掉。
            await asyncio.to_thread(sweep_legacy_runner_jobs)
            # 事件（日志、结果）走独立通道（Windows 命名管道）；建不起来就让 worker 照旧写
            # stdout，这次运行不受影响。没有这条通道的平台直接用 stdout，不记。
            if event_channel_supported():
                try:
                    event_server = WorkerEventServer.open()
                except OSError as exc:
                    event_server_failure = (
                        f"MaaFW 事件通道建立失败（{exc!r}），本次运行事件改走标准输出"
                    )
                    logger.warning(event_server_failure)
            if request.task_deadlines:
                # 按截止时刻收紧的任务（如特调把登录交给首任务完成）：剩余时间在下发前一刻算，
                # 借环境、准备 job 的耗时都扣掉。
                overrides = dict(payload.taskTimeLimitOverrides or {})
                for task_name, deadline in request.task_deadlines.items():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise MaaFWTaskDeadlineExpired(task_name)
                    configured = overrides.get(
                        task_name, payload.taskTimeLimitSeconds or 0
                    )
                    limit = max(1, int(remaining))
                    overrides[task_name] = (
                        min(configured, limit) if configured else limit
                    )
                payload.taskTimeLimitOverrides = overrides
            job_bytes = encode_job(
                payload,
                event_channel=event_server.spec if event_server is not None else None,
            )
            # ModAVD 实例：worker 及其 agent、adb 子进程的 adb 走脚本专用 server。
            # 另拷一份，不改运行环境对象里那份（可能被缓存复用）。agent pip 约束文件的
            # 目录已由借运行环境时带进 runner_environment.env（见 agent_env.runtime_lease）。
            worker_env = {
                **runner_environment.env,
                **request.extra_env,
            }
            if (desktop := request.desktop) is not None:
                from app.utils.windows.desktop_session.process_runner import (
                    launch_desktop_process,
                )

                scope = current_process_scope.get()
                if scope is not None:
                    scope.ensure_can_start()
                with self._operation("start_script"):
                    process = await launch_desktop_process(
                        desktop,
                        argv=[
                            str(runner_environment.python_executable),
                            "-m",
                            WORKER_MODULE,
                        ],
                        cwd=Path.cwd(),
                        env=worker_env,
                        stdin=job_bytes,
                        stream_limit=WORKER_STREAM_LINE_LIMIT,
                    )
                if scope is not None:
                    scope.retain_desktop_process(process.stop)
            else:
                with self._operation("start_script"):
                    process = await create_subprocess(
                        str(runner_environment.python_executable),
                        "-m",
                        WORKER_MODULE,
                        cwd=str(Path.cwd()),
                        env=worker_env,
                        stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        # 默认 64 KiB：agent 原样转发的输出、原生 ERROR 日志里整份 pipeline JSON
                        # 都可能更长，超了 readline 就抛错、读取任务退出，worker 写满管道后挂到硬超时
                        limit=WORKER_STREAM_LINE_LIMIT,
                    )
            worker_id = service.register_worker(process)
        except BaseException:
            if event_server is not None:
                event_server.close()
            with suppress(Exception):
                await asyncio.to_thread(service.release_environment, runner_environment)
            service.unregister_worker(worker_id)
            raise
        self._process = process
        self._point("run")
        result_payload: dict[str, Any] | None = None
        result_received = asyncio.Event()
        stderr_lines: list[str] = []
        # 两份文件：``.worker.log`` 是 MAS 自己这一侧（runner 事件、worker 的
        # stdout/stderr），``.maafw.log`` 是项目 ``debug/maafw.log`` 本次运行部分的
        # 原样副本——不加前缀、不改编码，和脚本作者自己用 MFAA 跑出来的一模一样，
        # 出问题可以直接转交。以前两者混在一个文件里、原生每行还带一个抄写时刻，
        # 脚本作者拿到手第一反应是"这日志不对"。
        worker_log_path = history_dir / f"{history_stamp}.worker.log"
        native_log_path = history_dir / f"{history_stamp}.maafw.log"
        framework_log_writer: _FrameworkLogWriter | None = None

        try:
            writer = _FrameworkLogWriter(worker_log_path)
            await asyncio.to_thread(writer.start)
            framework_log_writer = writer
            # 临时目录收尾就删，文件以附件归档进历史记录：路径只进后端日志，不进账号日志
            logger.info(f"MaaFW worker 日志写入中: {worker_log_path}")
        except Exception as exc:
            if framework_log_writer is not None:
                with suppress(Exception):
                    await asyncio.to_thread(framework_log_writer.close)
                framework_log_writer = None
            emit_log(f"MaaFW worker 日志创建失败: {exc}")
        except BaseException:
            # 在这里被停止：事件通道还没交给读取任务、下面的收尾也走不到，先关掉它（worker
            # 由 run 结束）。不关的话管道句柄留在宿主里一直不释放。
            if event_server is not None:
                event_server.close()
            raise

        def write_framework_log(source: str, message: str) -> None:
            if framework_log_writer is None:
                return
            framework_log_writer.write(source, message)

        def note_native_error(line: str) -> None:
            """worker 转来的一行是原生 ERR 行就留下（``[json=`` 起丢掉、有条数上限）；续行不要。"""

            excerpt = native_error_excerpt(line)
            if excerpt is None:
                return
            stdout_native_errors.append(excerpt)
            del stdout_native_errors[:-MAX_NATIVE_ERROR_LINES]

        # 项目有 password 输入框时第一行写打码说明：问题包导出凭它判断这份日志能不能往外发
        if request.redaction_notice:
            write_framework_log("runner", request.redaction_notice)
        if event_server_failure:
            write_framework_log("runner", event_server_failure)

        def handle_event(event: dict[str, Any]) -> None:
            """worker 发来的一个协议事件（事件通道或 stdout 退回格式，已打码），按类型分发。"""

            nonlocal result_payload
            event_type = event.get("type")
            if event_type == "log":
                message = str(event.get("message") or "")
                write_framework_log("runner", message)
                # 去向由 worker 定好（audience）；旧格式事件不带，按原来的文案规则判
                if event_audience(event) == AUDIENCE_UI:
                    emit_log(_framework_ui_message(message))
            elif event_type == "result" and isinstance(event.get("data"), dict):
                result_payload = event["data"]
                result_received.set()
            elif event_type == RUN_RECORD_EVENT_TYPE:
                # 结构化运行记录：只进专项记录，不进日志
                self._emit(MaaFWPlanRunRecord(event.get("data")))
            elif event_type == "error":
                message = str(event.get("message") or "")
                write_framework_log("runner-error", message)
                # Keep the complete error in the per-run framework log,
                # but apply the same native-noise filter as ordinary
                # framework diagnostics.  Worker error events can contain
                # an entire native parser/backtrace blob and must not
                # flood the user-facing task log.
                if event_audience(event) == AUDIENCE_UI:
                    emit_log(_framework_ui_message(message))

        async def read_events() -> None:
            """读事件通道：worker 打开管道、核对令牌后逐条分发；读到 EOF（worker 关闭管道或已退出、
            已写进去的都读完了）时结束。"""

            if event_server is None:
                return
            processed = 0
            try:
                async for event in event_server.events(
                    lambda note: write_framework_log("runner", note)
                ):
                    processed += 1
                    if processed % _RELAY_YIELD_EVERY_LINES == 0:
                        await asyncio.sleep(0)  # 同 read_stdout：别独占事件循环
                    handle_event(_redact_worker_event(event, secrets))
            finally:
                # 不再读了就立刻关掉：worker 再写会出错、改走 stdout，不会对着没人读的管道卡住
                event_server.close()

        async def feed_job() -> None:
            """把 job 写进 worker 的 stdin 再关掉；worker 先退出时写不进去，记一句就算了。"""

            stdin = process.stdin
            if stdin is None:
                return
            try:
                stdin.write(job_bytes)
                await stdin.drain()
            except (OSError, RuntimeError) as exc:
                write_framework_log(
                    "runner", f"MaaFW job 写入 worker 标准输入失败: {exc!r}"
                )
            finally:
                with suppress(Exception):
                    stdin.close()

        async def read_stdout() -> None:
            if process.stdout is None:
                return
            processed = 0
            async for raw_line in _iter_stream_lines(
                process.stdout,
                lambda: write_framework_log("worker-stdout", _STREAM_OVERRUN_NOTE),
            ):
                # StreamReader 缓冲里有数据时 `async for` 不会挂起，会一路取到
                # 缓冲耗尽为止。MaaFramework 的原生诊断动辄每秒几十行、单次运行
                # 几千行，这个循环于是能连续独占事件循环数十秒——真机上表现为
                # 界面日志停更、API 不响应、点了停止没反应，等这波处理完才一起
                # 恢复。定期显式让出，代价可以忽略。
                processed += 1
                if processed % _RELAY_YIELD_EVERY_LINES == 0:
                    await asyncio.sleep(0)
                # Worker protocol events are UTF-8 JSON, while MaaFramework
                # native diagnostics may be written directly to stdout using
                # the Windows ACP/GBK code page.  Decode protocol lines
                # strictly first and use the existing multi-codec fallback
                # for native text so Chinese diagnostics are not persisted as
                # replacement characters.
                try:
                    line = raw_line.decode("utf-8", errors="strict").strip()
                except UnicodeDecodeError:
                    line = decode_subprocess_output(raw_line).strip()
                if not line:
                    continue
                # 事件通道连上后 stdout 只剩原生诊断；通道建不起来、或中途断了，worker 把
                # 协议事件照旧一行一个 JSON 写在这里。
                event = _parse_worker_protocol_line(line, secrets)
                if event is None:
                    line = redact_secret_text(line, secrets)
                    write_framework_log("worker-stdout", line)
                    note_native_error(line)
                    if _should_forward_framework_log(line):
                        emit_log(_framework_ui_message(line))
                    continue
                handle_event(event)

        async def read_stderr() -> None:
            if process.stderr is None:
                return
            processed = 0
            async for raw_line in _iter_stream_lines(
                process.stderr,
                lambda: write_framework_log("worker-stderr", _STREAM_OVERRUN_NOTE),
            ):
                processed += 1
                if processed % _RELAY_YIELD_EVERY_LINES == 0:
                    await asyncio.sleep(0)  # 同 read_stdout：别独占事件循环
                line = clean_framework_output(
                    decode_subprocess_output(raw_line)
                ).strip()
                if not line:
                    continue
                line = redact_secret_text(line, secrets)
                write_framework_log("worker-stderr", line)
                note_native_error(line)
                stderr_lines.append(line)
                del stderr_lines[:-20]

        feed_task = asyncio.create_task(feed_job())
        events_task = asyncio.create_task(read_events())
        stdout_task = asyncio.create_task(read_stdout())
        stderr_task = asyncio.create_task(read_stderr())

        async def drain_readers(*, propagate_errors: bool) -> None:
            # worker 已经退出（或已被结束）：stdin 不用再写。事件通道把管道里剩下的读完、读到
            # EOF 就结束（写的一方没了，已写进去的照样读得出）；worker 从没打开过管道的话立刻
            # 结束，不再等。第二次调用时读取任务都已结束，这里不会再等。
            feed_task.cancel()
            if event_server is not None:
                event_server.worker_exited()
            _, pending_readers = await asyncio.wait(
                (stdout_task, stderr_task, events_task),
                timeout=5.0,
            )
            for task in pending_readers:
                task.cancel()
            reader_results = await asyncio.gather(
                stdout_task,
                stderr_task,
                events_task,
                return_exceptions=True,
            )
            await asyncio.gather(feed_task, return_exceptions=True)
            if propagate_errors:
                for result in reader_results:
                    if isinstance(result, Exception):
                        raise result

        try:
            returncode = await self._wait_worker_exit(process, result_received)
            await drain_readers(propagate_errors=True)
        finally:
            if process.returncode is None:
                await self.stop()
            elif self._process is process:
                self._process = None
            await drain_readers(propagate_errors=False)
            if event_server is not None:
                event_server.close()
            if framework_log_writer is not None:
                try:
                    await asyncio.to_thread(framework_log_writer.close)
                except Exception as exc:
                    emit_log(f"MaaFW worker 日志保存不完整: {exc}")
            try:
                copied = await asyncio.to_thread(
                    _copy_native_debug_log_delta,
                    native_debug_log_path,
                    native_debug_log_offset,
                    native_debug_log_rotations,
                    native_log_path,
                    secrets,
                )
            except Exception as exc:
                emit_log(f"MaaFW 原生日志复制失败: {exc}")
            else:
                if copied:
                    logger.info(f"MaaFW 原生日志已保存: {native_log_path}")
            # 资源包加载失败时找原因用：原生日志副本是 UTF-8、已打码，优先用它；worker stdout
            # 里同一行按控制台代码页转过，非 ASCII 的节点名 / 路径可能已成了「?」。
            native_errors = (
                await asyncio.to_thread(read_native_error_lines, native_log_path)
                if native_log_path.is_file()
                else []
            )
            self.native_errors = native_errors or list(stdout_native_errors)
            # 项目自己写的日志本次新增的部分：与 .maafw.log 同目录同前缀，按调用方给的
            # 项目日志打码值（脚本全部用户的密码）打码。
            project_log_path = history_dir / f"{history_stamp}.project.log"
            try:
                project_logs = await asyncio.to_thread(
                    copy_project_log_delta,
                    project_path,
                    project_log_marks,
                    project_log_path,
                    secrets=list(request.project_log_secrets),
                )
            except Exception as exc:
                emit_log(f"MaaFW 项目日志保存失败: {exc}")
            else:
                if project_logs.segments:
                    logger.info(
                        f"MaaFW 项目日志已保存: {project_log_path}"
                        f"（{len(project_logs.segments)} 个文件，"
                        f"{project_logs.written_bytes} 字节）"
                    )
            attachments = self.attachments
            for path, kind, role in (
                (worker_log_path, "log", "worker_log"),
                (native_log_path, "log", "native_log"),
                (project_log_path, "log", "project_log"),
            ):
                if path.is_file():
                    attachments.append(
                        MaaFWPlanRunAttachment(
                            path=path, kind=kind, role=role, display_name=path.name
                        )
                    )
            for image in history_dir.iterdir():
                if image.is_file() and image.suffix.lower() in {
                    ".png",
                    ".jpg",
                    ".jpeg",
                    ".webp",
                }:
                    attachments.append(
                        MaaFWPlanRunAttachment(
                            path=image,
                            kind="image",
                            role="failure_screenshot",
                            display_name=image.name,
                        )
                    )
            with suppress(Exception):
                await asyncio.to_thread(service.release_environment, runner_environment)
            service.unregister_worker(worker_id)

        if result_payload is not None:
            return MaaFWRunResult.model_validate(result_payload)
        message = f"MaaFW runner worker exited without result: {returncode}"
        self._point("run", "failed")
        detail = "\n".join(stderr_lines[-5:]).strip()
        if detail and _should_forward_framework_log(detail):
            message += f": {_framework_ui_message(detail)}"
        elif detail:
            # Native stderr is already preserved in the per-run framework log.
            # Do not copy parser/backtrace blobs into the normal task log when
            # the worker exits without a protocol result.
            message += (
                ": MaaFW worker 未返回任务结果，完整输出已保存到本次运行的 .worker.log"
            )
        raise RuntimeError(message)

    async def _wait_worker_exit(
        self,
        process: Any,
        result_received: asyncio.Event,
    ) -> int | None:
        """等 worker 退出；结果已经回传的话只再等有限时间。"""

        async def wait_exit():
            if self._request.desktop is not None:
                code, _, _ = await process.wait()
                return code
            return await process.wait()

        exit_task = asyncio.ensure_future(wait_exit())
        result_task = asyncio.ensure_future(result_received.wait())
        try:
            await asyncio.wait(
                {exit_task, result_task}, return_when=asyncio.FIRST_COMPLETED
            )
            if exit_task.done():
                return exit_task.result()
            try:
                return await asyncio.wait_for(
                    asyncio.shield(exit_task),
                    timeout=_WORKER_EXIT_AFTER_RESULT_SECONDS,
                )
            except asyncio.TimeoutError:
                self._log("MaaFW worker 已回传结果但迟迟不退出，强制结束以免拖过时限")
                await self.stop()
                return process.returncode
        finally:
            for task in (exit_task, result_task):
                if not task.done():
                    task.cancel()

    async def stop(self) -> None:
        """结束正在跑的 worker（整轮超时、被取消、结果回传后不退出、调用方停止任务时）。

        普通子进程先记下进程树再 terminate，等 5 秒不退就 kill，然后结束记下的后代；桌面分身
        里的交给它自己的 ``stop``。没有在跑的 worker 就什么都不做。
        """

        process = self._process
        self._process = None
        if process is None or process.returncode is not None:
            return

        if self._request.desktop is not None:
            with self._operation("stop_script"):
                await process.stop()
            return

        # 必须在 terminate 之前把后代记下来：Windows 的 TerminateProcess 是立即
        # 且不可捕获的，worker 的 shutdown() 没机会跑；而父进程一死，子进程就
        # 被重新挂到别处，事后再按父子关系已经查不到它们。
        descendants = await asyncio.to_thread(_snapshot_descendants, process.pid)

        self._point("stop_script")
        try:
            process.terminate()
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
        except ProcessLookupError:
            pass
        except Exception as exc:
            logger.warning(f"MaaFW runner worker 清理失败: {exc}")

        if descendants:
            await asyncio.to_thread(terminate_process_snapshot, descendants)
        self._point(
            "stop_script",
            "succeeded" if process.returncode is not None else "failed",
        )


# ---------------------------------------------------------------------------
# 环境准备的取消
# ---------------------------------------------------------------------------


async def _abandon_environment_preparation(
    prepare_task: "asyncio.Future[Any]",
    *,
    release: Any,
    grace_seconds: float,
    send_log: Any = None,
) -> None:
    """任务取消后有界等待环境准备收尾。

    调用方已把取消令牌置位。准备若在 ``grace_seconds`` 内以异常结束（安装被
    终止），直接返回；若恰好成功，释放拿到的租约。超过限期就不再等：收尾任务
    继续在后台跑，准备线程随 uv 子进程被杀而尽快结束。
    """

    async def release_after_prepare() -> None:
        try:
            prepared_after_cancel = await prepare_task
        except BaseException:
            return
        with suppress(Exception):
            await asyncio.to_thread(release, prepared_after_cancel)

    cleanup_task = asyncio.create_task(release_after_prepare())
    scope = current_process_scope.get()
    if scope is not None:
        scope.retain_worker(cleanup_task)
        if scope.closed:
            grace_seconds = 0
    try:
        await asyncio.wait_for(asyncio.shield(cleanup_task), timeout=grace_seconds)
    except asyncio.TimeoutError:
        _ABANDONED_PREPARATION_CLEANUPS.add(cleanup_task)
        cleanup_task.add_done_callback(_ABANDONED_PREPARATION_CLEANUPS.discard)
        if send_log is not None:
            send_log(
                "[MaaFW Runner] 环境准备未能在 "
                f"{grace_seconds:g} 秒内响应取消，已放弃等待"
            )
    except asyncio.CancelledError:
        # 再次被取消：同样不再等，收尾留给后台任务。
        _ABANDONED_PREPARATION_CLEANUPS.add(cleanup_task)
        cleanup_task.add_done_callback(_ABANDONED_PREPARATION_CLEANUPS.discard)


# ---------------------------------------------------------------------------
# worker 日志
# ---------------------------------------------------------------------------


class _FrameworkLogWriter:
    """在专用线程中按提交顺序写入一次运行的框架日志。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._queue: queue.Queue[tuple[str, str, str] | None] = queue.Queue()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._open_error: Exception | None = None
        self._write_error: Exception | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run,
            name="maafw-framework-log-writer",
            daemon=True,
        )
        self._thread.start()
        self._ready.wait()
        if self._open_error is not None:
            self.close()
            raise self._open_error

    def write(self, source: str, message: str) -> None:
        if self._thread is None:
            return
        timestamp = datetime.now().astimezone().strftime("%H:%M:%S.%f")[:-3]
        try:
            self._queue.put((timestamp, source, str(message or "")))
        except Exception:
            return

    def close(self) -> None:
        thread = self._thread
        if thread is None:
            return
        self._queue.join()
        self._queue.put(None)
        thread.join()
        self._thread = None
        if self._write_error is not None:
            raise RuntimeError(
                f"MaaFW 框架日志写入不完整: {self._write_error}"
            ) from self._write_error

    def _run(self) -> None:
        log_file: Any | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            log_file = self.path.open(
                "a",
                encoding="utf-8",
                buffering=1,
            )
        except Exception as exc:
            self._open_error = exc
            self._ready.set()
            return

        self._ready.set()
        try:
            while True:
                item = self._queue.get()
                try:
                    if item is None:
                        return
                    timestamp, source, message = item
                    cleaned = clean_framework_output(message)
                    for line in cleaned.splitlines() or [""]:
                        try:
                            log_file.write(f"[{timestamp}] [{source}] {line}\n")
                        except Exception as exc:
                            if self._write_error is None:
                                self._write_error = exc
                            continue
                except Exception as exc:
                    if self._write_error is None:
                        self._write_error = exc
                finally:
                    self._queue.task_done()
        finally:
            try:
                log_file.close()
            except Exception as exc:
                if self._write_error is None:
                    self._write_error = exc


def decode_subprocess_output(data: bytes) -> str:
    """子进程输出按 UTF-8 → GBK → Shift-JIS → UTF-16 依次试着解码，都不行按 latin1。"""

    if not data:
        return ""
    for encoding in _SUBPROCESS_OUTPUT_ENCODINGS:
        try:
            return data.decode(encoding, errors="strict")
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("latin1", errors="replace")


def clean_framework_output(message: str) -> str:
    return strip_ansi(message)


async def _iter_stream_lines(
    stream: asyncio.StreamReader, on_overrun: Callable[[], None]
) -> AsyncIterator[bytes]:
    """逐行读子进程输出；单行超过 StreamReader 上限时丢掉这一行、记一句，接着读。

    ``async for line in stream`` 碰到超长行直接抛 ValueError，读取任务随之结束，之后没人
    读管道，worker 写满管道就挂住。StreamReader 抛错前已经把那一行（或缓冲）丢掉，
    接着读是安全的。
    """

    while True:
        try:
            line = await stream.readline()
        except ValueError:
            on_overrun()
            continue
        if not line:
            return
        yield line


def _framework_ui_message(message: str) -> str:
    """Bound worker diagnostics copied to the user-facing task log.

    Complete worker output (runner events, worker stdout/stderr) is already
    retained in ``*.worker.log``. A malformed task/encoding error can otherwise
    contain megabytes of JSON or a parser trace and make the normal task page
    unusable.
    """

    cleaned = clean_framework_output(message).strip()
    if len(cleaned) <= _FRAMEWORK_UI_LOG_MAX_CHARS:
        return cleaned
    lines = cleaned.splitlines()
    compact = "\n".join(line[:240] for line in lines[:8]).strip()
    omitted = max(0, len(cleaned) - len(compact))
    summary = (
        f"{compact}\n… 上述内容已省略 {omitted} 个字符，"
        "完整内容请查看本次运行的 .worker.log"
    )
    return summary[:_FRAMEWORK_UI_LOG_MAX_CHARS]


def _parse_worker_protocol_line(
    line: str, secrets: list[str] | tuple[str, ...]
) -> dict[str, Any] | None:
    """worker stdout 的一行若是协议事件（JSON 对象）就解析并打码后返回，否则 None。

    **先解析、后打码**：以前对整行 JSON 做字符串替换，密码恰好是 ``true`` / ``result`` /
    ``success`` / ``2026`` 或某个任务名时，替换会打坏 JSON 结构、键名、截图路径、完成任务
    列表——成功的运行被判成「worker exited without result」而重试，或通知丢图、周期任务
    不记完成。现在只替换给人读的文本（log / error 的 ``message``、结果里的
    ``errorMessage`` / ``userMessage``），结构字段（路径、任务名、状态、布尔、数字）一律不动。
    解析不了的行（原生诊断）由调用方照旧整行打码。
    """

    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(event, dict):
        return None
    return _redact_worker_event(event, secrets)


def _redact_worker_event(
    event: dict[str, Any], secrets: list[str] | tuple[str, ...]
) -> dict[str, Any]:
    """协议事件只打码给人读的文本（见 ``_parse_worker_protocol_line``）；事件通道与 stdout 同一口径。"""

    message = event.get("message")
    if isinstance(message, str):
        event["message"] = redact_secret_text(message, secrets)
    data = event.get("data")
    if isinstance(data, dict):
        for key in ("errorMessage", "userMessage"):
            if isinstance(data.get(key), str):
                data[key] = redact_secret_text(data[key], secrets)
    return event


def _should_forward_framework_log(message: str) -> bool:
    """stdout / stderr 上的原生诊断与不带 audience 的旧格式事件进不进界面（规则在 worker_protocol）。"""

    return forwards_to_ui(message)


# ---------------------------------------------------------------------------
# 原生日志
# ---------------------------------------------------------------------------


def _iter_rotated_native_debug_logs(path: Path) -> list[Path]:
    """按轮转时间升序列出 MaaFW 的历史原生日志。

    文件名形如 ``maafw.bak.2026.08.30-22.58.30.451.log``，时间戳是零填充的
    定宽字段，按文件名排序即按时间排序。
    """

    try:
        return sorted(path.parent.glob(path.stem + ".bak.*" + path.suffix))
    except OSError:
        return []


def _snapshot_native_debug_log_state(path: Path) -> tuple[int, frozenset[str]]:
    """记下原生日志的读取起点：当前大小，以及运行前已存在的轮转文件。"""

    try:
        offset = path.stat().st_size
    except OSError:
        offset = 0
    return offset, frozenset(
        rotated.name for rotated in _iter_rotated_native_debug_logs(path)
    )


def _plan_native_debug_log_sources(
    path: Path,
    start_offset: int,
    known_rotations: frozenset[str],
) -> list[tuple[str, Path, int]]:
    """列出本次运行写下的原生日志分片，按时间先后排列。

    MaaFW 会在 ``maafw.log`` 涨到一定大小时把它整体挪成
    ``maafw.bak.<时间戳>.log``，再开一个空文件继续写。只记字节偏移不够用：
    轮转后新文件重新长回超过该偏移，收尾时便会拿运行前的偏移去 seek 一个
    内容毫不相干的文件——运行前半段凭空消失，切口还落在任意字节上。而长到
    足以触发轮转的运行，恰恰是最需要日志的那些。

    所以改为对比运行前后的轮转文件集合：新出现的那些就是本次运行被挪走的
    内容。其中最早的一个才是运行开始时正在写的文件，只有它要跳过运行前已有
    的部分，其余分片都从头读。
    """

    rotated = [
        candidate
        for candidate in _iter_rotated_native_debug_logs(path)
        if candidate.name not in known_rotations
    ]
    sources: list[tuple[str, Path, int]] = [
        ("debug/" + candidate.name, candidate, start_offset if index == 0 else 0)
        for index, candidate in enumerate(rotated)
    ]
    sources.append(("debug/" + path.name, path, 0 if rotated else start_offset))
    return sources


def _copy_native_debug_log_delta(
    path: Path,
    start_offset: int,
    known_rotations: frozenset[str],
    target: Path,
    secrets: list[str] | tuple[str, ...] = (),
) -> int:
    """把本次运行写下的原生日志分片按顺序原样追加到 ``target``，返回复制的字节数。

    按字节复制、不解码不清洗，副本才和项目 ``debug/maafw.log`` 完全一致。每次尝试
    各写各的文件（文件名是这次尝试的开始时刻），追加只是为了不覆盖已有内容。
    逐个分片流式复制，一份可能有几十 MB。

    唯一的改动是 ``secrets``（密码字段的原文及其 JSON 转义写法）：框架在
    ``Tasker::post_task`` 里按 INFO 级别记下整份 ``pipeline_override``（``[pipeline_override={...}]``），
    密码会原样出现；给了就逐行换成占位（按 UTF-8 / GBK / UTF-16LE 的字节替换，其余字节不动）。项目目录里框架
    自己写的 ``debug/maafw.log`` 不归 MAS 管，那份仍是原文。
    """

    # 每个写法按 UTF-8 / GBK / UTF-16LE 的字节都换（与 .project.log 同一套，见 run_redaction）。
    secret_pairs = secret_byte_pairs(list(secrets))

    copied = 0
    target_file: Any | None = None
    try:
        for _label, source_path, source_offset in _plan_native_debug_log_sources(
            path, start_offset, known_rotations
        ):
            try:
                current_size = source_path.stat().st_size
            except OSError:
                continue
            source_offset = source_offset if current_size >= source_offset else 0
            if current_size <= source_offset:
                continue
            if target_file is None:
                target.parent.mkdir(parents=True, exist_ok=True)
                target_file = target.open("ab")
            with source_path.open("rb") as source_file:
                source_file.seek(source_offset)
                if secret_pairs:
                    for raw_line in source_file:
                        for secret, placeholder in secret_pairs:
                            if secret in raw_line:
                                raw_line = raw_line.replace(secret, placeholder)
                        target_file.write(raw_line)
                else:
                    shutil.copyfileobj(source_file, target_file)
                copied += source_file.tell() - source_offset
    finally:
        if target_file is not None:
            target_file.close()
    return copied


# ---------------------------------------------------------------------------
# 进程树与旧 job 文件
# ---------------------------------------------------------------------------


def _snapshot_descendants(pid: int) -> list[tuple[int, float]]:
    """记下某进程当前的全部后代（pid 与创建时间）。

    创建时间与 pid 配对使用，防止 pid 复用导致误杀——这段时间里原进程可能
    已经退出、pid 被别人占了。
    """

    snapshot: list[tuple[int, float]] = []
    try:
        for child in psutil.Process(pid).children(recursive=True):
            with suppress(psutil.Error):
                snapshot.append((child.pid, child.create_time()))
    except psutil.Error:
        return []
    return snapshot


def terminate_process_snapshot(
    snapshot: list[tuple[int, float]], *, owner: str = "MaaFW worker"
) -> None:
    """结束快照里仍然存活、且身份对得上的进程。

    worker 被强杀后它启动的 agent 会变成孤儿：MaaFW 的 AgentClient 用 IPC 起
    agent，生命周期本该随 worker，但 TerminateProcess 不给收尾机会。实测残留
    过二十多个 agent.exe / python.exe，最老的有二十二小时，它们占内存也占文件
    句柄——曾导致 venv 目录删不掉。
    """

    victims: list[psutil.Process] = []
    for pid, create_time in snapshot:
        try:
            process = psutil.Process(pid)
            if abs(process.create_time() - create_time) > 1:
                continue  # pid 被复用了，不是当初那个进程
            process.terminate()
            victims.append(process)
        except psutil.Error:
            continue
    if not victims:
        return
    _gone, alive = psutil.wait_procs(victims, timeout=3)
    for process in alive:
        with suppress(psutil.Error):
            process.kill()
    psutil.wait_procs(alive, timeout=2)
    logger.info(f"已清理 {owner} 残留的 {len(victims)} 个子进程")


def sweep_legacy_runner_jobs() -> None:
    """清掉升级前的版本留下的 job 文件（现在 job 经 worker 的 stdin 传，不再落盘）。

    旧版本把 job 写在 ``data/maafw_runner_jobs``（更早是 ``runtime/maafw_runner_jobs``，
    首次访问时整体迁过来再清）。目录本身不再新建。
    """

    jobs_dir = Path.cwd() / "data" / "maafw_runner_jobs"
    _utils_io.migrate_legacy_dir(Path.cwd() / "runtime" / "maafw_runner_jobs", jobs_dir)
    _sweep_stale_runner_jobs(jobs_dir)


def _sweep_stale_runner_jobs(directory: Path) -> None:
    """删掉上次异常退出残留的 job 文件：里面可能有解密后的密码选项。"""

    try:
        candidates = list(directory.glob("maafw-runner-job-*.json"))
    except OSError:
        return
    now = time.time()
    for path in candidates:
        try:
            if now - path.stat().st_mtime < _STALE_RUNNER_JOB_SECONDS:
                continue
            path.unlink()
        except OSError:
            continue
        logger.info(f"已清理残留的 MaaFW job 文件: {path.name}")


__all__ = [
    "WORKER_STREAM_LINE_LIMIT",
    "MaaFWPlanRun",
    "MaaFWPlanRunAttachment",
    "MaaFWPlanRunEvent",
    "MaaFWPlanRunLog",
    "MaaFWPlanRunOutcome",
    "MaaFWPlanRunPoint",
    "MaaFWPlanRunRecord",
    "MaaFWPlanRunRequest",
    "MaaFWPlanRunSink",
    "MaaFWPlanRunStage",
    "MaaFWRunTimeoutError",
    "MaaFWTaskDeadlineExpired",
    "clean_framework_output",
    "decode_subprocess_output",
    "sweep_legacy_runner_jobs",
    "terminate_process_snapshot",
]
