"""配置基类 v2 参考示例（snake_case 字段名）。"""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal
from uuid import UUID

from pydantic import Field

from app.config import (
    ConfigCollection,
    ConfigEntry,
    ConfigGroup,
    ConfigTableColumn,
    Trigger,
    TriggerDecl,
    Virtual,
)
from app.config.shortcuts import collection, ref, trigger_field, virtual_field
from app.config.types import UrlString


class ExampleWebhook(ConfigEntry):
    """单文档配置示例。"""

    class Info(ConfigGroup):
        name: str = "示例 Webhook"
        enabled: bool = True

    class Data(ConfigGroup):
        url: UrlString = ""
        method: Literal["POST", "GET"] = "POST"

    info: Info = Field(default_factory=Info)
    data: Data = Field(default_factory=Data)


class ExampleScript(ConfigEntry):
    """脚本配置；作为 ``ExampleQueueItem`` 的外键目标。"""

    class Info(ConfigGroup):
        name: str = "示例脚本"
        status: Virtual[str] = None
        refresh: Trigger = False
        # 下拉组合按钮：Literal 触发值传给 handler
        action: Annotated[Literal["ping", "reset"] | None, TriggerDecl()] = None

    info: Info = Field(default_factory=Info)

    @virtual_field("info.status")
    def compute_status(self) -> str:
        return "enabled" if self.info.name else "disabled"

    @trigger_field("info.refresh")
    def on_refresh(self) -> None:
        _ = self.info.name

    @trigger_field("info.action")
    def on_action(self, value: Literal["ping", "reset"]) -> None:
        _ = (self.info.name, value)


class DeviceCol(ConfigTableColumn):
    """表格列：同 Entry 上多个 DeviceCol 字段合成一表。"""

    _table_key: ClassVar[str | None] = "devices"
    _table_transpose: ClassVar[bool] = False
    name: str = ""
    enabled: bool = True


class ExampleDeviceMatrix(ConfigEntry):
    """表格样式示例。"""

    left: DeviceCol = Field(default_factory=DeviceCol)
    right: DeviceCol = Field(default_factory=DeviceCol)


class ExampleQueueItem(ConfigEntry):
    """队列项；``ref('example_scripts')`` 绑定到 ref 池中的脚本集合。"""

    class Info(ConfigGroup):
        script_id: Annotated[
            UUID | str,
            ref("example_scripts", default="-", allow_values=("-",)),
        ] = "-"

    info: Info = Field(default_factory=Info)


class ExampleQueue(ConfigEntry):
    """队列配置：嵌套 ``items``；脚本池在 ref 池单独维护。"""

    class Info(ConfigGroup):
        name: str = "示例队列"

    info: Info = Field(default_factory=Info)
    items: ConfigCollection[ExampleQueueItem] = collection(ExampleQueueItem)
