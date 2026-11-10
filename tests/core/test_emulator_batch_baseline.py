"""批量设置的守卫基准使用各设备实际保存的值。"""

import json
from pathlib import Path

import pytest
import yaml

from app.config import config_manager
from app.core.emulator_manager.operations import EmulatorOperations
from app.models.config import EmulatorConfig
from app.models.emulator import EmulatorRuntimePolicy
from app.utils.common.emulator2 import facade
from app.utils.common.emulator2.avd.constants import DISPLAY_PRESETS
from app.utils.common.emulator2.avd.manager import _AvdCore
from app.utils.common.emulator2.guard import dump_baselines
from app.utils.common.emulator2.slots import PathRecord, SlotTable
from tests.config_support import activate_config


class _FakeCli:
    """modavd 的最小替身：``info`` 报各实例的显示，``set --resolution`` 换档位、保持方向。"""

    def __init__(self, displays: dict[str, tuple[int, int, int]]) -> None:
        self.displays = displays

    async def info(self, index: str) -> dict:
        width, height, dpi = self.displays[str(index)]
        return {
            "index": int(index),
            "config": {"width": width, "height": height, "dpi": dpi},
        }

    async def set(self, index: str, *, resolution: int | None = None, **_) -> dict:
        if resolution is not None:
            width, height, dpi = DISPLAY_PRESETS[resolution]
            old_width, old_height, _ = self.displays[str(index)]
            if old_height > old_width:
                width, height = height, width
            self.displays[str(index)] = (width, height, dpi)
        return {"applied": {}}


@pytest.mark.asyncio
async def test_batch_baseline_keeps_applied_dpi_and_orientation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exe = tmp_path / "avd/sdk/emulator/emulator.exe"
    exe.parent.mkdir(parents=True)
    exe.touch()
    # 添加过的 ModAVD 根目录要有命令行 tools\modavd.exe（门面只看它在不在，不运行它）
    (exe.parents[2] / "tools").mkdir()
    (exe.parents[2] / "tools" / "modavd.exe").touch()
    # 两台 720p 实例，8 号是竖屏
    cli = _FakeCli({"7": (1280, 720, 240), "8": (720, 1280, 240)})
    backend = _AvdCore(exe, 60, False, cli=cli)  # type: ignore[arg-type]

    path = PathRecord.create(str(backend.root), "AVD", "avd", "0.37.1")
    slots = SlotTable()
    slots.sync_path(path.path_id, ["7", "8"])
    saved = tmp_path / "emulator.yaml"
    config = await activate_config(
        EmulatorConfig.model_validate(
            {
                "Info": {
                    "Type": "emulator2",
                    "ConfigGuard": True,
                    "Paths": facade.dump_paths([path]),
                    "Slots": slots.to_json(),
                }
            }
        ),
        saved,
    )

    async def build_backend(*args, **kwargs):
        return backend

    monkeypatch.setitem(facade._BACKEND_BUILDERS, "avd", build_backend)

    class Operations(EmulatorOperations):
        runtime_policy = EmulatorRuntimePolicy(lambda: True, lambda: False, tmp_path)

        def _emulator_config(self, emulator_id):
            return config

        async def _save_baselines(self, emulator_id, baselines):
            config.Info.Baselines = dump_baselines(baselines)
            await config.commit()

    operations = Operations()
    # Mixed-family batches use the standard emulator's 1080p DPI in the request.
    result = await operations.apply_settings_to_all(
        "emulator", {"width": 1920, "height": 1080, "dpi": 360}
    )
    assert (result["okCount"], result["failCount"]) == (2, 0)
    await config_manager.flush()
    config = await activate_config(
        EmulatorConfig.model_validate(yaml.safe_load(saved.read_text(encoding="utf-8")))
    )
    assert json.loads(config.Info.Baselines) == {
        "0": {"width": 1920, "height": 1080, "dpi": 280},
        "1": {"width": 1080, "height": 1920, "dpi": 280},
    }

    manager = await operations.build_manager("emulator")
    for slot in ("0", "1"):
        assert await manager.enforce_baseline(slot, "启动前") == []
    # Both instances drift to 720p. The persisted baseline must restore the preset.
    for index in ("7", "8"):
        await backend.write_instance_settings(index, {"width": 1280, "height": 720})
    for slot, width, height in (("0", 1920, 1080), ("1", 1080, 1920)):
        assert set(await manager.enforce_baseline(slot, "启动前")) == {
            "width",
            "height",
            "dpi",
        }
        values = (await manager.read_settings(slot)).values()
        assert {key: values[key] for key in ("width", "height", "dpi")} == {
            "width": width,
            "height": height,
            "dpi": 280,
        }
