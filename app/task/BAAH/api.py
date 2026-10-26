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
"""脚本管理：BAAH 路由与端点专用模型。"""

from fastapi import APIRouter

from app.core import Config
from app.models.schema import (
    ComboBoxItem,
    ComboBoxOut,
)
from app.utils import get_logger

router = APIRouter()
logger = get_logger("脚本管理 API")


@router.get(
    "/baah/config-names",
    tags=["BAAH"],
    summary="获取 BAAH 配置文件名列表",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_baah_config_names_api(scriptId: str) -> ComboBoxOut:
    """返回 BAAH 配置目录下已有的配置文件名（不含 ``.json`` 后缀）。"""

    try:
        data = [
            ComboBoxItem(label=name, value=name)
            for name in Config.get_baah_config_names(scriptId)
        ]
        return ComboBoxOut(
            code=200,
            status="success",
            message=f"共 {len(data)} 份 BAAH 配置",
            data=data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_baah_config_names_api失败: {type(e).__name__}: {e}"
        )
        return ComboBoxOut(
            code=400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )
