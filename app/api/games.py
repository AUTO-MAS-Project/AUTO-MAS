"""插件游戏配置与设备管理入口，操作由配置管理器托管。"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field, SerializeAsAny

from app.config import CollectionOrderItem, ComponentHint, ConfigError, UiVisibility
from app.config.fields.hints import TriggerUiState
from app.config.wire import config_contract
from app.core import Config, GameManager, Plugin
from app.models.config.game import GameEntry
from app.models.config.plugin_emulator import EmulatorDeviceEntry
from app.models.emulator import SettingsConflictError
from app.models.schema import ConfigSnapshotOut, OutBase
from app.plugin.base.emulator import EmulatorControl
from app.plugin.base.game import GameAdapterPlugin
from app.utils import get_logger

logger = get_logger("游戏管理接口")


class GameTypeItem(BaseModel):
    type: str
    name: str
    configType: str
    kind: str


class GameTypesOut(ConfigSnapshotOut):
    data: list[GameTypeItem] = Field(default_factory=list)


class GameGetIn(BaseModel):
    gameId: UUID | None = None


class GameRuntimeData(BaseModel):
    actionHints: dict[str, list[ComponentHint]] = Field(default_factory=dict)
    deviceUsage: dict[str, str] = Field(default_factory=dict)
    recoveryPending: list[UUID] = Field(default_factory=list)
    maintenance: dict[str, Any] = Field(default_factory=dict)


class GameGetOut(ConfigSnapshotOut):
    order: list[CollectionOrderItem] = Field(default_factory=list)
    data: dict[str, SerializeAsAny[BaseModel]] = Field(default_factory=dict)
    runtime: dict[str, GameRuntimeData] = Field(default_factory=dict)


class GameCreateIn(BaseModel):
    type: str
    data: dict[str, Any] = Field(default_factory=dict)


class GameUpdateIn(BaseModel):
    gameId: UUID
    data: dict[str, Any]


class GameIdIn(BaseModel):
    gameId: UUID


class GameSearchOut(OutBase):
    data: dict[str, dict[str, Any]] = Field(default_factory=dict)


class GameDeviceIn(BaseModel):
    gameId: UUID
    deviceId: UUID


class GameDeviceUpdateIn(GameDeviceIn):
    data: dict[str, Any]


class GameSettingsIn(GameDeviceIn):
    changes: dict[str, int]
    expected: dict[str, int | None] | None = None


class GameSettingsOut(OutBase):
    data: dict[str, Any] = Field(default_factory=dict)


class GameBatchIn(GameIdIn):
    devices: list[UUID] | None = None


class GameBatchSettingsIn(GameBatchIn):
    changes: dict[str, int]


class GameBindingOptionsIn(BaseModel):
    scriptId: UUID
    userId: UUID | None = None


class GameBindingOption(BaseModel):
    value: UUID
    label: str
    disabledReason: str | None = None
    warning: str | None = None


class GameBindingOptionsOut(ConfigSnapshotOut):
    data: list[GameBindingOption] = Field(default_factory=list)
    supported: bool = True
    accountOverrideSupported: bool = True


class GameRoute(APIRoute):
    """把设备、配置与进程边界的失败交给管理页展示，保留统一响应包络。"""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def handle(request: Request):
            try:
                return await handler(request)
            except (HTTPException, RequestValidationError):
                raise
            except KeyError as error:
                result = OutBase(code=404, status="error", message=str(error))
            except (ValueError, ConfigError, SettingsConflictError) as error:
                result = OutBase(code=409, status="error", message=str(error))
            except Exception as error:
                logger.opt(exception=True).warning(f"游戏管理操作失败：{error}")
                result = OutBase(code=500, status="error", message=str(error))
            return JSONResponse(result.model_dump(mode="json"))

        return handle


router = APIRouter(prefix="/api/games", tags=["游戏与设备"], route_class=GameRoute)


@router.post("/binding/options", tags=["Get"], response_model=GameBindingOptionsOut)
async def game_binding_options(body: GameBindingOptionsIn) -> GameBindingOptionsOut:
    from app.models.script_access import script_users

    script = Config.ScriptConfig[body.scriptId]
    owner = script_users(script)[body.userId] if body.userId is not None else None
    capabilities = Config.script_game_binding(script, {})
    options = []
    if capabilities.supported and (
        owner is None or capabilities.account_override_supported
    ):
        for uid, entry in Config.GameConfig.items():
            hints: list[str] = []
            reason = await GameManager.validate_binding(
                str(body.scriptId),
                {"game": {"game_id": uid}},
                owner=owner,
                script=script,
                capabilities=capabilities,
                hints=hints,
            )
            options.append(
                GameBindingOption(
                    value=uid,
                    label=entry.info.name,
                    disabledReason=reason,
                    warning=None if reason else "；".join(hints) or None,
                )
            )
    return GameBindingOptionsOut(
        data=options,
        supported=capabilities.supported,
        accountOverrideSupported=capabilities.account_override_supported,
        uiSources=[
            Config.GameConfig.uid,
            script.uid,
            *([owner.uid] if owner is not None else []),
            Config.plugin_registry.uid,
        ],
    )


@router.post("/types", tags=["Get"], response_model=GameTypesOut)
async def game_types() -> GameTypesOut:
    return GameTypesOut(
        uiSources=[Config.plugin_registry.uid],
        data=[
            GameTypeItem(
                type=plugin_class.game_type_key,
                name=record.info.display_name or record.info.plugin_name,
                configType=Plugin.game_types[record.uid].game_class.__name__,
                kind=Plugin.game_types[record.uid]
                .game_class.Info.model_fields["type"]
                .default,
            )
            for record in Plugin.list_plugins()
            if record.uid in Plugin.game_types
            and (plugin_class := record._plugin_cls) is not None
            and issubclass(plugin_class, GameAdapterPlugin)
        ],
    )


def _action_hints(entry: GameEntry) -> dict[str, list[ComponentHint]]:
    """汇集配置原生触发器与游戏页专用 API 按钮的提示。"""
    control = entry._control
    capabilities = control.capabilities
    busy = entry.actions_busy
    can_edit_game = not (busy or entry.is_locked)
    game_hints = [
        hint
        for hint in entry._get_ui_hints().get("action", [])
        if hint.get("field") != "create_instance" or "create_instance" in capabilities
    ]
    game_hints.extend(
        {"field": field, "component": "button", "editable": can_edit_game}
        for field, supported in (
            ("save", True),
            ("delete", True),
            ("stable_mode", "stable_mode" in capabilities),
            ("capture", "settings" in capabilities),
        )
        if supported
    )
    result = {str(entry.uid): game_hints}
    for device in entry.devices.values():
        removed = getattr(device.info, "tombstone", False)
        device_hints = [
            hint
            for hint in device._get_ui_hints().get("action", [])
            if hint.get("state") == TriggerUiState.BUSY
            or (not removed and hint.get("field") in capabilities)
        ]
        if not removed:
            if "settings" in capabilities:
                device_hints.append(
                    {
                        "field": "settings",
                        "component": "button",
                        "editable": can_edit_game,
                    }
                )
            if "instance_options" in capabilities:
                device_hints.append(
                    {"field": "options", "component": "button", "editable": True}
                )
            if (
                isinstance(device, EmulatorDeviceEntry)
                and device._ui_visibility("info", "adb_address") == UiVisibility.SHOW
            ):
                device_hints.append(
                    {
                        "field": "connection",
                        "component": "button",
                        "editable": not (busy or device.is_locked)
                        and control.device_usage(device.uid) is None,
                    }
                )
        result[str(device.uid)] = device_hints
    return result


@router.post("/get", tags=["Get"], response_model=GameGetOut)
async def get_games(body: GameGetIn = Body(default_factory=GameGetIn)) -> GameGetOut:
    entries = (
        list(Config.GameConfig.items())
        if body.gameId is None
        else [(body.gameId, Config.GameConfig[body.gameId])]
    )
    data = {}
    runtime = {}
    order = []
    for uid, entry in entries:
        order.append(CollectionOrderItem(uid=uid, type=type(entry).__name__))
        data[str(uid)] = config_contract(
            type(entry), include_collections=True
        ).model_validate(entry.model_dump(context={"audience": "api"}))
        control = entry._control
        runtime[str(uid)] = GameRuntimeData(
            actionHints=_action_hints(entry),
            deviceUsage={
                str(d.uid): usage
                for d in entry.devices.values()
                if (usage := control.device_usage(d.uid)) is not None
            },
            recoveryPending=[
                d.uid for d in entry.devices.values() if control.recovery_pending(d.uid)
            ],
            maintenance=control.maintenance_snapshot,
        )
    return GameGetOut(
        order=order,
        data=data,
        runtime=runtime,
        uiSources=[body.gameId or Config.GameConfig.uid],
    )


@router.post("/create", tags=["Action"], response_model=GameGetOut)
async def create_game(body: GameCreateIn) -> GameGetOut:
    uid = await GameManager.create(body.type, body.data)
    return await get_games(GameGetIn(gameId=uid))


@router.post("/update", tags=["Update"], response_model=OutBase)
async def update_game(body: GameUpdateIn) -> OutBase:
    await GameManager.update(body.gameId, body.data)
    return OutBase()


@router.post("/device/update", tags=["Update"], response_model=OutBase)
async def update_game_device(body: GameDeviceUpdateIn) -> OutBase:
    await GameManager.update_device(body.gameId, body.deviceId, body.data)
    return OutBase()


@router.post("/delete", tags=["Delete"], response_model=OutBase)
async def delete_game(body: GameIdIn) -> OutBase:
    entry = Config.GameConfig[body.gameId]
    if entry.is_locked or entry.actions_busy:
        raise ValueError("游戏目标正在使用，不能删除")
    control = entry._control
    Config.GameConfig.remove(body.gameId)
    await Config.GameConfig.commit()
    try:
        await control.teardown()
    except Exception as error:
        logger.opt(exception=True).warning(
            f"游戏目标已删除，设备观察任务清理失败：{error}"
        )
    return OutBase()


@router.post("/search", tags=["Action"], response_model=GameSearchOut)
async def search_games() -> GameSearchOut:
    return GameSearchOut(data=await GameManager.search())


@router.post("/import", tags=["Action"], response_model=GameGetOut)
async def import_game(body: GameIdIn) -> GameGetOut:
    entry = await GameManager.add_found(body.gameId)
    return await get_games(GameGetIn(gameId=entry.uid))


@router.post("/settings/get", tags=["Get"], response_model=GameSettingsOut)
async def game_device_settings(body: GameDeviceIn) -> GameSettingsOut:
    control = Config.GameConfig[body.gameId]._control
    if not isinstance(control, EmulatorControl):
        raise ValueError("客户端不提供模拟器实例设置")
    return GameSettingsOut(data=(await control.read_settings(body.deviceId)).to_dict())


@router.post("/settings/update", tags=["Update"], response_model=GameSettingsOut)
async def update_game_settings(body: GameSettingsIn) -> GameSettingsOut:
    await GameManager.write_settings(
        body.gameId, body.deviceId, body.changes, body.expected
    )
    return await game_device_settings(
        GameDeviceIn(gameId=body.gameId, deviceId=body.deviceId)
    )


@router.post("/settings/batch", tags=["Update"], response_model=GameSettingsOut)
async def batch_game_settings(body: GameBatchSettingsIn) -> GameSettingsOut:
    return GameSettingsOut(
        data=await GameManager.configure_devices(
            body.gameId, "settings", devices=body.devices, changes=body.changes
        )
    )


@router.post("/stable-mode/apply", tags=["Action"], response_model=GameSettingsOut)
async def apply_stable_mode(body: GameBatchIn) -> GameSettingsOut:
    return GameSettingsOut(
        data=await GameManager.configure_devices(
            body.gameId, "stable_mode", devices=body.devices
        )
    )


@router.post("/guard/capture", tags=["Action"], response_model=GameSettingsOut)
async def capture_baselines(body: GameBatchIn) -> GameSettingsOut:
    return GameSettingsOut(
        data=await GameManager.configure_devices(
            body.gameId, "capture", devices=body.devices
        )
    )


@router.post("/device/options", tags=["Get"], response_model=GameSettingsOut)
async def device_options(body: GameDeviceIn) -> GameSettingsOut:
    control = Config.GameConfig[body.gameId]._control
    if not isinstance(control, EmulatorControl):
        raise ValueError("此目标不提供模拟器实例选项")
    return GameSettingsOut(data=await control.instance_options(body.deviceId))
