"""托管与账号共用的游戏目标；账号未选择时继承托管目标。"""

from dataclasses import dataclass
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, ValidationInfo, field_validator

from app.config import (
    ConfigEntry,
    ConfigGroup,
    NodeState,
    UiVisibility,
    config_manager,
    ref,
    select,
    ui,
)
from app.config.fields.ref import RefDeleteAction


@dataclass(frozen=True)
class GameBindingCapabilities:
    supported: bool = True
    account_override_supported: bool = True
    kinds: tuple[str, ...] = ()


async def clear_deleted_target(entry, event):
    await entry.update(
        type(entry).model_validate(
            {"game": {"game_id": "-", "device_id": "-", "unavailable_reason": ""}}
        )
    )


class GameBinding(ConfigGroup):
    unavailable_reason: Annotated[str, ui(visibility=UiVisibility.DISABLE)] = Field(
        default="", description="升级时无法解析的目标，需重新选择"
    )
    game_id: Annotated[
        UUID | Literal["-"],
        ref(
            "games",
            default="-",
            on_delete=RefDeleteAction.CUSTOM,
            on_delete_callback=clear_deleted_target,
        ),
        select(endpoint="/api/plugin/options/games"),
    ] = Field(default="-", description="游戏目标；账号留空时继承托管")
    device_id: Annotated[
        UUID | Literal["-"],
        select(endpoint="/api/plugin/options/devices"),
        ui(deps=["game.game_id"]),
    ] = Field(default="-", description="所选游戏的设备")

    @field_validator("device_id")
    @classmethod
    def validate_device(cls, value, info: ValidationInfo):
        entry = (info.context or {}).get("entry")
        if (
            value == "-"
            or entry is None
            or entry.activation_state == NodeState.INACTIVE
        ):
            return value
        game_id = info.data.get("game_id")
        if game_id is None or game_id == "-":
            raise ValueError("选择设备前须先选择游戏目标")
        game = config_manager.get_collection("games").get(game_id)
        if game is None or value not in game.devices:
            raise ValueError("设备不属于所选游戏目标")
        return value


class GameBindingOwner(ConfigEntry):
    game: GameBinding = Field(default_factory=GameBinding, description="游戏与设备")

    async def update(self, other: Self, *, check_visibility: bool = True) -> None:
        if (
            "game" in other.model_fields_set
            and "game_id" in other.game.model_fields_set
            and other.game.game_id == "-"
            and self.game.unavailable_reason
        ):
            # 历史坏引用的目标已是「-」，复位时不会触发目标变化信号。
            async with config_manager.transaction():
                await super().update(other, check_visibility=check_visibility)
                self.game.unavailable_reason = ""
                await self.commit()
            return
        await super().update(other, check_visibility=check_visibility)

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs):
        super().__pydantic_init_subclass__(**kwargs)
        cls.connect(
            GameBindingOwner.on_target_changed,
            phase="runtime",
            group="game",
            field="game_id",
        )

    @staticmethod
    async def on_target_changed(sender, event):
        if sender.game.game_id != "-" and sender.game.unavailable_reason:
            sender.game.unavailable_reason = ""
            await sender.commit()
