"""一次尝试的结果判定：吃「运行结果或异常」，返回普通数据的判定。

任务类的重试主循环只读这个判定决定怎么走：这次算成功、命中项目信号（停服维护 = 本次跳过，
需要更新客户端 = 失败）、游戏客户端要手动更新，还是失败；失败了还重不重试、要不要先修资源包、
重试前要不要重启游戏 / 模拟器、要不要补一句「运行环境不可用」；以及进运行记录的尝试级类别。
循环本身（次数、日志、通知、收尾）仍在任务类，三个专项各自的流程将来都调这同一个判定。

不读配置、不碰调用方的对象；判据只看结果字段、异常类型与消息里的环境级标记。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.task.MaaFW.tools.core.native.project_runtime import (
    ARCHITECTURE_MISMATCH_MARKERS,
)
from app.task.MaaFW.tools.core.runner.models import MaaFWRunResult
from app.task.MaaFW.tools.core.runner.run_events import (
    CATEGORY_ENVIRONMENT,
    CATEGORY_GAME_UPDATE_REQUIRED,
    CATEGORY_HOST_ERROR,
    CATEGORY_PRETASK_FAILED,
    CATEGORY_RESOURCE_FAILURE,
    CATEGORY_RUN_TIMEOUT,
)
from app.task.MaaFW.tools.core.worker_protocol import SERVER_MAINTENANCE

from .flavor import MaaFWLoginRequired
from .plan_run import MaaFWRunTimeoutError
from .pretask_run import MaaFWPretaskError

# 环境级失败：解释器自身坏了、依赖没装上。重试只会原样再失败一遍，而每次重试
# 还要重启一遍模拟器/游戏——默认 RunTimesLimit=3，白等好几分钟才告诉用户同一件事。
# 判据取消息标记而不是异常类型：这些错误跨了 runtime_pool 与 runner 两个包，
# 而宿主有意不在模块层导入 runtime_pool（那会让所有请求都付出导入成本）。
UNRETRYABLE_ENVIRONMENT_MARKERS = (
    "MaaFW runtime Python 自检失败",
    "MaaFW runtime ABI 探测失败",
    "runtime Python identity could not be verified",
    "MaaFW Runner 环境准备失败",
    "MaaFW Runner 环境准备超时",
    # 项目自带的 MaaFramework 与本机架构不符：换哪次尝试都是同一份库。运行前自检一般已
    # 拦下，这里兜住 worker 侧才发现的情况（异常与任务失败两条路都认）。
    *ARCHITECTURE_MISMATCH_MARKERS,
)


class MaaFWGameUpdateRequired(RuntimeError):
    """特调的游戏更新钩子判定客户端要手动更新：本账号本次判失败，不重试。"""


class MaaFWWorkstationLocked(RuntimeError):
    """电脑锁着屏，要用交互式桌面的控制器跑不了：本账号本次判失败，不重试。"""


#: 判定的结局。
VERDICT_SUCCEEDED = "succeeded"
VERDICT_SIGNAL = "signal"
VERDICT_GAME_UPDATE_REQUIRED = "game_update_required"
VERDICT_FAILED = "failed"

MaaFWAttemptOutcome = Literal["succeeded", "signal", "game_update_required", "failed"]


@dataclass(frozen=True)
class MaaFWAttemptVerdict:
    """一次尝试的判定（普通数据）。

    - ``outcome``：``succeeded`` / ``signal``（项目信号命中，不重试、不重启，直接收尾）/
      ``game_update_required``（游戏客户端要手动更新，不重试）/ ``failed``。
    - ``category``：进运行记录的尝试级类别；None 时由运行记录按任务结局补。
    - ``retry``：失败后还要不要再试（剩余任务都完成了不再试，那一条由调用方按计划判）。
    - ``repair_resource``：资源包加载失败，先修资源再看要不要立刻再跑（不占重试次数），不重启。
    - ``restart_client``：再试之前要不要关掉 MAS 自己起的游戏 / 模拟器。
    - ``environment_unusable``：要补一句「运行环境不可用，重试也不会有别的结果，已停止本轮」。
    - ``signal`` / ``maintenance``：命中的信号，以及它是不是停服维护（本次跳过）。
    - ``message`` / ``user_message``：异常时的账号日志文案与推送用的原文（整次运行超时有固定
      说法，``user_message`` 为 None）；运行结果的失败文案要读配置与原生报错，仍由调用方拼。
    """

    outcome: MaaFWAttemptOutcome
    category: str | None = None
    retry: bool = False
    repair_resource: bool = False
    restart_client: bool = False
    environment_unusable: bool = False
    signal: str | None = None
    maintenance: bool = False
    message: str | None = None
    user_message: str | None = None


def is_environment_failure(message: str) -> bool:
    """消息里有环境级失败的标记（``UNRETRYABLE_ENVIRONMENT_MARKERS``）：重试也一样。"""

    return any(marker in message for marker in UNRETRYABLE_ENVIRONMENT_MARKERS)


def result_failure_category(result: MaaFWRunResult) -> str | None:
    """worker 回报失败时尝试级的类别：只看结果里已有的字段与现有的环境级判定。

    返回 None 时由运行记录按任务结局补（任务都没开始是初始化失败）。
    """

    if result.resourceFailure is not None:
        return CATEGORY_RESOURCE_FAILURE
    if result.timedOut:
        return CATEGORY_RUN_TIMEOUT
    if is_environment_failure(result.errorMessage or ""):
        return CATEGORY_ENVIRONMENT
    return None


def _judge_exception(exc: BaseException) -> MaaFWAttemptVerdict:
    if isinstance(exc, MaaFWGameUpdateRequired):
        # 说明已由游戏更新钩子写进运行日志，调用方不再重复。
        return MaaFWAttemptVerdict(
            outcome=VERDICT_GAME_UPDATE_REQUIRED,
            category=CATEGORY_GAME_UPDATE_REQUIRED,
            message=str(exc),
        )
    locked = isinstance(exc, MaaFWWorkstationLocked)
    message = (
        str(exc)
        if isinstance(
            exc, (MaaFWPretaskError, MaaFWLoginRequired, MaaFWWorkstationLocked)
        )
        else f"MaaFW 运行异常: {exc}"
    )
    unretryable = locked or is_environment_failure(message)
    return MaaFWAttemptVerdict(
        outcome=VERDICT_FAILED,
        category=(
            CATEGORY_PRETASK_FAILED
            if isinstance(exc, MaaFWPretaskError)
            else CATEGORY_RUN_TIMEOUT
            if isinstance(exc, MaaFWRunTimeoutError)
            else CATEGORY_ENVIRONMENT
            if unretryable
            else CATEGORY_HOST_ERROR
        ),
        retry=not unretryable,
        restart_client=not unretryable,
        # 锁屏的说明自带「不重试」，不再重复一句
        environment_unusable=unretryable and not locked,
        message=message,
        # 宿主自己抛的多是 MAS 写的人话（「当前 controller 需要 ADB，请在托管管理页
        # 选择模拟器」「Path未配置」），推送照它说；带的排障片段由 run_report 滤掉。
        # 整次运行超时有固定说法，不用异常原文
        user_message=None if isinstance(exc, MaaFWRunTimeoutError) else str(exc),
    )


def _judge_result(result: MaaFWRunResult) -> MaaFWAttemptVerdict:
    if result.signal is not None:
        # 项目声明的信号节点命中：停服维护 = 本次跳过，需要更新客户端 = 失败；
        # 两种都是重试多少次都一样，不重启游戏 / 模拟器，直接收尾。
        return MaaFWAttemptVerdict(
            outcome=VERDICT_SIGNAL,
            signal=str(result.signal),
            maintenance=result.signal == SERVER_MAINTENANCE,
        )
    if result.success:
        return MaaFWAttemptVerdict(outcome=VERDICT_SUCCEEDED)
    category = result_failure_category(result)
    if result.resourceFailure is not None:
        # 资源包没能加载：资源文件一次尝试到下一次不会自己变，不重启游戏 / 模拟器；
        # 只有修过资源（视图换了载荷）才立刻再跑一次。
        return MaaFWAttemptVerdict(
            outcome=VERDICT_FAILED, category=category, repair_resource=True
        )
    if is_environment_failure(result.errorMessage or ""):
        # worker 在任务里报的环境级失败（如原生库架构不符）：每轮都一样，
        # 不再为它起停模拟器 / 游戏重试。
        return MaaFWAttemptVerdict(
            outcome=VERDICT_FAILED, category=category, environment_unusable=True
        )
    return MaaFWAttemptVerdict(
        outcome=VERDICT_FAILED, category=category, retry=True, restart_client=True
    )


def judge_attempt(outcome: MaaFWRunResult | BaseException) -> MaaFWAttemptVerdict:
    """一次尝试的判定：``outcome`` 是 worker 回报的结果，或这次尝试里抛出的异常。"""

    if isinstance(outcome, BaseException):
        return _judge_exception(outcome)
    return _judge_result(outcome)


__all__ = [
    "UNRETRYABLE_ENVIRONMENT_MARKERS",
    "VERDICT_FAILED",
    "VERDICT_GAME_UPDATE_REQUIRED",
    "VERDICT_SIGNAL",
    "VERDICT_SUCCEEDED",
    "MaaFWAttemptVerdict",
    "MaaFWGameUpdateRequired",
    "MaaFWWorkstationLocked",
    "is_environment_failure",
    "judge_attempt",
    "result_failure_category",
]
