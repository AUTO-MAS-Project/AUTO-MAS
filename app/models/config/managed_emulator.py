"""各模拟器插件复用的安装设置、稳定设备身份及恢复材料。"""

from typing import Annotated

from pydantic import Field

from app.config import ConfigCollection, ConfigGroup, UiVisibility, collection, ui
from app.models.config.plugin_emulator import EmulatorDeviceEntry, EmulatorEntry


class ManagedEmulatorDevice(EmulatorDeviceEntry):
    class Info(EmulatorDeviceEntry.Info):
        # 适配插件删除实例后只置 tombstone，宿主随后移除条目
        # （GameManager.remove_deleted_devices），所以最大的槽位号在删除后可能被
        # 新实例再次拿到。宿主移除时一并清掉该 uid 的绑定与配置守卫基准，复用的
        # uid 不会继承旧实例的设置。字段说明沿用旧文字，免得改动接口 schema。
        slot: Annotated[int, ui(visibility=UiVisibility.DISABLE)] = Field(
            default=0, ge=0, description="稳定显示槽位，删除后不复用"
        )
        tombstone: Annotated[bool, ui(visibility=UiVisibility.DISABLE)] = Field(
            default=False, description="实例已删除，保留身份与恢复材料"
        )

    class Session(ConfigGroup):
        backup: dict = Field(
            default_factory=dict, description="本轮临时设置修改前的原值"
        )

    info: Info = Field(default_factory=Info)  # pyright: ignore[reportIncompatibleVariableOverride]
    session: Annotated[Session, ui(visibility=UiVisibility.HIDE)] = Field(
        default_factory=Session
    )


class ManagedEmulatorEntry(EmulatorEntry):
    class Info(EmulatorEntry.Info):
        stable_mode: bool = Field(
            default=False, description="启动前确保适合自动化的稳定设置，关闭不还原"
        )
        config_guard: bool = Field(
            default=False, description="启动前与关闭后确保已保存的用户设置"
        )
        baselines: Annotated[
            dict[str, dict[str, int]], ui(visibility=UiVisibility.HIDE)
        ] = Field(default_factory=dict, description="各实例由用户明确保存的设置基准")
        force_kill_before_launch: bool = Field(
            default=False, description="启动前清理残留进程"
        )
        force_kill_on_close: bool = Field(
            default=False, description="关闭时清理残留进程"
        )
        boss_key: list[str] = Field(default_factory=list, description="老板键快捷键")

    info: Info = Field(default_factory=Info)  # pyright: ignore[reportIncompatibleVariableOverride]
    devices: ConfigCollection[ManagedEmulatorDevice] = collection(ManagedEmulatorDevice)  # type: ignore[assignment]  # pyright: ignore[reportIncompatibleVariableOverride]
