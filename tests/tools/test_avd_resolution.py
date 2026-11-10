"""AVD display presets through creation and settings (sent to modavd as ``--resolution``)."""

from pathlib import Path

import pytest

from app.utils.common.emulator2.avd.manager import _AvdCore


class _FakeCli:
    """Smallest modavd stand-in: ``info`` reports the saved display, calls are recorded."""

    def __init__(self, width: int = 1280, height: int = 720, dpi: int = 240) -> None:
        self.config = {"width": width, "height": height, "dpi": dpi}
        self.set_calls: list[dict] = []
        self.create_calls: list[dict] = []

    async def info(self, index: str) -> dict:
        return {"index": int(index), "config": dict(self.config)}

    async def set(self, index: str, **kwargs: object) -> dict:
        self.set_calls.append(kwargs)
        return {"applied": {}}

    async def check(self, *, memory: int | None = None) -> dict:
        return {"items": []}

    async def create(self, **kwargs: object) -> dict:
        self.create_calls.append(kwargs)
        return {"index": kwargs.get("index")}


def _manager(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cli: _FakeCli
) -> _AvdCore:
    exe = tmp_path / "sdk/emulator/emulator.exe"
    return _AvdCore(exe, 60, False, cli=cli)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_new_instance_defaults_to_1080p(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli = _FakeCli()
    manager = _manager(tmp_path, monkeypatch, cli)
    await manager.create_instance("display test", native_index=7)
    assert [call["resolution"] for call in cli.create_calls] == [1080]


@pytest.mark.asyncio
@pytest.mark.parametrize("portrait", [False, True])
async def test_settings_pick_the_preset_and_keep_orientation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, portrait: bool
) -> None:
    cli = _FakeCli(*((720, 1280, 240) if portrait else (1280, 720, 240)))
    manager = _manager(tmp_path, monkeypatch, cli)
    for width, height, dpi in [(1920, 1080, 280), (1280, 720, 240)]:
        current = (await manager.read_instance_settings("7")).values()
        # Mixed-family batch settings carry the standard emulator's DPI.
        applied = await manager.write_instance_settings(
            "7", {"width": width, "height": height, "dpi": 360}, current
        )
        assert applied == {
            "width": height if portrait else width,
            "height": width if portrait else height,
            "dpi": dpi,
        }
    # Already at 720p: only the switch to 1080p reaches modavd.
    assert cli.set_calls == [{"resolution": 1080}]


@pytest.mark.asyncio
async def test_custom_display_is_rejected_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli = _FakeCli()
    manager = _manager(tmp_path, monkeypatch, cli)
    for changes in ({"width": 1600, "height": 900}, {"dpi": 360}):
        with pytest.raises(ValueError):
            await manager.write_instance_settings("7", changes)
    assert cli.set_calls == []
