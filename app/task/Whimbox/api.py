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
"""脚本管理：奇想盒 路由与端点专用模型。"""

from typing import (
    List,
    Optional,
    Union,
)

from fastapi import APIRouter
from pydantic import (
    BaseModel,
    Field,
)

from app.models.schema import (
    OutBase,
)
from app.utils import get_logger


class WhimboxTaskCatalogItem(BaseModel):
    """任务目录条目：一条龙步骤开关（上游三件套机械转换）"""

    key: str = Field(default=..., description="上游配置键")
    display: str = Field(default=..., description="显示名（上游模板 description）")
    section: str = Field(default=..., description="上游配置节")


class WhimboxOptionCatalogItem(BaseModel):
    """任务目录条目：一条龙目标/参数字段（上游三件套机械转换）"""

    key: str = Field(default=..., description="上游配置键")
    display: str = Field(default=..., description="显示名（上游模板 description）")
    section: str = Field(default=..., description="上游配置节")
    field_type: str = Field(
        default=..., description="控件类型：bool/int/select/multi_select/text"
    )
    options: List[str] = Field(default_factory=list, description="值域候选")
    default: Optional[Union[bool, int, float, str, List[str]]] = Field(
        default=None, description="上游模板默认值（布尔语义已归一为 bool）"
    )


class WhimboxTaskCatalogData(BaseModel):
    """任务目录数据：步骤开关 + 参数字段 + 上游版本提示"""

    steps: List[WhimboxTaskCatalogItem] = Field(
        default_factory=list, description="一条龙步骤开关（键集与顺序来自上游模板）"
    )
    options: List[WhimboxOptionCatalogItem] = Field(
        default_factory=list, description="一条龙目标/参数字段"
    )
    upstream_version: str = Field(default="", description="奇想盒后端版本（dist-info）")


class WhimboxTaskCatalogOut(OutBase):
    """任务目录响应"""

    data: WhimboxTaskCatalogData = Field(default_factory=WhimboxTaskCatalogData)


router = APIRouter()
logger = get_logger("脚本管理 API")


@router.get(
    "/whimbox/task-catalog",
    tags=["Whimbox"],
    summary="获取奇想盒一条龙任务目录",
    response_model=WhimboxTaskCatalogOut,
    status_code=200,
)
async def get_whimbox_task_catalog_api(
    scriptId: str | None = None,
) -> WhimboxTaskCatalogOut:
    """下发一条龙任务目录（步骤开关 + 目标/参数字段）。

    字段定义与值域从上游安装目录三件套（default_config / setting_options /
    material）运行时机械转换，MAS 发版不管理；上游升级后下次读取自动生效。
    """

    try:
        if not scriptId:
            return WhimboxTaskCatalogOut(
                code=400, status="error", message="缺少 scriptId"
            )
        from app.task.Whimbox import api_service as whimbox_api

        try:
            catalog = whimbox_api.read_task_catalog(scriptId)
        except whimbox_api.WhimboxInstallError as e:
            return WhimboxTaskCatalogOut(code=400, status="error", message=str(e))

        data = WhimboxTaskCatalogData(
            steps=[
                WhimboxTaskCatalogItem(key=s.key, display=s.display, section=s.section)
                for s in catalog.steps
            ],
            options=[
                WhimboxOptionCatalogItem(
                    key=o.key,
                    display=o.display,
                    section=o.section,
                    field_type=o.field_type,
                    options=list(o.options),
                    default=o.default,
                )
                for o in catalog.options
            ],
            upstream_version=catalog.upstream_version,
        )
        return WhimboxTaskCatalogOut(
            message=f"共 {len(data.steps)} 个步骤, {len(data.options)} 个参数字段",
            data=data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_whimbox_task_catalog_api失败: {type(e).__name__}: {e}"
        )
        return WhimboxTaskCatalogOut(
            code=400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
        )
