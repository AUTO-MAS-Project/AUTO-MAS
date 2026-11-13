from __future__ import annotations

from copy import deepcopy
from typing import Annotated, ClassVar, Literal
from uuid import UUID

from auto_mas_core import ScriptEntry
from auto_mas_core.host.config import (
    ConfigCollection,
    ConfigGroup,
    Virtual,
    collection,
    encrypted,
    ref,
    virtual_field,
)
from auto_mas_core.host.config_types import (
    FolderPath,
)
from auto_mas_core.host.models_config_shared import (
    none_as,
)
from pydantic import Field

from maa_adapter.config.user import MaaUserConfig


class MaaConfig(ScriptEntry):
    "MAA配置"

    related_config: ClassVar = {}

    class EmulatorFields(ConfigGroup):
        Id: Annotated[
            UUID | str,
            ref(
                "EmulatorConfig",
                default="-",
                allow_values=("-",),
                display_field="Info.Name",
            ),
        ] = Field(default_factory=lambda: "-", description="模拟器 ID")
        Index: str = Field(default_factory=lambda: "-", description="模拟器索引")

    Emulator: EmulatorFields = Field(default_factory=EmulatorFields)

    class InfoFields(ConfigGroup):
        Name: str = Field(
            default_factory=lambda: "新 MAA 托管", description="MAA 托管名称"
        )

        Path: FolderPath = Field(default_factory=lambda: None, description="MAA 路径")

    Info: InfoFields = Field(default_factory=InfoFields)  # pyright: ignore[reportIncompatibleVariableOverride]

    class RunFields(ConfigGroup):
        AnnihilationTimeLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 40,
            description="剿灭时间限制（分钟）",
        )

        GameUpdateTimeLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 60,
            description="游戏更新时间限制（分钟）",
        )

        HardTimeLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 120,
            description="单账号运行总时限（分钟），包含等待和全部重试",
        )

        IfAutoInstallGameApk: bool = Field(
            default_factory=lambda: False,
            description="是否允许自动下载并安装游戏安装包（仅官服）",
        )

        IfCheckGameUpdate: bool = Field(
            default_factory=lambda: False, description="是否在启动 MAA 前检查游戏更新"
        )

        ProxyTimesLimit: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            default_factory=lambda: 0, description="代理次数限制"
        )

        RoutineTimeLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 10,
            description="日常时间限制（分钟）",
        )

        RunTimesLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 3, description="运行次数限制"
        )

        TaskTransitionMethod: Literal["NoAction", "ExitGame", "ExitEmulator"] = Field(
            default_factory=lambda: "ExitEmulator", description="任务切换方式"
        )

    Run: RunFields = Field(default_factory=RunFields)

    class UpdateFields(ConfigGroup):
        TakeoverMigrationVersion: Annotated[int, Field(ge=0, le=1)] = Field(
            default=1, description="更新接管一次性迁移版本"
        )

        MirrorChyanCDK: Annotated[str, encrypted()] = Field(
            default_factory=lambda: "",
            description="本托管的 Mirror 酱 CDK（加密存储，留空回退 MAS 全局配置）",
        )
        TakeoverEnabled: bool = Field(
            default_factory=lambda: False,
            description="是否接管 MAA 本体与资源更新（关=完全由 MAA 自行处理）",
        )
        Channel: Literal["stable", "beta"] = Field(
            default_factory=lambda: "stable", description="MAA 更新通道：正式版或公测版"
        )
        ChannelMigrationVersion: Annotated[int, Field(ge=0, le=1)] = Field(
            default=1, description="更新通道一次性迁移版本"
        )

    Update: UpdateFields = Field(default_factory=UpdateFields)
    # collection 在运行时将类型域限定为 MaaUserConfig；可变泛型的继承检查不表达该约束。
    users: ConfigCollection[MaaUserConfig] = collection(MaaUserConfig)  # pyright: ignore[reportIncompatibleVariableOverride]

    def get_emulator_binding(self) -> tuple[str | UUID, str]:
        """[兼容旧模拟器] 为设备反查提供已保存的绑定，执行与实例能力仍由 MAA 任务负责。"""
        return self.Emulator.Id, self.Emulator.Index

    @classmethod
    def normalize_payload(cls, data):
        """复制托管配置输入并兼容原有账号集合字段，保持插件配置读写结构一致。"""
        data = deepcopy(data)
        if data and "SubConfigsInfo" in data:
            subconfigs = data["SubConfigsInfo"]
            if "UserData" in subconfigs:
                subconfigs["users"] = subconfigs.pop("UserData")
        if data and "UserData" in data:
            data["users"] = data.pop("UserData")
        if data and "users" in data:
            for item in data["users"].get("order", []):
                if item.get("type") == "MaaPluginUserConfig":
                    item["type"] = "MaaUserConfig"
        return data

    class Metadata(ScriptEntry.Info):
        # 来源兼容字段改为虚拟读取；Virtual 的冷态 None 与父类可写字段类型不同。
        name: Virtual[str] = None  # pyright: ignore[reportIncompatibleVariableOverride]

    info: Metadata = Field(default_factory=Metadata)  # pyright: ignore[reportIncompatibleVariableOverride]

    @property
    def UserData(self):
        """将插件 users 集合暴露为来源专项使用的 UserData 入口。"""
        return self.users

    @virtual_field("info.name")
    def plugin_name(self):
        """将来源托管名称字段提供给插件脚本基类使用。"""
        return self.Info.Name

    async def _activate_from_payload(self, payload, *, regenerate_uuids=False):
        """将兼容后的账号集合结构交给配置框架，激活脚本节点及用户集合。"""
        await super()._activate_from_payload(
            type(self).normalize_payload(payload), regenerate_uuids=regenerate_uuids
        )
