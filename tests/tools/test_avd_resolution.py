"""AVD display presets through creation, settings and the pre-boot file contract."""

from pathlib import Path

import pytest

from app.utils.common.emulator2.avd.instances import (
    apply_display,
    config_path,
    read_ini,
    write_ini,
)
from app.utils.common.emulator2.avd.manager import _AvdCore


@pytest.mark.asyncio
async def test_new_instance_defaults_to_1080p(tmp_path: Path) -> None:
    manager = _AvdCore(tmp_path / "sdk/emulator/emulator.exe", 60, False)
    index = await manager.create_instance("display test", native_index=7)
    config = read_ini(config_path(tmp_path, index))
    assert [
        config[key] for key in ("hw.lcd.width", "hw.lcd.height", "hw.lcd.density")
    ] == ["1920", "1080", "280"]


@pytest.mark.asyncio
@pytest.mark.parametrize("portrait", [False, True])
async def test_settings_switch_both_ways_and_keep_orientation(
    tmp_path: Path, portrait: bool
) -> None:
    manager = _AvdCore(tmp_path / "sdk/emulator/emulator.exe", 60, False)
    index = await manager.create_instance(native_index=7, resolution=720)
    path = config_path(tmp_path, index)
    if portrait:
        config = read_ini(path)
        config.update({"hw.lcd.width": "720", "hw.lcd.height": "1280"})
        write_ini(path, config)
    for width, height, dpi in [(1920, 1080, 280), (1280, 720, 240)]:
        current = (await manager.read_instance_settings(index)).values()
        # Mixed-family batch settings carry the standard emulator's DPI.
        applied = await manager.write_instance_settings(
            index, {"width": width, "height": height, "dpi": 360}, current
        )
        expected = {
            "width": height if portrait else width,
            "height": width if portrait else height,
            "dpi": dpi,
        }
        assert applied == expected
        for _ in range(2):
            apply_display(tmp_path, index)
            values = (await manager.read_instance_settings(index)).values()
            assert {key: values[key] for key in expected} == expected
            assert read_ini(path)["hw.lcd.density"] == str(dpi)


@pytest.mark.parametrize(
    "config, expected",
    [
        ({"x": "1"}, ("1280", "720", "240")),
        ({"hw.lcd.height": "720"}, ("720", "1280", "240")),
        ({"hw.lcd.width": "1280", "hw.lcd.height": "720"}, ("1280", "720", "240")),
        (
            {"hw.lcd.width": "1080", "hw.lcd.height": "1920", "hw.lcd.density": "480"},
            ("1080", "1920", "280"),
        ),
    ],
)
def test_old_configs_keep_their_preset_across_preboot_writes(
    tmp_path: Path, config: dict[str, str], expected: tuple[str, str, str]
) -> None:
    path = config_path(tmp_path, 7)
    path.parent.mkdir(parents=True)
    write_ini(path, config)
    for _ in range(2):
        apply_display(tmp_path, 7)
        saved = read_ini(path)
        assert (
            tuple(
                saved[key]
                for key in ("hw.lcd.width", "hw.lcd.height", "hw.lcd.density")
            )
            == expected
        )


@pytest.mark.asyncio
async def test_custom_display_is_rejected_without_writing(tmp_path: Path) -> None:
    manager = _AvdCore(tmp_path / "sdk/emulator/emulator.exe", 60, False)
    index = await manager.create_instance(native_index=7)
    path = config_path(tmp_path, index)
    before = path.read_bytes()
    for changes in ({"width": 1600, "height": 900}, {"dpi": 360}):
        with pytest.raises(ValueError):
            await manager.write_instance_settings(index, changes)
        assert path.read_bytes() == before
