#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


from ipaddress import ip_address
from typing import Annotated
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Body, Query, Request, Response
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.core import Power, TaskManager
from app.models.log_flow import (
    MAX_NODE_ATTRIBUTE_TEXT,
    CloseReason,
    InvalidObservationCursor,
    Node,
    ObservationCursor,
)
from app.models.schema import (
    OutBase,
    PowerCountdownSnapshot,
    TaskRuntimeSnapshot,
    TaskSelectionNode,
    TaskStatusOut,
    TaskTreeData,
)
from app.models.task import TaskMode
from app.utils import get_logger
from app.utils.common.security import is_sensitive_log_key, sanitize_log_message
from app.utils.contracts.power import PowerSignal


class DispatchIn(BaseModel):
    taskId: str = Field(
        ...,
        description="目标任务ID, 设置类任务可选对应托管ID或账号ID, 代理类任务可选对应队列ID或托管ID",
    )


class TaskCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: TaskMode
    tasks: dict[int, TaskSelectionNode] = Field(
        ...,
        min_length=1,
        max_length=1,
        description="单入口任务要求树，顶层仅包含索引 0",
    )

    @field_validator("tasks", mode="before")
    @classmethod
    def validate_indices(cls, value):
        return TaskSelectionNode.validate_indices(value)


class TaskGetIn(BaseModel):
    taskId: str | None = None


class TaskIndexItem(BaseModel):
    uid: str


class TaskGetOut(OutBase):
    index: list[TaskIndexItem] = Field(default_factory=list)
    # Config 框架在运行时生成完整树的契约类，静态检查器无法把工厂结果作为类型。
    data: dict[str, TaskTreeData] = Field(default_factory=dict)  # type: ignore[valid-type]  # pyright: ignore[reportInvalidTypeForm]


class TaskCreateOut(OutBase):
    taskId: str = Field(..., description="新创建的任务ID")


class TaskLogCursor(BaseModel):
    sessionId: UUID
    sequence: int = Field(ge=0)


class TaskLogNodesOut(OutBase):
    nodes: tuple[Node, ...] = ()
    cursor: TaskLogCursor | None = None
    hasMore: bool = False
    closeReason: CloseReason | None = None


class PowerIn(BaseModel):
    signal: PowerSignal = Field(..., description="电源操作信号")


class PowerOut(OutBase):
    signal: PowerSignal = Field(..., description="电源操作信号")


router = APIRouter(prefix="/api/dispatch", tags=["任务调度"])
logger = get_logger("任务调度 API")


@router.get(
    "/runtime-snapshot",
    tags=["Get"],
    summary="获取运行中任务初始快照",
    response_model=TaskRuntimeSnapshot,
    status_code=200,
)
async def get_task_runtime_snapshot() -> TaskRuntimeSnapshot:
    """返回当前运行任务；WS 只承载后续状态、日志与完成事件。"""

    return TaskManager.get_runtime_snapshot()


@router.get(
    "/task/{task_id}",
    tags=["Get"],
    summary="按 taskId 查询单个任务状态",
    response_model=TaskStatusOut,
    status_code=200,
)
async def get_task_status(task_id: str) -> TaskStatusOut:
    """返回运行中或最近完成任务的终态；不包含日志。"""

    result = TaskManager.get_task_status(task_id)
    if result is None:
        return TaskStatusOut(
            code=404,
            status="error",
            message=f"任务 {task_id} 既不在运行中, 也不在最近完成的记录里",
            taskId=task_id,
        )
    return result


def _loopback_host(host: str | None) -> bool:
    if host == "localhost":
        return True
    try:
        return ip_address(host or "").is_loopback
    except ValueError:
        return False


def _local_node_reader(request: Request) -> bool:
    if (
        request.client is None
        or not _loopback_host(request.client.host)
        or not _loopback_host(request.url.hostname)
    ):
        return False
    origin = request.headers.get("origin")
    if origin is None:
        return True
    try:
        source = urlsplit(origin)
        return source.scheme in ("http", "https") and _loopback_host(source.hostname)
    except ValueError:
        return False


