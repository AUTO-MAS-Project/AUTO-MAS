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

"""手动更新（``/maafw/update`` 的 ``apply``）放到后台跑，按脚本登记过程与结果，
页面刷新、切走、关掉前端再打开都能接回来（``/maafw/update/job``）。

为什么不走 dispatch 的 ``mode: "Update"``：那条路要 MaaFW 管理器新增一种任务模式、把
``update_project`` 的应用流程搬进去；它整段锁住脚本、进调度台的任务列表；结果只有任务
日志，没有编辑页要的结构化结果（版本、下载来源、CDK 状态）；任务结束后 ``task_info``
即删，刷新后取不回结果。这里只在 ``update_project`` 外面包一层后台执行加登记：

- 同一脚本同时只有一份：进行中再发起 ``apply`` 直接接上那一份，拿到的是同一个结果。
- 登记只在进程内、不落盘：保留到这个脚本下一次手动更新开始或后端重启。
- 进度事件沿用 ``maafw.project-update.progress``（字段不变），推送前顺手记一份（只记这次应用
  自己的事件，应用期间别处发起的检查更新不记）；同阶段连续的
  进度只留最新一条，日志行只留最近 ``MAX_LOG_EVENTS`` 条，前端按顺序重放即可还原面板。
- 「检查更新」（``check``）照旧同步做完、不登记。
- 不提供停止：与之前一样，开始了就跑到结束。
"""

from __future__ import annotations

import asyncio
import threading
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime

from app.models.schema import (
    MaaFWProjectUpdateData,
    MaaFWProjectUpdateJobData,
    MaaFWProjectUpdateJobResult,
    WSMaaFWProjectUpdateProgressData,
)
from app.task.MaaFW.api_service.common import MaaFWApiReply, maafw_script_config
from app.utils import get_logger

# 与前端更新面板日志框的上限一致（updateProgress.ts 的 MAX_UPDATE_LOG_LINES）。
MAX_LOG_EVENTS = 300
UPDATE_INTERRUPTED = "MFW 项目更新被中断"

_logger = get_logger("MaaFW 项目更新")


@dataclass
class _ManualUpdateJob:
    script_id: str
    started_at: datetime
    task: asyncio.Task[MaaFWApiReply] | None = None
    finished_at: datetime | None = None
    events: list[WSMaaFWProjectUpdateProgressData] = field(default_factory=list)
    log_events: int = 0
    result: MaaFWApiReply | None = None


# 进度回调会从工作线程里来（构建 / 预检 / 登记跑在 to_thread 里），登记表的读写都持这把锁。
_jobs_lock = threading.Lock()
_jobs: dict[str, _ManualUpdateJob] = {}


def _now() -> datetime:
    return datetime.now()


# 当前上下文属于哪一次后台手动更新：只在 _run_apply 里设。同一脚本应用期间别的客户端发起的
# 「检查更新」也推同一种进度事件，不能按脚本 ID 认领，否则检查的终态被存进应用的过程、重放时
# 让后面应用的进度全被忽略。
_current_job: ContextVar[_ManualUpdateJob | None] = ContextVar(
    "maafw_manual_update_job", default=None
)


def current_update_job() -> _ManualUpdateJob | None:
    """本上下文所属的后台手动更新；不在其中（检查更新等）为 ``None``。

    进度出口在事件循环上建好时取一次并自己留着：核心包可能从自己起的线程回调，那里没有
    这份上下文。
    """

    return _current_job.get()


def record_update_progress(
    job: _ManualUpdateJob | None, data: WSMaaFWProjectUpdateProgressData
) -> None:
    """推送一条更新进度前调用：记进 ``job``（这条事件所属的那次手动更新）的过程。

    ``job`` 为 ``None``（只是检查更新）或已结束时什么都不做。可从任意线程调用。
    """

    if job is None:
        return
    with _jobs_lock:
        if job.finished_at is not None:
            return
        _append_event(job, data.model_copy())


def _append_event(
    job: _ManualUpdateJob, data: WSMaaFWProjectUpdateProgressData
) -> None:
    events = job.events
    if data.stage == "log":
        events.append(data)
        job.log_events += 1
        if job.log_events > MAX_LOG_EVENTS:
            for index, event in enumerate(events):
                if event.stage == "log":
                    del events[index]
                    job.log_events -= 1
                    break
        return
    # 下载 / 解压 / 覆盖的进度一秒好几条：与上一条非日志事件同阶段、都不带日志行时
    # 原地换成新的，重放结果不变（这几个阶段的数字只看最新一条）。
    for index in range(len(events) - 1, -1, -1):
        previous = events[index]
        if previous.stage == "log":
            continue
        if previous.stage == data.stage and not previous.log and not data.log:
            events[index] = data
            return
        break
    events.append(data)


