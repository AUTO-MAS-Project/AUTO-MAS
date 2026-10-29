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
class ScriptEmulatorBinding:
    """专项声明持久绑定的字段位置；是否运行占用由 task_resources 单独决定。"""

    group: str
    id_field: str
    index_field: str

    def read(self, script: ConfigEntry) -> tuple[str | UUID, str]:
        fields = getattr(script, self.group)
        return getattr(fields, self.id_field), getattr(fields, self.index_field)

    def read_patch(
        self, script: ConfigEntry, patch: dict[str, Any]
    ) -> tuple[Any, Any] | None:
        """只在本次提交设备号时合成候选绑定，兼容 Id、Index 分步保存。"""
        changes = patch.get(self.group) if isinstance(patch, dict) else None
        # 页面先存 Id、再存 Index。单存 Id 时不能用旧设备号检查新配置；运行时门面仍负责兜底。
        if not isinstance(changes, dict) or self.index_field not in changes:
            return None
        emulator_id, index = self.read(script)
        return changes.get(self.id_field, emulator_id), changes.get(
            self.index_field, index
        )


@dataclass(frozen=True, kw_only=True)
class ScriptConfigHandler:
    """专项只声明实际具备的能力，公共入口保持锁和提交边界。"""

    initialize: Callable[[ConfigEntry], Awaitable[None]] | None = None
    # 复制事务成功后、通用数据复制前执行；失败与取消由专项维持既有语义。
    clone_script: Callable[[ConfigEntry, ConfigEntry], Awaitable[None]] | None = None
    # 删除前准备可等待；删除提交后的同步通知先于通用目录清理，额外文件随后清理。
    prepare_script_removal: Callable[[ConfigEntry], Awaitable[None]] | None = None
    after_script_removal: Callable[[], None] | None = None
    cleanup_script_files: Callable[[str], Awaitable[None]] | None = None
    validate_update: Callable[[dict[str, Any]], None] | None = None
    import_config: ScriptConfigImporter | None = None
    prepare_user_update: UserUpdatePreparer | None = None
    user_config_class: type[ConfigEntry] | None = None
    prepare_user_read: UserReadPreparer | None = None
    initialize_user: UserInitializer | None = None
    prepare_user_removal: UserRemovalPreparer | None = None
    task_resources: Callable[[ConfigEntry], ScriptTaskResources] | None = None
    emulator_binding: ScriptEmulatorBinding | None = None
    supports_mod_avd: bool = False
