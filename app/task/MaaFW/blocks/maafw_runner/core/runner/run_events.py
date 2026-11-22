"""结构化运行记录的事件：worker 在运行中推给宿主的阶段与任务起止。

协议行与 ``log`` / ``result`` / ``error`` 一样是 worker stdout 上的一行 JSON：
``{"type": "record", "data": <下面某个事件>}``。事件的形状、阶段名、结局与失败类别只在
这里定义；宿主（``tools/embedded/run_record.py``）与 worker（``runner.py``）都从这里取，
换传输通道时只搬这一处。

只记已有判定能可靠得出的东西：阶段是 ``MaaFWRunner`` 里真实存在的初始化步骤，任务结局
与类别取自现有的收尾分支（单任务时限、原地打转、信号节点、脚本侧强停……），不另做判断。
记录是旁路：发不出去、宿主不认，运行照常。
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

# worker stdout 协议行的 type。
RUN_RECORD_EVENT_TYPE = "record"

# ---- 阶段 ------------------------------------------------------------------
# worker 侧（MaaFWRunner._ensure_initialized 的顺序，加上首个任务前的启动闸门）
STAGE_RUNTIME = "runtime"  # 加载 MaaFramework 原生库、全局初始化
STAGE_DEVICE = "device"  # 设备类型核对、ADB 设备就绪等待
STAGE_RESOURCE = "resource"  # 原生插件、资源包、信号节点扫描
STAGE_CONTROLLER = "controller"  # 建控制器、连接、首张截图
STAGE_AGENT = "agent"  # agent 环境检查、起进程、连上
STAGE_START_GATE = "start_gate"  # 游戏刚启动时，首个任务前等画面 / 读盘
# 宿主侧（runner_task 自己记，不经 worker）
STAGE_PRETASK = "pretask"  # interface 的运行前设置
STAGE_CLIENT = "client"  # 拉起 / 接管游戏、开模拟器、解析设备
STAGE_ENVIRONMENT = "environment"  # 运行池环境准备

# ---- 任务结局 ---------------------------------------------------------------
OUTCOME_SUCCEEDED = "succeeded"
OUTCOME_FAILED = "failed"
OUTCOME_SKIPPED = "skipped"  # 本轮没轮到（前面结束了本轮）
OUTCOME_TIMEOUT = "timeout"
OUTCOME_LOOP = "loop"  # 原地打转检测停下
OUTCOME_STOPPED = "stopped"  # 用户停止、脚本侧强停、信号节点命中

MaaFWTaskOutcome = Literal[
    "succeeded", "failed", "skipped", "timeout", "loop", "stopped"
]

# ---- 失败类别 ---------------------------------------------------------------
# 任务级（worker 判定）
CATEGORY_TASK_FAILED = "task_failed"  # 任务本身失败（pipeline 走不通、投递失败）
CATEGORY_TASK_TIMEOUT = "task_timeout"  # 单任务时限
CATEGORY_RUN_TIMEOUT = "run_timeout"  # 整次运行的时限（Run.RunTimeLimit）
CATEGORY_LOOP_GUARD = "loop_guard"  # 原地打转
CATEGORY_SCRIPT_STOPPED = "script_stopped"  # 项目自己 post_stop
CATEGORY_USER_STOPPED = "user_stopped"
CATEGORY_SIGNAL = "signal"  # 项目声明的信号节点（停服维护 / 需要更新客户端）
CATEGORY_GAME_LAUNCH_FAILED = "game_launch_failed"  # start_app 失败
CATEGORY_AGENT_EXITED = "agent_exited"
# 尝试级（宿主按 MaaFWRunResult 的现有字段与现有判定归类）
CATEGORY_INIT_FAILED = "init_failed"  # 任务开始之前就失败了，见 failedStage
CATEGORY_RESOURCE_FAILURE = "resource_failure"
CATEGORY_ENVIRONMENT = "environment"  # 运行环境不可用（重试也没用的那一类）
CATEGORY_PRETASK_FAILED = "pretask_failed"
CATEGORY_GAME_UPDATE_REQUIRED = "game_update_required"
CATEGORY_HOST_ERROR = "host_error"  # 宿主侧其它异常（worker 没回结果等）


class MaaFWStageEvent(BaseModel):
    """一个阶段开始（``begin``）或结束（``end``）。``ok`` 只在结束时给：假表示在这一步失败。"""

    kind: Literal["stage"] = "stage"
    stage: str
    state: Literal["begin", "end"]
    ok: bool | None = None
    at: float = Field(description="time.time() 秒")


class MaaFWTaskStartEvent(BaseModel):
    """计划里第 ``index`` 个任务（从 0 数）开始投递；``total`` 是本次计划的任务数。"""

    kind: Literal["task_start"] = "task_start"
    index: int
    total: int
    name: str
    label: str | None = None
    at: float


class MaaFWTaskEndEvent(BaseModel):
    """任务结束。``counted`` 为假：特调声明的收尾任务被放过，不计入本轮失败。"""

    kind: Literal["task_end"] = "task_end"
    index: int
    name: str
    outcome: MaaFWTaskOutcome
    category: str | None = None
    counted: bool = True
    at: float


MaaFWRunRecordEvent = Annotated[
    MaaFWStageEvent | MaaFWTaskStartEvent | MaaFWTaskEndEvent,
    Field(discriminator="kind"),
]

_EVENT_ADAPTER: TypeAdapter[Any] = TypeAdapter(MaaFWRunRecordEvent)


def parse_run_record_event(
    data: Any,
) -> MaaFWStageEvent | MaaFWTaskStartEvent | MaaFWTaskEndEvent | None:
    """协议行 ``data`` 转成事件；形状不对返回 None（新旧两边字段不一致时不拖垮运行）。"""

    try:
        return _EVENT_ADAPTER.validate_python(data)
    except ValidationError:
        return None


__all__ = [
    "CATEGORY_AGENT_EXITED",
    "CATEGORY_ENVIRONMENT",
    "CATEGORY_GAME_LAUNCH_FAILED",
    "CATEGORY_GAME_UPDATE_REQUIRED",
    "CATEGORY_HOST_ERROR",
    "CATEGORY_INIT_FAILED",
    "CATEGORY_LOOP_GUARD",
    "CATEGORY_PRETASK_FAILED",
    "CATEGORY_RESOURCE_FAILURE",
    "CATEGORY_RUN_TIMEOUT",
    "CATEGORY_SCRIPT_STOPPED",
    "CATEGORY_SIGNAL",
    "CATEGORY_TASK_FAILED",
    "CATEGORY_TASK_TIMEOUT",
    "CATEGORY_USER_STOPPED",
    "MaaFWRunRecordEvent",
    "MaaFWStageEvent",
    "MaaFWTaskEndEvent",
    "MaaFWTaskOutcome",
    "MaaFWTaskStartEvent",
    "OUTCOME_FAILED",
    "OUTCOME_LOOP",
    "OUTCOME_SKIPPED",
    "OUTCOME_STOPPED",
    "OUTCOME_SUCCEEDED",
    "OUTCOME_TIMEOUT",
    "RUN_RECORD_EVENT_TYPE",
    "STAGE_AGENT",
    "STAGE_CLIENT",
    "STAGE_CONTROLLER",
    "STAGE_DEVICE",
    "STAGE_ENVIRONMENT",
    "STAGE_PRETASK",
    "STAGE_RESOURCE",
    "STAGE_RUNTIME",
    "STAGE_START_GATE",
    "parse_run_record_event",
]
