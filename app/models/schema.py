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


from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional, Literal


class BaseOut(BaseModel):
    code: int = Field(default=200, description="状态码")
    status: str = Field(default="success", description="操作状态")
    message: str = Field(default="操作成功", description="操作消息")


class ScriptCreateIn(BaseModel):
    type: Literal["MAA", "General"]


class ScriptCreateOut(BaseOut):
    scriptId: str = Field(..., description="新创建的脚本ID")
    data: Dict[str, Any] = Field(..., description="脚本配置数据")


class ScriptGetIn(BaseModel):
    scriptId: Optional[str] = Field(None, description="脚本ID，仅在模式为Single时需要")


class ScriptGetOut(BaseOut):
    index: List[Dict[str, str]] = Field(..., description="脚本索引列表")
    data: Dict[str, Any] = Field(..., description="脚本列表或单个脚本数据")


class ScriptUpdateIn(BaseModel):
    scriptId: str = Field(..., description="脚本ID")
    data: Dict[str, Dict[str, Any]] = Field(..., description="脚本更新数据")


class ScriptDeleteIn(BaseModel):
    scriptId: str = Field(..., description="脚本ID")


class SettingGetOut(BaseOut):
    data: Dict[str, Dict[str, Any]] = Field(..., description="全局设置数据")


class SettingUpdateIn(BaseModel):
    data: Dict[str, Dict[str, Any]] = Field(..., description="全局设置更新数据")
