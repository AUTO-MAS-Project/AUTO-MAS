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


from fastapi import APIRouter, Body

from app.core import Config
from app.models.common_contract import (
    OutBase,
    project_model,
    project_model_list,
    project_model_map,
)
from app.models.queue_contract import (
    QueueRead,
    QueueCreateOut,
    QueueDeleteIn,
    QueueGetIn,
    QueueGetOut,
    QueueIndexItem,
    QueueItemRead,
    QueueItemCreateOut,
    QueueItemDeleteIn,
    QueueItemGetIn,
    QueueItemGetOut,
    QueueItemIndexItem,
    QueueItemReorderIn,
    QueueItemUpdateIn,
    QueueReorderIn,
    QueueSetInBase,
    QueueUpdateIn,
    TimeSetRead,
    TimeSetCreateOut,
    TimeSetDeleteIn,
    TimeSetGetIn,
    TimeSetGetOut,
    TimeSetIndexItem,
    TimeSetReorderIn,
    TimeSetUpdateIn,
)
from app.api.ws_command import ws_command

router = APIRouter(prefix="/api/queue", tags=["调度队列管理"])


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
        uid, config = await Config.add_queue()
        data = project_model(QueueRead, await config.toDict())
    except Exception as e:
        return QueueCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            queueId="",
            data=QueueRead(),
        )
    return QueueCreateOut(queueId=str(uid), data=data)


@ws_command("queue.get")
@router.post(
    "/get",
    tags=["Get"],
    summary="查询调度队列配置信息",
    response_model=QueueGetOut,
    status_code=200,
)
async def get_queues(queue: QueueGetIn = Body(...)) -> QueueGetOut:
    try:
        index, config = await Config.get_queue(queue.queueId)
        index = project_model_list(QueueIndexItem, index)
        data = project_model_map(QueueRead, config)
    except Exception as e:
        return QueueGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            index=[],
            data={},
        )
    return QueueGetOut(index=index, data=data)


@router.post(
    "/update",
    tags=["Update"],
    summary="更新调度队列配置信息",
    response_model=OutBase,
    status_code=200,
)
async def update_queue(queue: QueueUpdateIn = Body(...)) -> OutBase:
    try:
        await Config.update_queue(
            queue.queueId, queue.data.model_dump(exclude_unset=True)
        )
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
async def delete_queue(queue: QueueDeleteIn = Body(...)) -> OutBase:
    try:
        await Config.del_queue(queue.queueId)
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
async def reorder_queue(script: QueueReorderIn = Body(...)) -> OutBase:
    try:
        await Config.reorder_queue(script.indexList)
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/time/get",
    tags=["Get"],
    summary="查询定时项",
    response_model=TimeSetGetOut,
    status_code=200,
)
async def get_time_set(time: TimeSetGetIn = Body(...)) -> TimeSetGetOut:
    try:
        index, data = await Config.get_time_set(time.queueId, time.timeSetId)
        index = project_model_list(TimeSetIndexItem, index)
        data = project_model_map(TimeSetRead, data)
    except Exception as e:
        return TimeSetGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            index=[],
            data={},
        )
    return TimeSetGetOut(index=index, data=data)


@router.post(
    "/time/add",
    tags=["Add"],
    summary="添加定时项",
    response_model=TimeSetCreateOut,
    status_code=200,
)
async def add_time_set(time: QueueSetInBase = Body(...)) -> TimeSetCreateOut:
    uid, config = await Config.add_time_set(time.queueId)
    data = project_model(TimeSetRead, await config.toDict())
    return TimeSetCreateOut(timeSetId=str(uid), data=data)


@router.post(
    "/time/update",
    tags=["Update"],
    summary="更新定时项",
    response_model=OutBase,
    status_code=200,
)
async def update_time_set(time: TimeSetUpdateIn = Body(...)) -> OutBase:
    try:
        await Config.update_time_set(
            time.queueId, time.timeSetId, time.data.model_dump(exclude_unset=True)
        )
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
async def delete_time_set(time: TimeSetDeleteIn = Body(...)) -> OutBase:
    try:
        await Config.del_time_set(time.queueId, time.timeSetId)
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
async def reorder_time_set(time: TimeSetReorderIn = Body(...)) -> OutBase:
    try:
        await Config.reorder_time_set(time.queueId, time.indexList)
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/item/get",
    tags=["Get"],
    summary="查询队列项",
    response_model=QueueItemGetOut,
    status_code=200,
)
async def get_item(item: QueueItemGetIn = Body(...)) -> QueueItemGetOut:
    try:
        index, data = await Config.get_queue_item(item.queueId, item.queueItemId)
        index = project_model_list(QueueItemIndexItem, index)
        data = project_model_map(QueueItemRead, data)
    except Exception as e:
        return QueueItemGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            index=[],
            data={},
        )
    return QueueItemGetOut(index=index, data=data)


@router.post(
    "/item/add",
    tags=["Add"],
    summary="添加队列项",
    response_model=QueueItemCreateOut,
    status_code=200,
)
async def add_item(item: QueueSetInBase = Body(...)) -> QueueItemCreateOut:
    uid, config = await Config.add_queue_item(item.queueId)
    data = project_model(QueueItemRead, await config.toDict())
    return QueueItemCreateOut(queueItemId=str(uid), data=data)


@router.post(
    "/item/update",
    tags=["Update"],
    summary="更新队列项",
    response_model=OutBase,
    status_code=200,
)
async def update_item(item: QueueItemUpdateIn = Body(...)) -> OutBase:
    try:
        await Config.update_queue_item(
            item.queueId, item.queueItemId, item.data.model_dump(exclude_unset=True)
        )
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
async def delete_item(item: QueueItemDeleteIn = Body(...)) -> OutBase:
    try:
        await Config.del_queue_item(item.queueId, item.queueItemId)
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
async def reorder_item(item: QueueItemReorderIn = Body(...)) -> OutBase:
    try:
        await Config.reorder_queue_item(item.queueId, item.indexList)
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()
