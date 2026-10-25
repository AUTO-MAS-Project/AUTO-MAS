"""魔改 AVD 更新的宿主装配：读取当前配置、查询实例与发布进度。"""

from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.models.schema import WSAvdUpdateProgressData
from app.utils.emulator2.avd import manager, service, updater

from .config import Config
from .ws import Publisher, protocol


def _settings() -> updater.UpdateSettings:
    # 每个检查 / 选包步骤读取当前设置，切换更新源仍会使更新器的检查缓存失效。
    return updater.UpdateSettings(
        github_only=Config.setting.Update.Source == "GitHub",
        automas_version=Config.VERSION,
        mirror_cdk=str(Config.setting.Update.MirrorChyanCDK or "").strip(),
    )


def _managed_roots() -> list[Path]:
    return service.managed_roots(list(Config.EmulatorConfig.values()))


async def _publish_progress(root: Path, progress: updater.UpdateProgress) -> None:
    await Publisher.send(
        id=protocol.ID_EMULATOR_MANAGER,
        type=protocol.AVD_UPDATE_PROGRESS,
        data=WSAvdUpdateProgressData(root=str(root), **asdict(progress)),
    )


_HOST = updater.UpdateHost(
    settings=_settings,
    proxy=lambda: Config.proxy,
    managed_roots=_managed_roots,
    running_instances=manager.running_instances,
    opening_instances=manager.opening_instances,
    publish_progress=_publish_progress,
)


async def status(root: str, *, check: bool = False) -> dict[str, Any]:
    return await updater.status(root, check=check, host=_HOST)


async def update(root: str) -> dict[str, Any]:
    return await updater.update(root, host=_HOST)


async def startup() -> None:
    await updater.startup(host=_HOST)
