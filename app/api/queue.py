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


from typing import Annotated

from fastapi import APIRouter, Body, Path

from app.api.common import bind_api
from app.core import Config
from app.contracts.common_contract import (
    IndexOrderPatch,
    OutBase,
    project_model,
    project_model_list,
    project_model_map,
)
from app.contracts.queue_contract import (
    QueueCreateOut,
    QueueDetailOut,
    QueueGetOut,
    QueueIndexItem,
    QueueItemCreateOut,
    QueueItemDetailOut,
    QueueItemGetOut,
    QueueItemIndexItem,
    QueueItemPatch,
    QueueItemRead,
    QueuePatch,
    QueueRead,
    TimeSetCreateOut,
    TimeSetDetailOut,
    TimeSetGetOut,
    TimeSetIndexItem,
    TimeSetPatch,
    TimeSetRead,
)

router = APIRouter(prefix="/api/queue", tags=["调度队列管理"])
api = bind_api(router)

QueueIdPath = Annotated[str, Path(description="队列 ID")]
TimeSetIdPath = Annotated[str, Path(description="时间设置 ID")]
QueueItemIdPath = Annotated[str, Path(description="队列项 ID")]


async def _build_queue_collection_out() -> QueueGetOut:
    index, data = await Config.get_queue(None)
    return QueueGetOut(
        index=project_model_list(QueueIndexItem, index),
        data=project_model_map(QueueRead, data),
    )


async def _build_queue_detail_out(queue_id: str) -> QueueDetailOut:
    _, data = await Config.get_queue(queue_id)
    projected = project_model_map(QueueRead, data)
    return QueueDetailOut(data=projected[queue_id])


async def _build_queue_create_out() -> QueueCreateOut:
    uid, config = await Config.add_queue()
    return QueueCreateOut(
        id=str(uid),
        data=project_model(QueueRead, await config.toDict()),
    )


async def _update_queue_config(queue_id: str, data: QueuePatch) -> OutBase:
    await Config.update_queue(queue_id, data.model_dump(exclude_unset=True))
    return OutBase()


async def _delete_queue_config(queue_id: str) -> OutBase:
    await Config.del_queue(queue_id)
    return OutBase()


async def _build_time_set_collection_out(queue_id: str) -> TimeSetGetOut:
    index, data = await Config.get_time_set(queue_id, None)
    return TimeSetGetOut(
        index=project_model_list(TimeSetIndexItem, index),
        data=project_model_map(TimeSetRead, data),
    )


async def _build_time_set_detail_out(
    queue_id: str, time_set_id: str
) -> TimeSetDetailOut:
    _, data = await Config.get_time_set(queue_id, time_set_id)
    projected = project_model_map(TimeSetRead, data)
    return TimeSetDetailOut(data=projected[time_set_id])


async def _build_time_set_create_out(queue_id: str) -> TimeSetCreateOut:
    uid, config = await Config.add_time_set(queue_id)
    return TimeSetCreateOut(
        id=str(uid),
        data=project_model(TimeSetRead, await config.toDict()),
    )


async def _update_time_set_config(
    queue_id: str, time_set_id: str, data: TimeSetPatch
) -> OutBase:
    await Config.update_time_set(
        queue_id, time_set_id, data.model_dump(exclude_unset=True)
    )
    return OutBase()


async def _delete_time_set_config(queue_id: str, time_set_id: str) -> OutBase:
    await Config.del_time_set(queue_id, time_set_id)
    return OutBase()


async def _build_queue_item_collection_out(queue_id: str) -> QueueItemGetOut:
    index, data = await Config.get_queue_item(queue_id, None)
    return QueueItemGetOut(
        index=project_model_list(QueueItemIndexItem, index),
        data=project_model_map(QueueItemRead, data),
    )


async def _build_queue_item_detail_out(
    queue_id: str, queue_item_id: str
) -> QueueItemDetailOut:
    _, data = await Config.get_queue_item(queue_id, queue_item_id)
    projected = project_model_map(QueueItemRead, data)
    return QueueItemDetailOut(data=projected[queue_item_id])


async def _build_queue_item_create_out(queue_id: str) -> QueueItemCreateOut:
    uid, config = await Config.add_queue_item(queue_id)
    return QueueItemCreateOut(
        id=str(uid),
        data=project_model(QueueItemRead, await config.toDict()),
    )


async def _update_queue_item_config(
    queue_id: str, queue_item_id: str, data: QueueItemPatch
) -> OutBase:
    await Config.update_queue_item(
        queue_id, queue_item_id, data.model_dump(exclude_unset=True)
    )
    return OutBase()


async def _delete_queue_item_config(queue_id: str, queue_item_id: str) -> OutBase:
    await Config.del_queue_item(queue_id, queue_item_id)
    return OutBase()


@api.get(
    "",
    tags=["Get"],
    summary="查询全部调度队列",
    response_model=QueueGetOut,
    index=[],
    data={},
)
async def list_queues() -> QueueGetOut:
    return await _build_queue_collection_out()


@api.post(
    "",
    ws_endpoint="queue.add",
    tags=["Add"],
    summary="创建调度队列",
    response_model=QueueCreateOut,
    id="",
    data=QueueRead(),
)
async def create_queue() -> QueueCreateOut:
    return await _build_queue_create_out()


