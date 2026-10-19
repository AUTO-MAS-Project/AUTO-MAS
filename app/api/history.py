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


from datetime import datetime
from pathlib import Path
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

from app.core import Config
from app.models.schema import OutBase, ReplayRecord
from app.utils import get_logger


class PullCountStatistics(BaseModel):
    resource_pulls: int = Field(..., description="资源折算抽数")
    carry_over_pulls: int = Field(..., description="可留到下版本的凭证抽数")
    next_pool_shop_pulls: int = Field(..., description="下版本商店抽数")
    next_pool_signin_pulls: int = Field(..., description="下版本签到抽数")
    current_pool_total: int = Field(..., description="当前卡池可用抽数")
    next_pool_total: int = Field(..., description="下版本卡池预计总抽数")


class HistoryIndexItem(BaseModel):
    date: str = Field(..., description="日期")
    status: Literal["DONE", "SKIP", "ERROR"] = Field(
        ..., description="状态: DONE 完成, SKIP 跳过(如停服维护), ERROR 失败"
    )
    jsonFile: str = Field(..., description="对应JSON文件")
    result: Optional[str] = Field(
        default=None, description="运行结果文本，可能带运行阶段前缀"
    )


class HistoryData(BaseModel):
    replays: list[ReplayRecord] = Field(
        default_factory=list, description="本轮失败回放"
    )
    index: Optional[List[HistoryIndexItem]] = Field(
        default=None, description="历史记录索引列表"
    )
    recruit_statistics: Optional[Dict[str, int]] = Field(
        default=None, description="公招统计数据, key为星级, value为对应的公招数量"
    )
    drop_statistics: Optional[Dict[str, Dict[str, int]]] = Field(
        default=None,
        description="掉落统计数据, 格式为 { '关卡号': { '掉落物': 数量 } }",
    )
    matrix_statistics: Optional[Dict[str, str]] = Field(
        default=None, description="基质统计数据, key为技能组合, value为符合武器名称"
    )
    pull_count_statistics: Optional[PullCountStatistics] = Field(
        default=None, description="MaaEnd 抽数计算统计"
    )
    error_info: Optional[Dict[str, str]] = Field(
        default=None, description="报错信息, key为时间戳, value为错误描述"
    )
    log_content: Optional[str] = Field(
        default=None, description="日志内容, 仅在提取单条历史记录数据时返回"
    )


class HistorySearchIn(BaseModel):
    mode: Literal["DAILY", "WEEKLY", "MONTHLY"] = Field(..., description="合并模式")
    start_date: str = Field(..., description="开始日期, 格式YYYY-MM-DD")
    end_date: str = Field(..., description="结束日期, 格式YYYY-MM-DD")


class HistorySearchOut(OutBase):
    data: Dict[str, Dict[str, HistoryData]] = Field(
        ...,
        description="历史记录索引数据字典, 格式为 { '日期': { '用户名': [历史记录信息] } }",
    )


class HistoryDataGetIn(BaseModel):
    jsonPath: str = Field(..., description="需要提取数据的历史记录JSON文件")


class HistoryDataGetOut(OutBase):
    data: HistoryData = Field(..., description="历史记录数据")


class ReplayListOut(OutBase):
    replays: list[ReplayRecord] = Field(default_factory=list)
    directory: str = ""


router = APIRouter(prefix="/api/history", tags=["历史记录"])
logger = get_logger("历史记录 API")


@router.get(
    "/replays",
    tags=["Get"],
    response_model=ReplayListOut,
    operation_id="get_obs_replays_api_history_replays_get",
    summary="查询保留的失败回放",
)
async def get_obs_replays() -> ReplayListOut:
    from app.services.obs_replay import ObsReplay

    try:
        return ReplayListOut(
            replays=await ObsReplay.list_replays(), directory=str(ObsReplay.directory)
        )
    except Exception as error:
        return ReplayListOut(code=500, status="error", message=str(error))


@router.post(
    "/search",
    tags=["Get"],
    summary="搜索历史记录总览信息",
    response_model=HistorySearchOut,
    status_code=200,
)
async def search_history(history: HistorySearchIn) -> HistorySearchOut:

    try:
        data = await Config.search_history(
            history.mode,
            datetime.strptime(history.start_date, "%Y-%m-%d").date(),
            datetime.strptime(history.end_date, "%Y-%m-%d").date(),
        )
        for date, users in data.items():
            for user, records in users.items():
                record = await Config.merge_statistic_info(records)
                # 安全检查：确保 index 字段存在
                if "index" not in record:
                    record["index"] = []
                record["index"] = [HistoryIndexItem(**_) for _ in record["index"]]
                record = HistoryData(**record)
                data[date][user] = record
    except Exception as e:
        logger.opt(exception=True).warning(
            f"search_history失败: {type(e).__name__}: {e}"
        )
        return HistorySearchOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data={},
        )
    return HistorySearchOut(data=data)


@router.post(
    "/data",
    tags=["Get"],
    summary="从指定文件内获取历史记录数据",
    response_model=HistoryDataGetOut,
    status_code=200,
)
async def get_history_data(history: HistoryDataGetIn = Body(...)) -> HistoryDataGetOut:

    try:
        path = Path(history.jsonPath)
        data = await Config.merge_statistic_info([path])
        data.pop("index", None)
        data["log_content"] = path.with_suffix(".log").read_text(encoding="utf-8")
        from app.services.obs_replay import ObsReplay

        try:
            data["replays"] = await ObsReplay.list_replays(history_path=str(path))
        except Exception:
            logger.warning("无法读取关联回放，仍返回历史日志")
        data = HistoryData(**data)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_history_data失败: {type(e).__name__}: {e}"
        )
        return HistoryDataGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=HistoryData(**{}),
        )
    return HistoryDataGetOut(data=data)
