"""魔改 AVD 更新的宿主装配：读取当前配置、查询实例与发布进度。"""

from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.models.schema import WSAvdUpdateProgressData
from app.utils import emulator2 as _utils_emulator2

from .config import Config
from .ws import Publisher, protocol


def _settings() -> _utils_emulator2.avd.updater.UpdateSettings:
    # 每个检查 / 选包步骤读取当前设置，切换更新源仍会使更新器的检查缓存失效。
    return _utils_emulator2.avd.updater.UpdateSettings(
        github_only=Config.setting.Update.Source == "GitHub",
        automas_version=Config.VERSION,
        mirror_cdk=str(Config.setting.Update.MirrorChyanCDK or "").strip(),
    )


def _managed_roots() -> list[Path]:
    return _utils_emulator2.avd.service.managed_roots(
        list(Config.EmulatorConfig.values())
    )


async def _publish_progress(
    root: Path, progress: _utils_emulator2.avd.updater.UpdateProgress
) -> None:
    await Publisher.send(
        id=protocol.ID_EMULATOR_MANAGER,
        type=protocol.AVD_UPDATE_PROGRESS,
        data=WSAvdUpdateProgressData(root=str(root), **asdict(progress)),
    )


_HOST = _utils_emulator2.avd.updater.UpdateHost(
    settings=_settings,
    proxy=lambda: Config.proxy,
    managed_roots=_managed_roots,
    running_instances=_utils_emulator2.avd.manager.running_instances,
    opening_instances=_utils_emulator2.avd.manager.opening_instances,
    publish_progress=_publish_progress,
)


async def status(root: str, *, check: bool = False) -> dict[str, Any]:
    return await _utils_emulator2.avd.updater.status(root, check=check, host=_HOST)


async def update(root: str) -> dict[str, Any]:
    return await _utils_emulator2.avd.updater.update(root, host=_HOST)


async def startup() -> None:
    await _utils_emulator2.avd.updater.startup(host=_HOST)