@api.patch(
    "/order",
    tags=["Update"],
    summary="重新排序调度队列",
    response_model=OutBase,
)
async def reorder_queue(body: IndexOrderPatch = Body(...)) -> OutBase:
    await Config.reorder_queue(body.index_list)
    return OutBase()


@api.get(
    "/{queue_id}",
    ws_endpoint="queue.get",
    tags=["Get"],
    summary="查询单个调度队列",
    response_model=QueueDetailOut,
    data=QueueRead(),
)
async def get_queue(queue_id: QueueIdPath) -> QueueDetailOut:
    return await _build_queue_detail_out(queue_id)


@api.patch(
    "/{queue_id}",
    tags=["Update"],
    summary="更新调度队列",
    response_model=OutBase,
)
async def update_queue(queue_id: QueueIdPath, data: QueuePatch = Body(...)) -> OutBase:
    return await _update_queue_config(queue_id, data)


@api.delete(
    "/{queue_id}",
    tags=["Delete"],
    summary="删除调度队列",
    response_model=OutBase,
)
async def delete_queue(queue_id: QueueIdPath) -> OutBase:
    return await _delete_queue_config(queue_id)


@api.get(
    "/{queue_id}/times",
    tags=["Get"],
    summary="查询队列下的全部定时项",
    response_model=TimeSetGetOut,
    index=[],
    data={},
)
async def list_time_sets(queue_id: QueueIdPath) -> TimeSetGetOut:
    return await _build_time_set_collection_out(queue_id)


@api.post(
    "/{queue_id}/times",
    tags=["Add"],
    summary="创建定时项",
    response_model=TimeSetCreateOut,
    id="",
    data=TimeSetRead(),
)
async def create_time_set(queue_id: QueueIdPath) -> TimeSetCreateOut:
    return await _build_time_set_create_out(queue_id)


@api.patch(
    "/{queue_id}/times/order",
    tags=["Update"],
    summary="重新排序定时项",
    response_model=OutBase,
)
async def reorder_time_sets(
    queue_id: QueueIdPath, body: IndexOrderPatch = Body(...)
) -> OutBase:
    await Config.reorder_time_set(queue_id, body.index_list)
    return OutBase()


@api.get(
    "/{queue_id}/times/{time_set_id}",
    tags=["Get"],
    summary="查询单个定时项",
    response_model=TimeSetDetailOut,
    data=TimeSetRead(),
)
async def get_time_set(
    queue_id: QueueIdPath, time_set_id: TimeSetIdPath
) -> TimeSetDetailOut:
    return await _build_time_set_detail_out(queue_id, time_set_id)


@api.patch(
    "/{queue_id}/times/{time_set_id}",
    tags=["Update"],
    summary="更新定时项",
    response_model=OutBase,
)
async def update_time_set(
    queue_id: QueueIdPath,
    time_set_id: TimeSetIdPath,
    data: TimeSetPatch = Body(...),
) -> OutBase:
    return await _update_time_set_config(queue_id, time_set_id, data)


@api.delete(
    "/{queue_id}/times/{time_set_id}",
    tags=["Delete"],
    summary="删除定时项",
    response_model=OutBase,
)
async def delete_time_set(queue_id: QueueIdPath, time_set_id: TimeSetIdPath) -> OutBase:
    return await _delete_time_set_config(queue_id, time_set_id)


@api.get(
    "/{queue_id}/items",
    tags=["Get"],
    summary="查询队列下的全部队列项",
    response_model=QueueItemGetOut,
    index=[],
    data={},
)
async def list_queue_items(queue_id: QueueIdPath) -> QueueItemGetOut:
    return await _build_queue_item_collection_out(queue_id)


@api.post(
    "/{queue_id}/items",
    tags=["Add"],
    summary="创建队列项",
    response_model=QueueItemCreateOut,
    id="",
    data=QueueItemRead(),
)
async def create_queue_item(queue_id: QueueIdPath) -> QueueItemCreateOut:
    return await _build_queue_item_create_out(queue_id)


@api.patch(
    "/{queue_id}/items/order",
    tags=["Update"],
    summary="重新排序队列项",
    response_model=OutBase,
)
async def reorder_queue_items(
    queue_id: QueueIdPath, body: IndexOrderPatch = Body(...)
) -> OutBase:
    await Config.reorder_queue_item(queue_id, body.index_list)
    return OutBase()


@api.get(
    "/{queue_id}/items/{queue_item_id}",
    tags=["Get"],
    summary="查询单个队列项",
    response_model=QueueItemDetailOut,
    data=QueueItemRead(),
)
async def get_queue_item(
    queue_id: QueueIdPath, queue_item_id: QueueItemIdPath
) -> QueueItemDetailOut:
    return await _build_queue_item_detail_out(queue_id, queue_item_id)


@api.patch(
    "/{queue_id}/items/{queue_item_id}",
    tags=["Update"],
    summary="更新队列项",
    response_model=OutBase,
)
async def update_queue_item(
    queue_id: QueueIdPath,
    queue_item_id: QueueItemIdPath,
    data: QueueItemPatch = Body(...),
) -> OutBase:
    return await _update_queue_item_config(queue_id, queue_item_id, data)


@api.delete(
    "/{queue_id}/items/{queue_item_id}",
    tags=["Delete"],
    summary="删除队列项",
    response_model=OutBase,
)
async def delete_queue_item(
    queue_id: QueueIdPath, queue_item_id: QueueItemIdPath
) -> OutBase:
    return await _delete_queue_item_config(queue_id, queue_item_id)
