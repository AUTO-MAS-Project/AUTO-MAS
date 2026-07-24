"""Deterministic fakes for emulator manager / API tests.

All fakes avoid real filesystem, registry, process, and ADB access.
Tests must never touch real emulator directories or processes.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.models.emulator import DeviceInfo, DeviceStatus


class FakeConfigHolder:
    """Wraps a raw config dict; ``await holder.toDict()`` returns it."""

    def __init__(self, data: dict[str, dict[str, Any]]) -> None:
        self._data = data

    async def toDict(self) -> dict[str, dict[str, Any]]:
        return self._data


class FakeEmulatorConfigCollection:
    """Dict-like collection keyed by UUID string."""

    def __init__(self, configs: dict[str, dict[str, Any]] | None = None) -> None:
        self._configs = configs or {}

    def __getitem__(self, uid: uuid.UUID) -> FakeConfigHolder:
        key = str(uid)
        if key not in self._configs:
            raise KeyError(key)
        return FakeConfigHolder(self._configs[key])

    def keys(self):
        return [uuid.UUID(k) for k in self._configs]

    def items(self):
        return [(uuid.UUID(k), FakeConfigHolder(v)) for k, v in self._configs.items()]


class FakeConfigNamespace:
    """Replacement for ``Config`` singleton used by emulator_manager."""

    def __init__(
        self,
        configs: dict[str, dict[str, Any]] | None = None,
        *,
        if_block_ad: bool = False,
    ) -> None:
        self.EmulatorConfig = FakeEmulatorConfigCollection(configs)
        self._if_block_ad = if_block_ad

    def get(self, group: str, name: str) -> Any:
        if group == "Function" and name == "IfBlockAd":
            return self._if_block_ad
        return None


class FakePublisher:
    """Records all sent WS messages instead of sending them."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send(
        self,
        id: str,
        type: str,
        data: Any = None,
    ) -> bool:
        payload = data.model_dump() if hasattr(data, "model_dump") else dict(data or {})
        self.sent.append({"id": id, "type": type, "data": payload})
        return True


class FakeDeviceBase:
    """Controllable fake ``DeviceBase`` for deterministic tests."""

    def __init__(self, config: Any) -> None:
        self.config = config
        self.open_calls: list[tuple[str, str]] = []
        self.close_calls: list[str] = []
        self.setvisible_calls: list[tuple[str, bool]] = []
        self._info: dict[str, DeviceInfo] = {}
        self._open_exception: Exception | None = None
        self._close_exception: Exception | None = None
        self._setvisible_exception: Exception | None = None

    async def open(self, idx: str, package_name: str = "") -> DeviceInfo:
        self.open_calls.append((idx, package_name))
        if self._open_exception is not None:
            raise self._open_exception
        return self._info.get(
            idx,
            DeviceInfo(
                title=f"fake-{idx}", status=DeviceStatus.ONLINE, adb_address="127.0.0.1:5555"
            ),
        )

    async def close(self, idx: str) -> DeviceStatus:
        self.close_calls.append(idx)
        if self._close_exception is not None:
            raise self._close_exception
        return DeviceStatus.OFFLINE

    async def getStatus(self, idx: str) -> DeviceStatus:
        return DeviceStatus.ONLINE

    async def getInfo(self, idx: str | None) -> dict[str, DeviceInfo]:
        return dict(self._info)

    async def setVisible(self, idx: str, is_visible: bool) -> DeviceStatus:
        self.setvisible_calls.append((idx, is_visible))
        if self._setvisible_exception is not None:
            raise self._setvisible_exception
        return DeviceStatus.ONLINE


def make_config_data(
    *,
    name: str = "test-emu",
    type: str = "general",
    path: str = "/nonexistent/path",
    max_wait_time: int = 10,
    force_kill: bool = False,
) -> dict[str, dict[str, Any]]:
    """Build a raw config dict matching EmulatorConfig schema."""
    return {
        "Info": {
            "Name": name,
            "Type": type,
            "Path": path,
            "BossKey": "[]",
            "MaxWaitTime": max_wait_time,
            "ForceKillOnClose": force_kill,
        }
    }


@pytest.fixture
def fake_publisher() -> FakePublisher:
    return FakePublisher()


@pytest.fixture
def patch_emulator_manager(monkeypatch: pytest.MonkeyPatch, fake_publisher: FakePublisher):
    """Monkeypatch emulator_manager module-level deps with fakes.

    Returns a namespace with ``config``, ``fake_publisher``, ``fake_device_factory``
    that tests can configure per-case.
    """

    from app.core import emulator_manager as mod

    fake_config = FakeConfigNamespace()
    fake_device_factory = FakeDeviceBase

    monkeypatch.setattr(mod, "Config", fake_config)
    monkeypatch.setattr(
        mod,
        "EMULATOR_TYPE_BOOK",
        {"general": fake_device_factory, "mumu": fake_device_factory, "ldplayer": fake_device_factory},
    )
    monkeypatch.setattr(mod, "Publisher", fake_publisher)

    # Reset inflight dict to avoid cross-test leakage
    mod.EmulatorManager._inflight.clear()

    ns = type("ns", (), {})()
    ns.config = fake_config
    ns.publisher = fake_publisher
    ns.fake_device_factory = fake_device_factory
    ns.mod = mod
    return ns