@router.get(
    "/task/{task_id}/runs/{script_run_id}/log-nodes",
    tags=["Get"],
    summary="按运行分支查询已采集的日志节点",
    response_model=TaskLogNodesOut,
    responses={
        403: {"model": TaskLogNodesOut},
        404: {"model": TaskLogNodesOut},
        409: {"model": TaskLogNodesOut},
    },
)
async def get_task_log_nodes(
    task_id: UUID,
    script_run_id: UUID,
    request: Request,
    response: Response,
    userRunId: UUID | None = None,
    sessionId: UUID | None = None,
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> TaskLogNodesOut:
    """首次省略游标；后续传入返回的 sessionId 和 sequence（after）。"""
    response.headers["Cache-Control"] = "no-store"
    if not _local_node_reader(request):
        response.status_code = 403
        return TaskLogNodesOut(code=403, status="error", message="日志节点仅限本机读取")
    observation = TaskManager.get_node_observation(
        task_id, script_run_id, user_run_id=userRunId
    )
    if observation is None:
        response.status_code = 404
        return TaskLogNodesOut(
            code=404, status="error", message="该运行没有可读取的日志节点会话"
        )
    try:
        if sessionId is None and after:
            raise InvalidObservationCursor("缺少会话 ID")
        cursor = ObservationCursor(sessionId, after) if sessionId is not None else None
        page = observation.read(after=cursor, limit=limit)
    except InvalidObservationCursor:
        response.status_code = 409
        return TaskLogNodesOut(
            code=409, status="error", message="游标已失效，请从头读取"
        )
    return TaskLogNodesOut(
        nodes=tuple(_public_log_node(node) for node in page.nodes),
        cursor=TaskLogCursor(
            sessionId=page.cursor.session_id, sequence=page.cursor.sequence
        ),
        hasMore=page.has_more,
        closeReason=page.close_reason,
    )


def _public_log_node(node: Node) -> Node:
    attributes = []
    for attribute in node.attributes:
        if is_sensitive_log_key(attribute.key):
            continue
        value = attribute.value
        if isinstance(value, str):
            attribute = attribute.model_copy(
                update={"value": sanitize_log_message(value)[:MAX_NODE_ATTRIBUTE_TEXT]}
            )
        attributes.append(attribute)
    return node.model_copy(
        update={
            "text": sanitize_log_message(node.text),
            "attributes": tuple(attributes),
        }
    )


@router.post("/get", tags=["Get"], response_model=TaskGetOut)
async def get_tasks(body: TaskGetIn = Body(...)) -> TaskGetOut:
    ids = [body.taskId] if body.taskId else [str(uid) for uid in TaskManager.task_info]
    try:
        data = {
            uid: tree for uid in ids if (tree := TaskManager.get_task(uid)) is not None
        }
    except ValueError:
        return TaskGetOut(code=400, status="error", message="任务 ID 格式错误")
    if body.taskId and not data:
        return TaskGetOut(code=404, status="error", message="任务不存在")
    return TaskGetOut(index=[TaskIndexItem(uid=uid) for uid in data], data=data)


@router.get(
    "/power/countdown-snapshot",
    tags=["Get"],
    summary="获取电源倒计时初始快照",
    response_model=PowerCountdownSnapshot,
    status_code=200,
)
async def get_power_countdown_snapshot() -> PowerCountdownSnapshot:
    """返回当前倒计时；WS 只承载后续逐秒更新与取消事件。"""

    return Power.get_power_countdown_snapshot()


@router.post(
    "/start",
    tags=["Action"],
    summary="添加任务",
    response_model=TaskCreateOut,
    status_code=200,
)
async def add_task(task: TaskCreateIn = Body(...)) -> TaskCreateOut:

    try:
        task_id = await TaskManager.start(task.mode, task.tasks)
    except RuntimeError as error:
        return TaskCreateOut(code=409, status="error", message=str(error), taskId="")
    except Exception as e:
        logger.opt(exception=True).warning(f"add_task失败: {type(e).__name__}: {e}")
        return TaskCreateOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}", taskId=""
        )
    return TaskCreateOut(taskId=str(task_id))


@router.post(
    "/stop",
    tags=["Action"],
    summary="中止任务",
    response_model=OutBase,
    status_code=200,
)
async def stop_task(task: DispatchIn = Body(...)) -> OutBase:

    try:
        await TaskManager.stop_task(task.taskId)
    except Exception as e:
        logger.opt(exception=True).warning(f"stop_task失败: {type(e).__name__}: {e}")
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/get/power",
    tags=["Get"],
    summary="获取电源标志",
    response_model=PowerOut,
    status_code=200,
)
async def get_power() -> PowerOut:

    try:
        # 电源任务启动后标志已清空, 等待期间要回报任务实际待执行的操作
        signal = Power.current_power_operation or Power.signal
    except Exception as e:
        logger.opt(exception=True).warning(f"get_power失败: {type(e).__name__}: {e}")
        return PowerOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            signal=PowerSignal.NO_ACTION,
        )
    return PowerOut.model_validate({"signal": signal})


@router.post(
    "/set/power",
    tags=["Action"],
    summary="设置电源标志",
    response_model=OutBase,
    status_code=200,
)
async def set_power(task: PowerIn = Body(...)) -> OutBase:

    try:
        if not await Power.set_signal(task.signal, overwrite=True):
            return OutBase(
                code=409, status="error", message="已有电源任务，未覆盖当前操作"
            )
    except Exception as e:
        logger.opt(exception=True).warning(f"set_power失败: {type(e).__name__}: {e}")
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/cancel/power",
    tags=["Action"],
    summary="取消电源任务",
    response_model=OutBase,
    status_code=200,
)
async def cancel_power_task() -> OutBase:

    try:
        await Power.cancel_power_task()
    except Exception as e:
        logger.opt(exception=True).warning(
            f"cancel_power_task失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()