async def _run_apply(job: _ManualUpdateJob) -> MaaFWApiReply:
    # 延迟导入：update.py 在模块顶层导入本模块（推送前记事件），避免循环导入。
    from app.task.MaaFW.api_service.update import update_project

    reply: MaaFWApiReply | None = None
    # 任务有自己的上下文副本，这里设的只在这次更新里可见
    _current_job.set(job)
    try:
        reply = await update_project(job.script_id, "apply")
        return reply
    except asyncio.CancelledError:
        reply = MaaFWApiReply.error(500, UPDATE_INTERRUPTED)
        raise
    except Exception as exc:
        _logger.opt(exception=True).warning(
            f"MFW 后台手动更新异常: script={job.script_id} {type(exc).__name__}: {exc}"
        )
        reply = MaaFWApiReply.error(500, f"MFW 项目更新失败: {exc}")
        return reply
    finally:
        with _jobs_lock:
            job.result = reply or MaaFWApiReply.error(500, UPDATE_INTERRUPTED)
            job.finished_at = _now()
        result = job.result
        elapsed = (job.finished_at - job.started_at).total_seconds()
        _logger.info(
            f"MFW 后台手动更新结束: script={job.script_id} code={result.code} "
            f"用时 {elapsed:.1f} 秒 结果: {result.message or ''}"
        )


async def apply_project_update(script_id: str) -> MaaFWApiReply:
    """``/maafw/update`` 的 ``apply``：在后台开始一次手动更新并等它结束。

    同一脚本已有进行中的手动更新时不再起一份，等的就是那一份。请求断开（页面刷新、
    关掉前端）不影响后台的更新，结果留在登记里，由 ``/maafw/update/job`` 取回。
    """

    # 脚本是否有效、能不能更新都由 update_project 判断（原样的 400 / 409），这里不先查一遍：
    # 无效 ID 也只是登记一份「已结束、失败」的结果，与之前同步做完时的响应一致。
    # 查与登记之间没有 await：同一事件循环上并发的两次发起不会都起一份。
    job = _jobs.get(script_id)
    if job is not None and job.finished_at is None and job.task is not None:
        _logger.info(
            f"MFW 手动更新已在进行（{job.started_at.isoformat(timespec='seconds')} 开始），"
            f"接上这一份: script={script_id}"
        )
    else:
        job = _ManualUpdateJob(script_id=script_id, started_at=_now())
        with _jobs_lock:
            _jobs[script_id] = job
        job.task = asyncio.create_task(
            _run_apply(job), name=f"maafw-manual-update-{script_id}"
        )
        _logger.info(f"MFW 手动更新在后台开始: script={script_id}")
    # shield：请求被取消（客户端断开）时只取消这次等待，后台更新照常跑完。
    return await asyncio.shield(job.task)


async def run_project_update(script_id: str, action: str) -> MaaFWApiReply:
    """``/maafw/update``：``check`` 照旧同步做完，``apply`` 走后台登记。"""

    if action == "apply":
        return await apply_project_update(script_id)
    from app.task.MaaFW.api_service.update import update_project

    return await update_project(script_id, action)


def _job_data(job: _ManualUpdateJob) -> MaaFWProjectUpdateJobData:
    with _jobs_lock:
        finished_at = job.finished_at
        events = list(job.events)
        result = job.result
    job_result = None
    if finished_at is not None and result is not None:
        data = result.data if isinstance(result.data, MaaFWProjectUpdateData) else None
        job_result = MaaFWProjectUpdateJobResult(
            code=result.code, message=result.message or "", data=data
        )
    return MaaFWProjectUpdateJobData(
        state="running" if finished_at is None else "finished",
        startedAt=job.started_at.isoformat(timespec="seconds"),
        finishedAt=(finished_at.isoformat(timespec="seconds") if finished_at else None),
        events=events,
        result=job_result,
    )


async def project_update_job(script_id: str, *, wait: bool = False) -> MaaFWApiReply:
    """``/maafw/update/job``：该脚本当前或最近一次手动更新的过程快照与结果。

    ``wait`` 为真且正在更新时等它结束再返回（请求断开不影响更新）。页面刷新后先不等、
    取一次快照还原面板，再带 ``wait`` 等结果。
    """

    try:
        maafw_script_config(script_id)
    except (KeyError, ValueError, TypeError) as exc:
        return MaaFWApiReply.error(400, f"MFW 脚本无效: {exc}")

    job = _jobs.get(script_id)
    if job is None:
        return MaaFWApiReply(data=MaaFWProjectUpdateJobData())
    if wait and job.finished_at is None and job.task is not None:
        _logger.info(f"等待进行中的 MFW 手动更新结束: script={script_id}")
        await asyncio.shield(job.task)
    return MaaFWApiReply(data=_job_data(job))
