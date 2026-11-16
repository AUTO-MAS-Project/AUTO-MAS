"""业务配置的历史文档转换入口。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.config import ConfigEntry


class DomainEntry(ConfigEntry):
    """在新框架激活前完成历史分组、旧字段与旧默认值转换。"""

    @classmethod
    def normalize_payload(cls, data: dict[str, Any]) -> dict[str, Any]:
        return deepcopy(data)

    async def _activate_from_payload(
        self, payload: dict[str, Any], *, regenerate_uuids: bool = False
    ) -> None:
        await super()._activate_from_payload(
            type(self).normalize_payload(payload), regenerate_uuids=regenerate_uuids
        )
