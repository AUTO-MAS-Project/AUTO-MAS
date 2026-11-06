"""The creation endpoint carries the selected AVD preset to the operation owner."""

import pytest
from pydantic import ValidationError

import app.api.emulator.instances as api


@pytest.mark.asyncio
async def test_create_preserves_resolution_in_operation_options(monkeypatch) -> None:
    received = []

    async def create(emulator_id, path_id, name, options):
        received.append(options)
        return {"ok": True, "slot": "1", "nativeIndex": "7"}

    monkeypatch.setattr(api.EmulatorManager, "create_instance", create)
    for resolution in (None, 720, 1080):
        payload = api.Emulator2InstanceCreateIn(
            emulatorId="emulator", pathId="installation", resolution=resolution
        )
        result = await api.create_instance(payload)
        assert result.ok
        assert received[-1]["resolution"] == resolution
    with pytest.raises(ValidationError):
        api.Emulator2InstanceCreateIn(
            emulatorId="emulator", pathId="installation", resolution=1440
        )
