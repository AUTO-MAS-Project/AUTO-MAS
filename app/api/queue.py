#   AUTO_MAA:A MAA Multi Account Management and Automation Tool
#   Copyright © 2024-2025 DLmaster361

#   This file is part of AUTO_MAA.

#   AUTO_MAA is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO_MAA is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO_MAA. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


from fastapi import APIRouter, Body

from core import Config
from models.schema import *

router = APIRouter(prefix="/api/queue", tags=["调度队列管理"])


@router.post(
    "/add", summary="添加调度队列", response_model=QueueCreateOut, status_code=200
)
async def add_queue() -> QueueCreateOut:

    uid, config = await Config.add_queue()
    return QueueCreateOut(queueId=str(uid), data=await config.toDict())


@router.post(
    "/get", summary="查询调度队列配置信息", response_model=QueueGetOut, status_code=200
)
async def get_queues(queue: QueueGetIn = Body(...)) -> QueueGetOut:

    try:
        index, data = await Config.get_queue(queue.queueId)
    except Exception as e:
        return QueueGetOut(code=500, status="error", message=str(e), index=[], data={})
    return QueueGetOut(index=index, data=data)


@router.post(
    "/update", summary="更新调度队列配置信息", response_model=OutBase, status_code=200
)
async def update_queue(queue: QueueUpdateIn = Body(...)) -> OutBase:

    try:
        await Config.update_queue(queue.queueId, queue.data)
    except Exception as e:
        return OutBase(code=500, status="error", message=str(e))
    return OutBase()


@router.post("/delete", summary="删除调度队列", response_model=OutBase, status_code=200)
async def delete_queue(queue: QueueDeleteIn = Body(...)) -> OutBase:

    try:
        await Config.del_queue(queue.queueId)
    except Exception as e:
        return OutBase(code=500, status="error", message=str(e))
    return OutBase()


@router.post(
    "/time/add", summary="添加定时项", response_model=TimeSetCreateOut, status_code=200
)
async def add_time_set(time: QueueSetInBase = Body(...)) -> TimeSetCreateOut:

    uid, config = await Config.add_time_set(time.queueId)
    return TimeSetCreateOut(timeSetId=str(uid), data=await config.toDict())


@router.post(
    "/time/update", summary="更新定时项", response_model=OutBase, status_code=200
)
async def update_time_set(time: TimeSetUpdateIn = Body(...)) -> OutBase:

    try:
        await Config.update_time_set(time.queueId, time.timeSetId, time.data)
    except Exception as e:
        return OutBase(code=500, status="error", message=str(e))
    return OutBase()


@router.post(
    "/time/delete", summary="删除定时项", response_model=OutBase, status_code=200
)
async def delete_time_set(time: TimeSetDeleteIn = Body(...)) -> OutBase:

    try:
        await Config.del_time_set(time.queueId, time.timeSetId)
    except Exception as e:
        return OutBase(code=500, status="error", message=str(e))
    return OutBase()


@router.post(
    "/item/add",
    summary="添加队列项",
    response_model=QueueItemCreateOut,
    status_code=200,
)
async def add_item(item: QueueSetInBase = Body(...)) -> QueueItemCreateOut:

    uid, config = await Config.add_queue_item(item.queueId)
    return QueueItemCreateOut(queueItemId=str(uid), data=await config.toDict())


@router.post(
    "/item/update", summary="更新队列项", response_model=OutBase, status_code=200
)
async def update_item(item: QueueItemUpdateIn = Body(...)) -> OutBase:

    try:
        await Config.update_queue_item(item.queueId, item.queueItemId, item.data)
    except Exception as e:
        return OutBase(code=500, status="error", message=str(e))
    return OutBase()


@router.post(
    "/item/delete", summary="删除队列项", response_model=OutBase, status_code=200
)
async def delete_item(item: QueueItemDeleteIn = Body(...)) -> OutBase:

    try:
        await Config.del_queue_item(item.queueId, item.queueItemId)
    except Exception as e:
        return OutBase(code=500, status="error", message=str(e))
    return OutBase()
