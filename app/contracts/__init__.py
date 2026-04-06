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

"""
API Contract 层

本模块包含所有 API 请求/响应模型，按领域拆分为独立文件。

设计原则：
1. Contract 只负责 API 边界定义，不包含业务逻辑
2. 使用单一 Contract 模型 + readOnly/writeOnly 字段标记
3. 所有 Contract 继承 ApiModel，获得统一配置
4. 字段命名使用 snake_case，通过 alias 兼容前端
"""

from .common_contract import (
    ApiModel,
    ComboBoxItem,
    ComboBoxOut,
    IndexOrderPatch,
    InfoOut,
    OutBase,
    ResourceCollectionOut,
    ResourceCreateOut,
    ResourceItemOut,
    dump_writable_data,
    project_model,
    project_model_list,
    project_model_map,
)

__all__ = [
    "ApiModel",
    "OutBase",
    "InfoOut",
    "ComboBoxItem",
    "ComboBoxOut",
    "ResourceCollectionOut",
    "ResourceItemOut",
    "ResourceCreateOut",
    "IndexOrderPatch",
    "dump_writable_data",
    "project_model",
    "project_model_list",
    "project_model_map",
]
