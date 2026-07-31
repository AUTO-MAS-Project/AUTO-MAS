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

"""调度队列 API：请求/响应字段基于 ``QueueEntry`` 等，直接操作 ``Config.queues``。"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Body
from pydantic import BaseModel, Field

from app.api.ws_command import ws_command
from app.config import CollectionOrderItem
from app.config.errors import ConfigAggregateError
from app.core import Config
from app.models.config import QueueEntry, QueueItemEntry, TimeSetEntry
from app.models.schema import OutBase

router = APIRouter(prefix="/api/queue", tags=["调度队列管理"])


# ==================== 字段（基于 ConfigEntry） ====================


class QueueCreateOut(OutBase):
    queueId: str = Field(default="", description="新队列 ID")
    data: QueueEntry = Field(default_factory=QueueEntry, description="队列配置")


class QueueGetIn(BaseModel):
    queueId: Optional[str] = Field(
        default=None, description="队列 ID；缺省返回全部"
    )


class QueueGetOut(OutBase):
    order: list[CollectionOrderItem] = Field(
        default_factory=list, description="队列顺序"
    )
    data: dict[str, QueueEntry] = Field(
        default_factory=dict, description="队列数据，key 为 uid"
    )


class QueueUpdateIn(BaseModel):
    queueId: str = Field(..., description="队列 ID")
    data: QueueEntry = Field(..., description="队列补丁（Wire 形状）")


class QueueDeleteIn(BaseModel):
    queueId: str = Field(..., description="队列 ID")


class QueueReorderIn(BaseModel):
    indexList: list[str] = Field(..., description="按新顺序排列的队列 UID 列表")


class QueueSetInBase(BaseModel):
    queueId: str = Field(..., description="所属队列 ID")


class TimeSetGetIn(QueueSetInBase):
    timeSetId: Optional[str] = Field(
        default=None, description="定时项 ID；缺省返回全部"
    )


class TimeSetGetOut(OutBase):
    order: list[CollectionOrderItem] = Field(
        default_factory=list, description="定时项顺序"
    )
    data: dict[str, TimeSetEntry] = Field(
        default_factory=dict, description="定时项数据，key 为 uid"
    )


class TimeSetCreateOut(OutBase):
    timeSetId: str = Field(default="", description="新定时项 ID")
    data: TimeSetEntry = Field(default_factory=TimeSetEntry, description="定时项配置")


class TimeSetUpdateIn(QueueSetInBase):
    timeSetId: str = Field(..., description="定时项 ID")
    data: TimeSetEntry = Field(..., description="定时项补丁（Wire 形状）")


class TimeSetDeleteIn(QueueSetInBase):
    timeSetId: str = Field(..., description="定时项 ID")


class TimeSetReorderIn(QueueSetInBase):
    indexList: list[str] = Field(..., description="按新顺序排列的定时项 UID 列表")


class QueueItemGetIn(QueueSetInBase):
    queueItemId: Optional[str] = Field(
        default=None, description="队列项 ID；缺省返回全部"
    )


class QueueItemGetOut(OutBase):
    order: list[CollectionOrderItem] = Field(
        default_factory=list, description="队列项顺序"
    )
    data: dict[str, QueueItemEntry] = Field(
        default_factory=dict, description="队列项数据，key 为 uid"
    )


class QueueItemCreateOut(OutBase):
    queueItemId: str = Field(default="", description="新队列项 ID")
    data: QueueItemEntry = Field(
        default_factory=QueueItemEntry, description="队列项配置"
    )


class QueueItemUpdateIn(QueueSetInBase):
    queueItemId: str = Field(..., description="队列项 ID")
    data: QueueItemEntry = Field(..., description="队列项补丁（Wire 形状）")


class QueueItemDeleteIn(QueueSetInBase):
    queueItemId: str = Field(..., description="队列项 ID")


class QueueItemReorderIn(QueueSetInBase):
    indexList: list[str] = Field(..., description="按新顺序排列的队列项 UID 列表")


# ==================== 队列 ====================


@ws_command("queue.add")
@router.post(
    "/add",
    tags=["Add"],
    summary="添加调度队列",
    response_model=QueueCreateOut,
    status_code=200,
)
async def add_queue() -> QueueCreateOut:
    try:
        col = Config.queues
        uid = col.add(QueueEntry)
        await col.commit()
        return QueueCreateOut(queueId=str(uid), data=col[uid])
    except Exception as e:
        return QueueCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            queueId="",
            data=QueueEntry(),
        )


@ws_command("queue.get", params=QueueGetIn)
@router.post(
    "/get",
    tags=["Get"],
    summary="查询调度队列配置信息",
    response_model=QueueGetOut,
    status_code=200,
)
async def get_queues(body: QueueGetIn = Body(...)) -> QueueGetOut:
    try:
        col = Config.queues
        uids = [UUID(body.queueId)] if body.queueId else list(col.keys())
        return QueueGetOut(
            order=[
                CollectionOrderItem(uid=uid, type=type(col[uid]).__name__)
                for uid in uids
            ],
            data={str(uid): col[uid] for uid in uids},
        )
    except Exception as e:
        return QueueGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            order=[],
            data={},
        )


@router.post(
    "/update",
    tags=["Update"],
    summary="更新调度队列配置信息",
    response_model=OutBase,
    status_code=200,
)
async def update_queue(body: QueueUpdateIn = Body(...)) -> OutBase:
    try:
        await Config.queues[UUID(body.queueId)].update(body.data)
    except ConfigAggregateError as e:
        return OutBase(code=500, status="error", message=str(e))
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/delete",
    tags=["Delete"],
    summary="删除调度队列",
    response_model=OutBase,
    status_code=200,
)
async def delete_queue(body: QueueDeleteIn = Body(...)) -> OutBase:
    try:
        col = Config.queues
        col.remove(body.queueId)
        await col.commit()
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/order",
    tags=["Update"],
    summary="重新排序",
    response_model=OutBase,
    status_code=200,
)
async def reorder_queue(body: QueueReorderIn = Body(...)) -> OutBase:
    try:
        col = Config.queues
        col.set_order(list(map(UUID, body.indexList)))
        await col.commit()
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


# ==================== 定时项 ====================


@router.post(
    "/time/get",
    tags=["Get"],
    summary="查询定时项",
    response_model=TimeSetGetOut,
    status_code=200,
)
async def get_time_set(body: TimeSetGetIn = Body(...)) -> TimeSetGetOut:
    try:
        col = Config.queues[UUID(body.queueId)].time_sets
        uids = [UUID(body.timeSetId)] if body.timeSetId else list(col.keys())
        return TimeSetGetOut(
            order=[
                CollectionOrderItem(uid=uid, type=type(col[uid]).__name__)
                for uid in uids
            ],
            data={str(uid): col[uid] for uid in uids},
        )
    except Exception as e:
        return TimeSetGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            order=[],
            data={},
        )


@router.post(
    "/time/add",
    tags=["Add"],
    summary="添加定时项",
    response_model=TimeSetCreateOut,
    status_code=200,
)
async def add_time_set(body: QueueSetInBase = Body(...)) -> TimeSetCreateOut:
    try:
        col = Config.queues[UUID(body.queueId)].time_sets
        uid = col.add(TimeSetEntry)
        await col.commit()
        return TimeSetCreateOut(timeSetId=str(uid), data=col[uid])
    except Exception as e:
        return TimeSetCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            timeSetId="",
            data=TimeSetEntry(),
        )


@router.post(
    "/time/update",
    tags=["Update"],
    summary="更新定时项",
    response_model=OutBase,
    status_code=200,
)
async def update_time_set(body: TimeSetUpdateIn = Body(...)) -> OutBase:
    try:
        await Config.queues[UUID(body.queueId)].time_sets[UUID(body.timeSetId)].update(
            body.data
        )
    except ConfigAggregateError as e:
        return OutBase(code=500, status="error", message=str(e))
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/time/delete",
    tags=["Delete"],
    summary="删除定时项",
    response_model=OutBase,
    status_code=200,
)
async def delete_time_set(body: TimeSetDeleteIn = Body(...)) -> OutBase:
    try:
        col = Config.queues[UUID(body.queueId)].time_sets
        col.remove(body.timeSetId)
        await col.commit()
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/time/order",
    tags=["Update"],
    summary="重新排序定时项",
    response_model=OutBase,
    status_code=200,
)
async def reorder_time_set(body: TimeSetReorderIn = Body(...)) -> OutBase:
    try:
        col = Config.queues[UUID(body.queueId)].time_sets
        col.set_order(list(map(UUID, body.indexList)))
        await col.commit()
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


# ==================== 队列项 ====================


@router.post(
    "/item/get",
    tags=["Get"],
    summary="查询队列项",
    response_model=QueueItemGetOut,
    status_code=200,
)
async def get_item(body: QueueItemGetIn = Body(...)) -> QueueItemGetOut:
    try:
        col = Config.queues[UUID(body.queueId)].items
        uids = [UUID(body.queueItemId)] if body.queueItemId else list(col.keys())
        return QueueItemGetOut(
            order=[
                CollectionOrderItem(uid=uid, type=type(col[uid]).__name__)
                for uid in uids
            ],
            data={str(uid): col[uid] for uid in uids},
        )
    except Exception as e:
        return QueueItemGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            order=[],
            data={},
        )


@router.post(
    "/item/add",
    tags=["Add"],
    summary="添加队列项",
    response_model=QueueItemCreateOut,
    status_code=200,
)
async def add_item(body: QueueSetInBase = Body(...)) -> QueueItemCreateOut:
    try:
        col = Config.queues[UUID(body.queueId)].items
        uid = col.add(QueueItemEntry)
        await col.commit()
        return QueueItemCreateOut(queueItemId=str(uid), data=col[uid])
    except Exception as e:
        return QueueItemCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            queueItemId="",
            data=QueueItemEntry(),
        )


@router.post(
    "/item/update",
    tags=["Update"],
    summary="更新队列项",
    response_model=OutBase,
    status_code=200,
)
async def update_item(body: QueueItemUpdateIn = Body(...)) -> OutBase:
    try:
        await Config.queues[UUID(body.queueId)].items[UUID(body.queueItemId)].update(
            body.data
        )
    except ConfigAggregateError as e:
        return OutBase(code=500, status="error", message=str(e))
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/item/delete",
    tags=["Delete"],
    summary="删除队列项",
    response_model=OutBase,
    status_code=200,
)
async def delete_item(body: QueueItemDeleteIn = Body(...)) -> OutBase:
    try:
        col = Config.queues[UUID(body.queueId)].items
        col.remove(body.queueItemId)
        await col.commit()
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/item/order",
    tags=["Update"],
    summary="重新排序队列项",
    response_model=OutBase,
    status_code=200,
)
async def reorder_item(body: QueueItemReorderIn = Body(...)) -> OutBase:
    try:
        col = Config.queues[UUID(body.queueId)].items
        col.set_order(list(map(UUID, body.indexList)))
        await col.commit()
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()
