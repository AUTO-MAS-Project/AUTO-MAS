"""设备驱动及控制器的公共开发接口。"""

from app.models.config.managed_emulator import (
    ManagedEmulatorDevice,
    ManagedEmulatorEntry,
)
from app.models.emulator import (
    DeviceBase,
    DeviceInfo,
    DeviceRef,
    DeviceStatus,
    DeviceUpdateOptions,
    EmulatorRuntimePolicy,
    FieldValue,
    InstanceSettings,
    SettingsConflictError,
)
from app.plugin.base.emulator import EmulatorControl, EmulatorExpect

__all__ = [
    "DeviceBase",
    "DeviceInfo",
    "DeviceRef",
    "DeviceStatus",
    "DeviceUpdateOptions",
    "EmulatorRuntimePolicy",
    "EmulatorControl",
    "EmulatorExpect",
    "FieldValue",
    "InstanceSettings",
    "SettingsConflictError",
    "ManagedEmulatorEntry",
    "ManagedEmulatorDevice",
]
