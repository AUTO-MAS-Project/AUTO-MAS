"""专项在动作发生处通知本次运行的观察者；不持久化，也不驱动调度。"""

from asyncio import CancelledError
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Literal

from app.utils import get_logger
from app.utils.common.game_update import GameUpdateResult

type RunStage = Literal[
    "script_update",
    "game_update",
    "start_game",
    "start_script",
    "run",
    "stop_script",
    "stop_game",
    "attempt",
    "retry",
    "finalize",
    "special",
    "task",
]
type PointState = Literal[
    "entered", "succeeded", "failed", "cancelled", "stopped", "skipped", "matched"
]


@dataclass(frozen=True, slots=True)
class RunPoint:
    stage: RunStage
    state: PointState
    key: str = ""
    attempt: int | None = None


type RunObserver = Callable[[object, RunPoint], None]
_observer: ContextVar[RunObserver | None] = ContextVar("run_observer", default=None)
logger = get_logger("专项运行进度")


@contextmanager
def observe_run(observer: RunObserver) -> Iterator[None]:
    """在一个调度协程及其子任务内旁听；owner 是实际执行器，不是配置 UUID。"""
    token = _observer.set(observer)
    try:
        yield
    finally:
        _observer.reset(token)


def point(
    owner: object,
    stage: RunStage,
    *,
    state: PointState = "entered",
    key: str = "",
    attempt: int | None = None,
) -> None:
    """只报告明确发生的事实；正常返回不等于成功，未调用不等于跳过。"""
    if (observer := _observer.get()) is not None:
        try:
            observer(owner, RunPoint(stage, state, key, attempt))
        except (CancelledError, Exception):
            # 可视化故障不能改变原任务的结果，也不能阻止关闭进程和还原配置。
            logger.opt(exception=True).warning("专项运行进度观察失败")


def begin_attempt(owner: object, number: int, *, phase: str = "") -> None:
    """在进入循环体后调用；新阶段的第一次尝试不是前一阶段的重试。"""
    if number > 1:
        point(owner, "retry", key=phase, attempt=number)
    point(owner, "attempt", key=phase, attempt=number)


@contextmanager
def operation(owner: object, stage: RunStage) -> Iterator[None]:
    """仅包住以异常表示失败的动作；返回业务结果的检查在判定处上报。"""
    point(owner, stage)
    try:
        yield
    except CancelledError:
        point(owner, stage, state="cancelled")
        raise
    except Exception:
        point(owner, stage, state="failed")
        raise
    else:
        point(owner, stage, state="succeeded")


def game_update_result(owner: object, result: GameUpdateResult) -> None:
    """检查通过和确实安装分别保留；需要手动更新不是已完成。"""
    state: PointState = "succeeded"
    if result.status == "Skipped":
        state = "skipped"
    elif result.status == "NeedManualUpdate":
        state = "failed"
    point(owner, "game_update", state=state, key=result.status)
