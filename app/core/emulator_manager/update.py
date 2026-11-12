"""ModAVD 更新的宿主装配：读取当前配置、代理环境、正在开机的实例与发布进度。"""

from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.config import EncryptedValue
from app.core import Config, Publisher
from app.core.ws import protocol
from app.models.schema import WSAvdUpdateProgressData
from app.utils import emulator2 as _utils_emulator2
from app.utils.common.proxy_env import proxy_environment

_DPAPI_PREFIX = "DPAPI:"


def _mirror_cdk_dpapi() -> str:
    """MAS 全局 Mirror 酱 CDK 的 DPAPI 密文（base64，去掉 ``DPAPI:`` 前缀），原样交给 modavd，不解密。"""
    stored = getattr(Config.setting.effective, "Update").__dict__.get("MirrorChyanCDK")
    if not isinstance(stored, EncryptedValue):
        return ""
    return stored.ciphertext().removeprefix(_DPAPI_PREFIX).strip()


class AvdUpdateOperations:
    def __init__(self) -> None:
        self._HOST = _utils_emulator2.avd.updater.UpdateHost(
            settings=self._avd_update_settings,
            environment=lambda: proxy_environment(Config.proxy),
            managed_roots=self._avd_managed_roots,
            opening_instances=_utils_emulator2.avd.manager.opening_instances,
            publish_progress=self._publish_avd_progress,
        )

    def _avd_update_settings(self) -> _utils_emulator2.avd.updater.UpdateSettings:
        # 每一步都读当前设置：更新源一改，之前查到的最新版本就作废。
        github = Config.setting.Update.Source == "GitHub"
        return _utils_emulator2.avd.updater.UpdateSettings(
            source="github" if github else "mirrorchyan",
            automas_version=Config.VERSION,
            # 更新源选 GitHub 时不用 CDK（和以前一样），显式传空串，modavd 也就不用它自己存的
            cdk_dpapi="" if github else _mirror_cdk_dpapi(),
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
