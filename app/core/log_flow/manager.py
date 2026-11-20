"""MAS 运行节点与独立采集会话接线。"""

import asyncio

from app.models.task import TaskScriptItem, TaskUserItem
from app.utils.common.log_flow.contracts import PipelineSpec
from app.utils.common.log_flow.session import LogFlowSession, SessionOpenError


async def open_for_run(
    run: TaskScriptItem | TaskUserItem, config: PipelineSpec, *, timeout: float = 5.0
) -> LogFlowSession:
    """执行层传入实际运行对象；日志来源不能指定任务或账号身份。"""
    observation = run.open_node_observation()
    try:
        return await LogFlowSession.open(
            config, timeout=timeout, observation=observation
        )
    except asyncio.CancelledError:
        observation.finish("worker_error", "采集启动已取消")
        raise
    except SessionOpenError as exc:
        observation.finish("worker_error", str(exc))
        raise
