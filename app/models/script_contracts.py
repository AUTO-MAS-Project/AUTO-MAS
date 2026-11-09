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

"""[兼容旧专项] 存量专项配置适配契约，待插件迁移后移除。

现有 Config CRUD 通过宿主注册的回调衔接专项配置操作。
后续由真实插件声明承接配置访问、生命周期和设备绑定能力，再移除对应回调、
注册／绑定入口及本模块；新插件与四级执行框架不新增对此兼容壳的依赖。
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from app.config import ConfigEntry


class ScriptConfigImporter(Protocol):
    """[兼容旧专项] 配置导入回调；后续由插件配置导入能力承接。"""

    def __call__(
        self,
        script: ConfigEntry,
        target_directory: Path,
        *,
        user_id: str | None = None,
    ) -> Awaitable[None] | None:
        """[兼容旧专项] 将配置导入目标目录，允许同步或异步处理。"""
        ...


class UserReadPreparer(Protocol):
    """[兼容旧专项] 用户读取准备回调；后续由插件配置访问能力承接。"""

    def __call__(
        self, script: ConfigEntry, *, user_ids: list[str] | None
    ) -> Awaitable[None]:
        """[兼容旧专项] 在公共查询前准备指定用户的配置。"""
        ...


class UserConfigDirectoryResolver(Protocol):
    def __call__(
        self,
        script: ConfigEntry,
        user: ConfigEntry,
        *,
        data_path: Path,
    ) -> Path: ...


class UserInitializer(Protocol):
    """[兼容旧专项] 用户初始化回调；后续由插件配置生命周期承接。"""

    def __call__(
        self,
        script: ConfigEntry,
        user: ConfigEntry,
        *,
        rollback: Callable[[], Awaitable[None]],
    ) -> Awaitable[None]:
        """[兼容旧专项] 初始化已提交的新成员；专项按原有失败语义调用同 Task 撤回能力。"""
        ...


class UserRemovalPreparer(Protocol):
    """[兼容旧专项] 用户删除准备回调；后续由插件配置生命周期承接。"""

    def __call__(
        self, script: ConfigEntry, user_id: UUID
    ) -> Callable[[], Awaitable[None]] | None:
        """[兼容旧专项] 捕获删除前信息；返回仅在公共层删除提交成功后执行的文件清理。"""
        ...


class UserUpdatePreparer(Protocol):
    """[兼容旧专项] 用户更新准备回调；后续由插件配置更新能力承接。"""

    def __call__(
        self, script: ConfigEntry, user: ConfigEntry, *, data: dict[str, Any]
    ) -> Awaitable[Callable[[], None] | None] | Callable[[], None] | None:
        """[兼容旧专项] 原地准备补丁，不提交配置；可返回提交保护范围内同步复核及补全补丁的回调。"""
        ...


@dataclass(frozen=True, kw_only=True)
class ScriptEmulatorBinding:
    """[兼容旧专项] 存量设备字段映射；后续由插件设备绑定声明承接。"""

    group: str
    id_field: str
    index_field: str

    def read(self, script: ConfigEntry) -> tuple[str | UUID, str]:
        """[兼容旧专项] 按声明的字段位置读取持久设备绑定。"""
        fields = getattr(script, self.group)
        return getattr(fields, self.id_field), getattr(fields, self.index_field)

    def read_patch(
        self, script: ConfigEntry, patch: dict[str, Any]
    ) -> tuple[Any, Any] | None:
        """[兼容旧专项] 仅在提交设备号时合成候选，兼容 Id、Index 分步保存。"""
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
    """[兼容旧专项] 存量配置回调集合，后续由插件配置能力声明承接并移除。

    只声明现有专项实际具备的能力，公共入口继续保持锁和提交边界。
    新插件不扩展此回调集合，迁移时同步移除宿主注册及 Config 绑定壳。
    """

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
    user_config_directory: UserConfigDirectoryResolver | None = None
    prepare_user_read: UserReadPreparer | None = None
    initialize_user: UserInitializer | None = None
    prepare_user_removal: UserRemovalPreparer | None = None
    emulator_binding: ScriptEmulatorBinding | None = None
    supports_mod_avd: bool = False
