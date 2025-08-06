#   AUTO_MAA:A MAA Multi Account Management and Automation Tool
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox

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


from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional, Literal


class OutBase(BaseModel):
    code: int = Field(default=200, description="状态码")
    status: str = Field(default="success", description="操作状态")
    message: str = Field(default="操作成功", description="操作消息")


class InfoOut(OutBase):
    data: Dict[str, Any] = Field(..., description="收到的服务器数据")


class ScriptCreateIn(BaseModel):
    type: Literal["MAA", "General"]


class ScriptCreateOut(OutBase):
    scriptId: str = Field(..., description="新创建的脚本ID")
    data: Dict[str, Any] = Field(..., description="脚本配置数据")


class ScriptGetIn(BaseModel):
    scriptId: Optional[str] = Field(None, description="脚本ID，仅在模式为Single时需要")


class ScriptGetOut(OutBase):
    index: List[Dict[str, str]] = Field(..., description="脚本索引列表")
    data: Dict[str, Any] = Field(..., description="脚本列表或单个脚本数据")


class ScriptUpdateIn(BaseModel):
    scriptId: str = Field(..., description="脚本ID")
    data: Dict[str, Dict[str, Any]] = Field(..., description="脚本更新数据")


class ScriptDeleteIn(BaseModel):
    scriptId: str = Field(..., description="脚本ID")


class ScriptReorderIn(BaseModel):
    indexList: List[str] = Field(..., description="脚本ID列表，按新顺序排列")


class UserInBase(BaseModel):
    scriptId: str = Field(..., description="所属脚本ID")


class UserCreateOut(OutBase):
    userId: str = Field(..., description="新创建的用户ID")
    data: Dict[str, Any] = Field(..., description="用户配置数据")


class UserUpdateIn(UserInBase):
    userId: str = Field(..., description="用户ID")
    data: Dict[str, Dict[str, Any]] = Field(..., description="用户更新数据")


class UserDeleteIn(UserInBase):
    userId: str = Field(..., description="用户ID")


class UserReorderIn(UserInBase):
    indexList: List[str] = Field(..., description="用户ID列表，按新顺序排列")


class PlanCreateIn(BaseModel):
    type: Literal["MaaPlan"]


class PlanCreateOut(OutBase):
    planId: str = Field(..., description="新创建的计划ID")
    data: Dict[str, Any] = Field(..., description="计划配置数据")


class PlanGetIn(BaseModel):
    planId: Optional[str] = Field(None, description="计划ID，仅在模式为Single时需要")


class PlanGetOut(OutBase):
    index: List[Dict[str, str]] = Field(..., description="计划索引列表")
    data: Dict[str, Any] = Field(..., description="计划列表或单个计划数据")


class PlanUpdateIn(BaseModel):
    planId: str = Field(..., description="计划ID")
    data: Dict[str, Dict[str, Any]] = Field(..., description="计划更新数据")


class PlanDeleteIn(BaseModel):
    planId: str = Field(..., description="计划ID")


class PlanReorderIn(BaseModel):
    indexList: List[str] = Field(..., description="计划ID列表，按新顺序排列")


class QueueCreateOut(OutBase):
    queueId: str = Field(..., description="新创建的队列ID")
    data: Dict[str, Any] = Field(..., description="队列配置数据")


class QueueGetIn(BaseModel):
    queueId: Optional[str] = Field(None, description="队列ID，仅在模式为Single时需要")


class QueueGetOut(OutBase):
    index: List[Dict[str, str]] = Field(..., description="队列索引列表")
    data: Dict[str, Any] = Field(..., description="队列列表或单个队列数据")


class QueueUpdateIn(BaseModel):
    queueId: str = Field(..., description="队列ID")
    data: Dict[str, Dict[str, Any]] = Field(..., description="队列更新数据")


class QueueDeleteIn(BaseModel):
    queueId: str = Field(..., description="队列ID")


class QueueReorderIn(BaseModel):
    indexList: List[str] = Field(..., description="调度队列ID列表，按新顺序排列")


class QueueSetInBase(BaseModel):
    queueId: str = Field(..., description="所属队列ID")


class TimeSetCreateOut(OutBase):
    timeSetId: str = Field(..., description="新创建的时间设置ID")
    data: Dict[str, Any] = Field(..., description="时间设置配置数据")


class TimeSetUpdateIn(QueueSetInBase):
    timeSetId: str = Field(..., description="时间设置ID")
    data: Dict[str, Dict[str, Any]] = Field(..., description="时间设置更新数据")


class TimeSetDeleteIn(QueueSetInBase):
    timeSetId: str = Field(..., description="时间设置ID")


class TimeSetReorderIn(QueueSetInBase):
    indexList: List[str] = Field(..., description="时间设置ID列表，按新顺序排列")


class QueueItemCreateOut(OutBase):
    queueItemId: str = Field(..., description="新创建的队列项ID")
    data: Dict[str, Any] = Field(..., description="队列项配置数据")


class QueueItemUpdateIn(QueueSetInBase):
    queueItemId: str = Field(..., description="队列项ID")
    data: Dict[str, Dict[str, Any]] = Field(..., description="队列项更新数据")


class QueueItemDeleteIn(QueueSetInBase):
    queueItemId: str = Field(..., description="队列项ID")


class QueueItemReorderIn(QueueSetInBase):
    indexList: List[str] = Field(..., description="队列项ID列表，按新顺序排列")


class DispatchIn(BaseModel):
    taskId: str = Field(
        ...,
        description="目标任务ID，设置类任务可选对应脚本ID或用户ID，代理类任务可选对应队列ID或脚本ID",
    )


class DispatchCreateIn(DispatchIn):
    mode: Literal["自动代理", "人工排查", "设置脚本"] = Field(
        ..., description="任务模式"
    )


class SettingGetOut(OutBase):
    data: Dict[str, Dict[str, Any]] = Field(..., description="全局设置数据")


class SettingUpdateIn(BaseModel):
    data: Dict[str, Dict[str, Any]] = Field(..., description="全局设置更新数据")
