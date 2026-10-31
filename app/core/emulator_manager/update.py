"""魔改 AVD 更新的宿主装配：读取当前配置、查询实例与发布进度。"""

from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.core import Config, Publisher
from app.core.ws import protocol
from app.models.schema import WSAvdUpdateProgressData
from app.utils import emulator2 as _utils_emulator2


class AvdUpdateOperations:
    def __init__(self) -> None:
        self._HOST = _utils_emulator2.avd.updater.UpdateHost(
            settings=self._avd_update_settings,
            proxy=lambda: Config.proxy,
            managed_roots=self._avd_managed_roots,
            running_instances=_utils_emulator2.avd.manager.running_instances,
            opening_instances=_utils_emulator2.avd.manager.opening_instances,
            publish_progress=self._publish_avd_progress,
        )

    def _avd_update_settings(self) -> _utils_emulator2.avd.updater.UpdateSettings:
        # 每个检查 / 选包步骤读取当前设置，切换更新源仍会使更新器的检查缓存失效。
        return _utils_emulator2.avd.updater.UpdateSettings(
            github_only=Config.setting.Update.Source == "GitHub",
            automas_version=Config.VERSION,
            mirror_cdk=str(Config.setting.Update.MirrorChyanCDK or "").strip(),
        )

    def _avd_managed_roots(self) -> list[Path]:
        return _utils_emulator2.avd.service.managed_roots(
            list(Config.EmulatorConfig.values())
        )

    async def _publish_avd_progress(
        self, root: Path, progress: _utils_emulator2.avd.updater.UpdateProgress
    ) -> None:
        await Publisher.send(
            id=protocol.ID_EMULATOR_MANAGER,
            type=protocol.AVD_UPDATE_PROGRESS,
            data=WSAvdUpdateProgressData(root=str(root), **asdict(progress)),
        )

    async def avd_update_status(
        self, root: str, *, check: bool = False
    ) -> dict[str, Any]:
        return await _utils_emulator2.avd.updater.status(
            root, check=check, host=self._HOST
        )

    async def update_avd(self, root: str) -> dict[str, Any]:
        return await _utils_emulator2.avd.updater.update(root, host=self._HOST)

    async def startup_avd_update(self) -> None:
        await _utils_emulator2.avd.updater.startup(host=self._HOST)
