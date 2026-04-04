from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common_contract import ApiModel, OutBase


class HistoryIndexItem(ApiModel):
    date: str = Field(..., description="日期")
    status: Literal["DONE", "ERROR"] = Field(..., description="状态")
    jsonFile: str = Field(..., description="对应JSON文件")


class HistoryData(ApiModel):
    index: list[HistoryIndexItem] | None = Field(
        default=None, description="历史记录索引列表"
    )
    recruit_statistics: dict[str, int] | None = Field(
        default=None, description="公招统计数据, key为星级, value为对应的公招数量"
    )
    drop_statistics: dict[str, dict[str, int]] | None = Field(
        default=None,
        description="掉落统计数据, 格式为 { '关卡号': { '掉落物': 数量 } }",
    )
    error_info: dict[str, str] | None = Field(
        default=None, description="报错信息, key为时间戳, value为错误描述"
    )
    sanity: int | None = Field(default=None, description="当前理智值")
    sanity_full_at: str | None = Field(
        default=None, description="理智回满时间, 格式通常为 YYYY-MM-DD HH:MM:SS"
    )
    log_content: str | None = Field(
        default=None, description="日志内容, 仅在提取单条历史记录数据时返回"
    )


class HistorySearchIn(ApiModel):
    mode: Literal["DAILY", "WEEKLY", "MONTHLY"] = Field(..., description="合并模式")
    start_date: str = Field(..., description="开始日期, 格式YYYY-MM-DD")
    end_date: str = Field(..., description="结束日期, 格式YYYY-MM-DD")


class HistorySearchOut(OutBase):
    data: dict[str, dict[str, HistoryData]] = Field(
        ...,
        description="历史记录索引数据字典, 格式为 { '日期': { '用户名': [历史记录信息] } }",
    )


class HistoryDataGetIn(ApiModel):
    jsonPath: str = Field(..., description="需要提取数据的历史记录JSON文件")


class HistoryDataGetOut(OutBase):
    data: HistoryData = Field(..., description="历史记录数据")


__all__ = [
    "HistoryIndexItem",
    "HistoryData",
    "HistorySearchIn",
    "HistorySearchOut",
    "HistoryDataGetIn",
    "HistoryDataGetOut",
]
