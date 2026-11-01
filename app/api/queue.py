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


from typing import (
    Dict,
    List,
    Literal,
    Optional,
)

from fastapi import APIRouter, Body
from pydantic import (
    BaseModel,
    Field,
)

import app.models.config as _config_models
from app.config.wire import ConfigInput, ConfigPayload
from app.core import Commands, Config
from app.core.config.manager import QueueItemNotFoundError, QueueNotFoundError
from app.models.schema import OutBase
from app.utils import get_logger

QueueConfig = ConfigPayload[_config_models.QueueConfig]
QueueConfigInput = ConfigInput[_config_models.QueueConfig]
QueueItem = ConfigPayload[_config_models.QueueItem]
QueueItemInput = ConfigInput[_config_models.QueueItem]
TimeSet = ConfigPayload[_config_models.TimeSet]
TimeSetInput = ConfigInput[_config_models.TimeSet]


class QueueIndexItem(BaseModel):
    uid: str = Field(..., description="唯一标识符")
    type: Literal["QueueConfig"] = Field(..., description="配置类型")


class QueueItemIndexItem(BaseModel):
    uid: str = Field(..., description="唯一标识符")
    type: Literal["QueueItem"] = Field(..., description="配置类型")


class TimeSetIndexItem(BaseModel):
    uid: str = Field(..., description="唯一标识符")
    type: Literal["TimeSet"] = Field(..., description="配置类型")


class QueueCreateOut(OutBase):
    queueId: str = Field(..., description="新创建的队列ID")
    data: QueueConfig = Field(..., description="队列配置数据")


class QueueGetIn(BaseModel):
    queueId: Optional[str] = Field(
        default=None, description="队列ID, 未携带时表示获取所有队列数据"
    )


class QueueGetOut(OutBase):
    index: List[QueueIndexItem] = Field(..., description="队列索引列表")
    data: Dict[str, QueueConfig] = Field(
        ..., description="队列数据字典, key来自于index列表的uid"
    )


class QueueUpdateIn(BaseModel):
    queueId: str = Field(..., description="队列ID")
    data: QueueConfigInput = Field(..., description="队列更新数据")


class QueueDeleteIn(BaseModel):
    queueId: str = Field(..., description="队列ID")


class QueueSetInBase(BaseModel):
    queueId: str = Field(..., description="所属队列ID")


class TimeSetGetIn(QueueSetInBase):
    timeSetId: Optional[str] = Field(
        default=None, description="时间设置ID, 未携带时表示获取所有时间设置数据"
    )


class TimeSetGetOut(OutBase):
    index: List[TimeSetIndexItem] = Field(..., description="时间设置索引列表")
    data: Dict[str, TimeSet] = Field(
        ..., description="时间设置数据字典, key来自于index列表的uid"
    )


class TimeSetCreateOut(OutBase):
    timeSetId: str = Field(..., description="新创建的时间设置ID")
    data: TimeSet = Field(..., description="时间设置配置数据")


class TimeSetUpdateIn(QueueSetInBase):
    timeSetId: str = Field(..., description="时间设置ID")
    data: TimeSetInput = Field(..., description="时间设置更新数据")


class TimeSetDeleteIn(QueueSetInBase):
    timeSetId: str = Field(..., description="时间设置ID")


class TimeSetReorderIn(QueueSetInBase):
    indexList: List[str] = Field(..., description="时间设置ID列表, 按新顺序排列")


class QueueItemGetIn(QueueSetInBase):
    queueItemId: Optional[str] = Field(
        default=None, description="队列项ID, 未携带时表示获取所有队列项数据"
    )


class QueueItemGetOut(OutBase):
    index: List[QueueItemIndexItem] = Field(..., description="队列项索引列表")
    data: Dict[str, QueueItem] = Field(
        ..., description="队列项数据字典, key来自于index列表的uid"
    )


class QueueItemCreateOut(OutBase):
    queueItemId: str = Field(..., description="新创建的队列项ID")
    data: QueueItem = Field(..., description="队列项配置数据")


class QueueItemUpdateIn(QueueSetInBase):
    queueItemId: str = Field(..., description="队列项ID")
    data: QueueItemInput = Field(..., description="队列项更新数据")


class QueueItemDeleteIn(QueueSetInBase):
    queueItemId: str = Field(..., description="队列项ID")


class QueueItemReorderIn(QueueSetInBase):
    indexList: List[str] = Field(..., description="队列项ID列表, 按新顺序排列")


router = APIRouter(prefix="/api/queue", tags=["调度队列管理"])
logger = get_logger("调度队列 API")


@Commands.register("queue.add")
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
        data = QueueConfig(**config.model_dump(context={"audience": "api"}))
    except Exception as e:
        logger.opt(exception=True).warning(f"add_queue失败: {type(e).__name__}: {e}")
        return QueueCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            queueId="",
            data=QueueConfig(**{}),
        )
    return QueueCreateOut(queueId=str(uid), data=data)


@Commands.register("queue.get", params=QueueGetIn)
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
        index = [QueueIndexItem(**_) for _ in index]
        data = {uid: QueueConfig(**cfg) for uid, cfg in config.items()}
    except QueueNotFoundError as e:
        return QueueGetOut(code=404, status="error", message=str(e), index=[], data={})
    except Exception as e:
        logger.opt(exception=True).warning(f"get_queues失败: {type(e).__name__}: {e}")
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
        logger.opt(exception=True).warning(f"update_queue失败: {type(e).__name__}: {e}")
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
        logger.opt(exception=True).warning(f"delete_queue失败: {type(e).__name__}: {e}")
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
        index = [TimeSetIndexItem(**_) for _ in index]
        data = {uid: TimeSet(**cfg) for uid, cfg in data.items()}
    except Exception as e:
        logger.opt(exception=True).warning(f"get_time_set失败: {type(e).__name__}: {e}")
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
    data = TimeSet(**config.model_dump(context={"audience": "api"}))
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
        logger.opt(exception=True).warning(
            f"update_time_set失败: {type(e).__name__}: {e}"
        )
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
        logger.opt(exception=True).warning(
            f"delete_time_set失败: {type(e).__name__}: {e}"
        )
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
        logger.opt(exception=True).warning(
            f"reorder_time_set失败: {type(e).__name__}: {e}"
        )
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
        index = [QueueItemIndexItem(**_) for _ in index]
        data = {uid: QueueItem(**cfg) for uid, cfg in data.items()}
    except (QueueNotFoundError, QueueItemNotFoundError) as e:
        return QueueItemGetOut(
            code=404, status="error", message=str(e), index=[], data={}
        )
    except Exception as e:
        logger.opt(exception=True).warning(f"get_item失败: {type(e).__name__}: {e}")
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

    try:
        uid, config = await Config.add_queue_item(item.queueId)
        data = QueueItem(**config.model_dump(context={"audience": "api"}))
    except Exception as e:
        # 循环运行中的队列会拒绝增删队列项，原因要带回给前端提示
        logger.opt(exception=True).warning(f"add_item失败: {type(e).__name__}: {e}")
        return QueueItemCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            queueItemId="",
            data=QueueItem(**{}),
        )
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
        logger.opt(exception=True).warning(f"update_item失败: {type(e).__name__}: {e}")
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
        logger.opt(exception=True).warning(f"delete_item失败: {type(e).__name__}: {e}")
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
        logger.opt(exception=True).warning(f"reorder_item失败: {type(e).__name__}: {e}")
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()
