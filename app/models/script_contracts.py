"""[兼容旧专项] 旧配置 CRUD 回调契约，专项完成插件化后移除；新插件不使用。"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from app.config import ConfigEntry


class ScriptConfigImporter(Protocol):
    """配置导入回调。"""

    def __call__(
        self,
        script: ConfigEntry,
        target_directory: Path,
        *,
        user_id: str | None = None,
    ) -> Awaitable[None] | None:
        """将配置导入目标目录，允许同步或异步处理。"""
        ...


class UserReadPreparer(Protocol):
    """用户读取准备回调。"""

    def __call__(
        self, script: ConfigEntry, *, user_ids: list[str] | None
    ) -> Awaitable[None]:
        """在公共查询前准备指定用户的配置。"""
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
    """用户初始化回调。"""

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
    """用户删除准备回调。"""

    def __call__(
        self, script: ConfigEntry, user_id: UUID
    ) -> Callable[[], Awaitable[None]] | None:
        """捕获删除前信息；返回仅在公共层删除提交成功后执行的文件清理。"""
        ...


class UserUpdatePreparer(Protocol):
    """用户更新准备回调。"""

    def __call__(
        self, script: ConfigEntry, user: ConfigEntry, *, data: dict[str, Any]
    ) -> Awaitable[Callable[[], None] | None] | Callable[[], None] | None:
        """原地准备补丁，不提交配置；可返回提交保护范围内同步复核及补全补丁的回调。"""
        ...


@dataclass(frozen=True, kw_only=True)
class ScriptEmulatorBinding:
    """存量设备字段映射。"""

    group: str
    id_field: str
    index_field: str

    def read(self, script: ConfigEntry) -> tuple[str | UUID, str]:
        """按声明的字段位置读取持久设备绑定。"""
        fields = getattr(script, self.group)
        return getattr(fields, self.id_field), getattr(fields, self.index_field)

    def read_patch(
        self, script: ConfigEntry, patch: dict[str, Any]
    ) -> tuple[Any, Any] | None:
        """仅在提交设备号时合成候选，兼容 Id、Index 分步保存。"""
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
    """[兼容旧专项] 存量配置回调与设备字段映射，不属于插件 SDK。"""

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
