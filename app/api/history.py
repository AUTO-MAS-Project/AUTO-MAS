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


from datetime import date
from mimetypes import guess_type
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Body
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, model_validator

from app.core import History
from app.core.history import HistoryNotFoundError, HistoryStorageError
from app.models.schema import HistoryBucket, HistoryDetail, OutBase
from app.utils import get_logger


class HistorySearchIn(BaseModel):
    mode: Literal["DAILY", "WEEKLY", "MONTHLY"] = Field(..., description="合并模式")
    start_date: date = Field(..., description="开始日期，包含当天")
    end_date: date = Field(..., description="结束日期，包含当天")

    @model_validator(mode="after")
    def check_dates(self):
        if self.start_date > self.end_date:
            raise ValueError("开始日期不得晚于结束日期")
        return self


class HistorySearchOut(OutBase):
    data: dict[str, dict[str, HistoryBucket]] = Field(
        ..., description="日期 → 用户名 → 记录与统计"
    )


class HistoryDetailGetIn(BaseModel):
    recordId: UUID = Field(..., description="历史记录编号")


class HistoryDetailGetOut(OutBase):
    data: HistoryDetail


router = APIRouter(prefix="/api/history", tags=["历史记录"])
logger = get_logger("历史记录 API")


def _storage_error(error: HistoryStorageError) -> JSONResponse:
    status = 404 if isinstance(error, HistoryNotFoundError) else 503
    logger.opt(exception=error).warning(f"历史查询失败：{error}")
    return JSONResponse(
        status_code=status,
        content=OutBase(code=status, status="error", message=str(error)).model_dump(),
    )


@router.post(
    "/search",
    tags=["Get"],
    summary="搜索历史记录及类型化统计",
    operation_id="search_history_api_history_search_post",
    response_model=HistorySearchOut,
)
async def search_history(history: HistorySearchIn) -> HistorySearchOut | JSONResponse:
    try:
        data = await History.search(
            start_date=history.start_date, end_date=history.end_date, mode=history.mode
        )
        return HistorySearchOut(data=data)
    except HistoryStorageError as error:
        return _storage_error(error)


@router.post(
    "/detail",
    tags=["Get"],
    summary="按记录编号获取执行结果、日志和附件",
    operation_id="get_history_detail_api_history_detail_post",
    response_model=HistoryDetailGetOut,
)
async def get_history_detail(
    history: HistoryDetailGetIn = Body(...),
) -> HistoryDetailGetOut | JSONResponse:
    try:
        return HistoryDetailGetOut(
            data=await History.get_detail(record_id=history.recordId)
        )
    except HistoryStorageError as error:
        return _storage_error(error)


@router.get(
    "/attachments/{attachment_id}",
    tags=["Get"],
    summary="按附件编号读取图片、文件或视频",
    operation_id="get_history_attachment_api_history_attachments__attachment_id__get",
    response_model=None,
)
async def get_history_attachment(
    attachment_id: UUID, download: bool = False
) -> FileResponse | JSONResponse:
    try:
        attachment = await History.get_attachment(attachment_id=attachment_id)
        filename = attachment.display_name
        suffix = attachment.path.suffix
        if suffix and not filename.lower().endswith(suffix.lower()):
            filename += suffix
        return FileResponse(
            path=attachment.path,
            filename=filename,
            media_type=guess_type(attachment.path.name)[0]
            or "application/octet-stream",
            content_disposition_type="inline"
            if not download and attachment.kind in {"image", "video"}
            else "attachment",
        )
    except HistoryStorageError as error:
        return _storage_error(error)
