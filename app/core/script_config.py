#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
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

"""专项配置操作契约；具体实现由宿主按配置类型注入。"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from app.config import ConfigEntry
from app.models.task import ScriptTaskResources


class ScriptConfigImporter(Protocol):
    def __call__(
        self,
        script: ConfigEntry,
        target_directory: Path,
        *,
        user_id: str | None = None,
    ) -> Awaitable[None] | None: ...


class UserReadPreparer(Protocol):
    def __call__(
        self, script: ConfigEntry, *, user_ids: list[str] | None
    ) -> Awaitable[None]: ...


class UserInitializer(Protocol):
    def __call__(
        self,
        script: ConfigEntry,
        user: ConfigEntry,
        *,
        rollback: Callable[[], Awaitable[None]],
    ) -> Awaitable[None]:
        """初始化已提交的新成员；专项按原有失败语义调用同 Task 撤回能力。"""
        ...


class UserRemovalPreparer(Protocol):
    def __call__(
        self, script: ConfigEntry, user_id: UUID
    ) -> Callable[[], Awaitable[None]] | None:
        """捕获删除前信息；返回仅在公共层删除提交成功后执行的文件清理。"""
        ...


class UserUpdatePreparer(Protocol):
    def __call__(
        self, script: ConfigEntry, user: ConfigEntry, *, data: dict[str, Any]
    ) -> Awaitable[None] | None:
        """原地准备本次补丁，不提交配置；异步步骤由写入方在同一 Task 等待。"""
        ...


@dataclass(frozen=True, kw_only=True)
class ScriptConfigHandler:
    """专项只声明实际具备的能力，公共入口保持锁和提交边界。"""

    initialize: Callable[[ConfigEntry], Awaitable[None]] | None = None
    validate_update: Callable[[dict[str, Any]], None] | None = None
    import_config: ScriptConfigImporter | None = None
    prepare_user_update: UserUpdatePreparer | None = None
    user_config_class: type[ConfigEntry] | None = None
    prepare_user_read: UserReadPreparer | None = None
    initialize_user: UserInitializer | None = None
    prepare_user_removal: UserRemovalPreparer | None = None
    task_resources: Callable[[ConfigEntry], ScriptTaskResources] | None = None
