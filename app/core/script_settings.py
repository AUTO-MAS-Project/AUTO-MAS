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
"""脚本编辑用例，只依赖配置存取与绑定校验契约。"""

from collections.abc import Awaitable, Callable
from typing import Any, Protocol


class ScriptSettingsGateway(Protocol):
    """编辑用例需要的配置能力，由宿主的配置入口实现。"""

    async def update_script(self, script_id: str, data: dict[str, Any]) -> None: ...

    async def update_user(
        self, script_id: str, user_id: str, data: dict[str, Any]
    ) -> bool: ...


BindingValidator = Callable[[str, dict[str, Any]], Awaitable[str | None]]


class ScriptSettings:
    """编排保存顺序；配置写入能力与绑定校验由组装层注入。"""

    def __init__(
        self,
        *,
        gateway: ScriptSettingsGateway,
        validate_binding: BindingValidator,
    ) -> None:
        self._gateway = gateway
        self._validate_binding = validate_binding

    async def update_script(self, script_id: str, data: dict[str, Any]) -> str | None:
        """绑定校验通过后才提交，拒绝时沿用现有提示。"""
        refusal = await self._validate_binding(script_id, data)
        if refusal:
            return refusal
        await self._gateway.update_script(script_id, data)
        return None

    async def update_user(
        self, script_id: str, user_id: str, *, data: dict[str, Any]
    ) -> None:
        """交给统一写入入口，在同一 Task 内预处理并提交配置。"""
        await self._gateway.update_user(script_id, user_id, data=data)
