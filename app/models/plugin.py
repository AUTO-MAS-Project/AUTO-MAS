from __future__ import annotations

import json
from typing import Any, cast

from pydantic import BaseModel, Field

from app.core.config.pydantic import PydanticConfigBase
from app.core.config.types import JsonDictString


class PluginInstanceConfig(PydanticConfigBase):
    """插件实例配置"""

    class InfoModel(BaseModel):
        Plugin: str = ""
        Id: str = ""
        Name: str = "新插件实例"
        Enabled: bool = True

    class DataModel(BaseModel):
        Config: JsonDictString = Field(default="{ }")

        def config_dict(self) -> dict[str, Any]:
            try:
                parsed = json.loads(self.Config)
            except json.JSONDecodeError:
                return {}

            return cast(dict[str, Any], parsed) if isinstance(parsed, dict) else {}

    Info: InfoModel = Field(default_factory=InfoModel)
    Data: DataModel = Field(default_factory=DataModel)
