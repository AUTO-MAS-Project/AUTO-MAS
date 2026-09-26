import asyncio
import importlib
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from maa import resource as maa_resource
from maa.toolkit import Toolkit

from app.core.config import Config
from app.models.emulator import DeviceInfo, DeviceStatus


class _ResourceStub:
    def post_bundle(self, *_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(wait=lambda: None)

    def custom_action(self, _name: str):
        return lambda action: action


@pytest.fixture(scope="module")
def maa_manager_module(tmp_path_factory: pytest.TempPathFactory):
    module_name = "app.core.maa_manager"
    already_loaded = module_name in sys.modules
    if already_loaded:
        yield importlib.import_module(module_name)
        return

    config_path = tmp_path_factory.mktemp("maa-manager-config")
    with (
        patch.object(Config, "config_path", config_path),
        patch.object(maa_resource, "Resource", _ResourceStub),
        patch.object(Toolkit, "init_option"),
    ):
        module = importlib.import_module(module_name)

    try:
        yield module
    finally:
        sys.modules.pop(module_name, None)
        core_module = sys.modules.get("app.core")
        if getattr(core_module, "maa_manager", None) is module:
            delattr(core_module, "maa_manager")


def _available_devices(monkeypatch, maa_manager_module, *addresses: str):
    devices = [SimpleNamespace(address=address) for address in addresses]
    monkeypatch.setattr(
        maa_manager_module.Toolkit,
        "find_adb_devices",
        staticmethod(lambda: devices),
    )
    return devices


def _convert(maa_manager_module, address: str):
    return asyncio.run(
        maa_manager_module.MaaFWManager.convert_adb(
            DeviceInfo(
                title="测试设备",
                status=DeviceStatus.ONLINE,
                adb_address=address,
            )
        )
    )


def test_convert_adb_matches_usb_serial_exactly(
    monkeypatch, maa_manager_module
) -> None:
    devices = _available_devices(
        monkeypatch, maa_manager_module, "OTHER123", "HA2FKGY1"
    )

    assert _convert(maa_manager_module, "HA2FKGY1") is devices[1]


def test_convert_adb_matches_wireless_address_exactly(
    monkeypatch, maa_manager_module
) -> None:
    devices = _available_devices(
        monkeypatch,
        maa_manager_module,
        "192.168.1.10:5555",
        "192.168.1.20:5555",
    )

    assert _convert(maa_manager_module, "192.168.1.20:5555") is devices[1]


@pytest.mark.parametrize(
    ("target", "available"),
    [
        ("emulator-5554", "127.0.0.1:5555"),
        ("127.0.0.1:5555", "emulator-5554"),
    ],
)
def test_convert_adb_matches_equivalent_emulator_addresses(
    monkeypatch, maa_manager_module, target: str, available: str
) -> None:
    devices = _available_devices(monkeypatch, maa_manager_module, "HA2FKGY1", available)

    assert _convert(maa_manager_module, target) is devices[1]


def test_convert_adb_does_not_match_wireless_devices_by_port(
    monkeypatch, maa_manager_module
) -> None:
    _available_devices(
        monkeypatch,
        maa_manager_module,
        "192.168.1.10:5555",
        "192.168.1.30:5555",
    )

    with pytest.raises(RuntimeError, match="无法找到指定设备"):
        _convert(maa_manager_module, "192.168.1.20:5555")


def test_convert_adb_raises_when_unknown_usb_serial_is_not_found(
    monkeypatch, maa_manager_module
) -> None:
    _available_devices(monkeypatch, maa_manager_module, "OTHER123")

    with pytest.raises(RuntimeError, match="无法找到指定设备"):
        _convert(maa_manager_module, "HA2FKGY1")
