"""游戏中心 API。

路由仅负责契约转换与错误收敛；持久化和 provider 调用由服务层完成。
"""

from __future__ import annotations

from typing import Literal, Optional, cast

from fastapi import APIRouter, Body
from pydantic import BaseModel, Field

from app.models.game_center import (
    StoredGame,
    StoredGameDataPatch,
    StoredGameInfoPatch,
    StoredGamePatch,
    StoredGameTask,
)
from app.models.schema import (
    GameAddIn,
    GameCheckOut,
    GameConfig,
    GameConfig_Cache,
    GameConfig_Data,
    GameConfig_Info,
    GameConfigIndexItem,
    GameCreateOut,
    GameDeleteIn,
    GameGetIn,
    GameGetOut,
    GameOperationOut,
    GamePresetItem,
    GamePresetsOut,
    GameProviderItem,
    GameProvidersOut,
    GameReorderIn,
    GameUpdateIn,
    OutBase,
)
from app.plugins import PluginManager
from app.services.game_center import (
    GameCenterError,
    GameCenterService,
    get_default_game_center_service,
)
from app.utils import get_logger


logger = get_logger("游戏中心API")
router = APIRouter(prefix="/api/game_center", tags=["游戏中心"])


class GameActionIn(BaseModel):
    gameId: str = Field(..., description="游戏 UUID")
    expectedRevision: int = Field(..., ge=1, description="期望的游戏配置版本")


class GameTaskCancelIn(GameActionIn):
    expectedTaskId: str = Field(..., min_length=1, description="期望取消的任务 UUID")


class GameTaskStatusIn(BaseModel):
    gameId: str = Field(..., description="游戏 UUID")


class GameTaskStatusOut(OutBase):
    running: bool = Field(default=False, description="任务是否仍在运行")
    taskId: str = Field(default="", description="任务 UUID")
    gameId: str = Field(default="", description="游戏 UUID")
    action: Literal["install_or_update"] = "install_or_update"
    taskStatus: Optional[
        Literal["running", "handed_off", "completed", "failed", "cancelled"]
    ] = None
    phase: Optional[
        Literal[
            "queued",
            "handoff",
            "download",
            "verify",
            "patch",
            "install",
            "awaiting_user",
            "completed",
            "failed",
            "cancelled",
        ]
    ] = None
    percent: float = Field(default=0.0, ge=0.0, le=100.0)
    downloaded: int = Field(default=0, ge=0)
    total: int = Field(default=0, ge=0)
    speed: float = Field(default=0.0, ge=0.0)
    detail: str = ""
    startedAt: Optional[str] = None
    updatedAt: Optional[str] = None
    finishedAt: Optional[str] = None


def _get_game_center_service() -> GameCenterService:
    service = PluginManager.service.get("game_center")
    if service is None:
        service = get_default_game_center_service()
    if not isinstance(service, GameCenterService):
        raise RuntimeError("game_center 服务类型不正确")
    return cast(GameCenterService, service)


def _error(exc: Exception) -> tuple[int, str]:
    if isinstance(exc, GameCenterError):
        return exc.code, exc.message
    logger.exception("游戏中心 API 发生未处理错误")
    return 500, "游戏中心内部错误"


def _to_api_game(game: StoredGame) -> GameConfig:
    return GameConfig(
        Info=GameConfig_Info.model_validate(game.Info.model_dump()),
        Data=GameConfig_Data.model_validate(game.Data.model_dump()),
        Cache=GameConfig_Cache.model_validate(game.Cache.model_dump()),
        Revision=game.Revision,
    )


def _to_patch(data: GameConfig) -> StoredGamePatch:
    if "Cache" in data.model_fields_set or "Revision" in data.model_fields_set:
        raise GameCenterError(400, "Cache 和 Revision 为只读字段")
    info = (
        StoredGameInfoPatch.model_validate(data.Info.model_dump(exclude_unset=True))
        if data.Info is not None
        else None
    )
    game_data = (
        StoredGameDataPatch.model_validate(data.Data.model_dump(exclude_unset=True))
        if data.Data is not None
        else None
    )
    return StoredGamePatch(Info=info, Data=game_data)


def _to_task_status(
    game_id: str,
    task: StoredGameTask | None,
) -> GameTaskStatusOut:
    if task is None:
        return GameTaskStatusOut(gameId=game_id)
    return GameTaskStatusOut(
        running=task.status == "running",
        taskId=task.task_id,
        gameId=task.game_id,
        action=task.action,
        taskStatus=task.status,
        phase=task.phase,
        percent=task.percent,
        downloaded=task.downloaded,
        total=task.total,
        speed=task.speed,
        detail=task.message,
        startedAt=task.started_at,
        updatedAt=task.updated_at,
        finishedAt=task.finished_at,
    )


@router.post("/get", response_model=GameGetOut, summary="查询游戏配置")
async def get_games(payload: GameGetIn = Body(default_factory=GameGetIn)) -> GameGetOut:
    try:
        index, games = await _get_game_center_service().get_games(payload.gameId)
        return GameGetOut(
            index=[GameConfigIndexItem(uid=game_id) for game_id in index],
            data={game_id: _to_api_game(game) for game_id, game in games.items()},
        )
    except Exception as exc:
        code, message = _error(exc)
        return GameGetOut(code=code, status="error", message=message)


@router.post("/add", response_model=GameCreateOut, summary="添加游戏配置")
async def add_game(payload: GameAddIn = Body(default_factory=GameAddIn)) -> GameCreateOut:
    try:
        game = await _get_game_center_service().add_game(
            _to_patch(payload.data),
            preset_key=payload.preset,
        )
        return GameCreateOut(gameId=game.game_id, data=_to_api_game(game))
    except Exception as exc:
        code, message = _error(exc)
        return GameCreateOut(code=code, status="error", message=message)


@router.post("/update", response_model=GameCreateOut, summary="更新游戏配置")
async def update_game(payload: GameUpdateIn = Body(...)) -> GameCreateOut:
    try:
        game = await _get_game_center_service().update_game(
            payload.gameId,
            _to_patch(payload.data),
            expected_revision=payload.expectedRevision,
        )
        return GameCreateOut(gameId=game.game_id, data=_to_api_game(game))
    except Exception as exc:
        code, message = _error(exc)
        return GameCreateOut(code=code, status="error", message=message)


@router.post("/delete", response_model=OutBase, summary="删除游戏配置")
async def delete_game(payload: GameDeleteIn = Body(...)) -> OutBase:
    try:
        await _get_game_center_service().delete_game(
            payload.gameId,
            expected_revision=payload.expectedRevision,
        )
        return OutBase()
    except Exception as exc:
        code, message = _error(exc)
        return OutBase(code=code, status="error", message=message)


@router.post("/order", response_model=OutBase, summary="重新排序游戏配置")
async def reorder_games(payload: GameReorderIn = Body(...)) -> OutBase:
    try:
        await _get_game_center_service().reorder_games(payload.indexList)
        return OutBase()
    except Exception as exc:
        code, message = _error(exc)
        return OutBase(code=code, status="error", message=message)


@router.post("/providers", response_model=GameProvidersOut, summary="发现游戏 provider")
async def list_providers() -> GameProvidersOut:
    try:
        providers = [
            GameProviderItem(
                name=item.provider.descriptor.name,
                displayName=item.provider.descriptor.display_name,
                platforms=sorted(item.provider.descriptor.platforms),
                capabilities=sorted(item.provider.descriptor.capabilities),
                owner=item.owner,
            )
            for item in _get_game_center_service().list_providers()
        ]
        return GameProvidersOut(providers=providers)
    except Exception as exc:
        code, message = _error(exc)
        return GameProvidersOut(code=code, status="error", message=message)


@router.post("/presets", response_model=GamePresetsOut, summary="列出游戏创建预设")
async def list_presets() -> GamePresetsOut:
    try:
        presets = [
            GamePresetItem(
                key=item.key,
                name=item.name,
                platform=item.platform,
                provider=item.provider,
                executable=item.executable,
                packageName=item.package_name,
            )
            for item in _get_game_center_service().list_presets()
        ]
        return GamePresetsOut(presets=presets)
    except Exception as exc:
        code, message = _error(exc)
        return GamePresetsOut(code=code, status="error", message=message)


@router.post("/check", response_model=GameCheckOut, summary="检查游戏安装与版本")
async def check_game(payload: GameActionIn = Body(...)) -> GameCheckOut:
    try:
        result = await _get_game_center_service().check_game(
            payload.gameId,
            expected_revision=payload.expectedRevision,
        )
        return GameCheckOut(
            local_version=result.local_version,
            latest_version=result.latest_version,
            needs_update=result.needs_update,
            installed=result.installed,
        )
    except Exception as exc:
        code, message = _error(exc)
        return GameCheckOut(code=code, status="error", message=message)


@router.post(
    "/install",
    response_model=GameTaskStatusOut,
    summary="启动游戏安装或更新任务",
)
async def install_game(payload: GameActionIn = Body(...)) -> GameTaskStatusOut:
    try:
        task = await _get_game_center_service().start_install_or_update(
            payload.gameId,
            expected_revision=payload.expectedRevision,
        )
        return _to_task_status(payload.gameId, task)
    except Exception as exc:
        code, message = _error(exc)
        return GameTaskStatusOut(
            code=code,
            status="error",
            message=message,
            gameId=payload.gameId,
        )


@router.post(
    "/cancel",
    response_model=GameTaskStatusOut,
    summary="取消游戏安装或更新任务",
)
async def cancel_game(payload: GameTaskCancelIn = Body(...)) -> GameTaskStatusOut:
    try:
        task = await _get_game_center_service().cancel_operation(
            payload.gameId,
            expected_task_id=payload.expectedTaskId,
            expected_revision=payload.expectedRevision,
        )
        return _to_task_status(payload.gameId, task)
    except Exception as exc:
        code, message = _error(exc)
        return GameTaskStatusOut(
            code=code,
            status="error",
            message=message,
            gameId=payload.gameId,
        )


@router.post(
    "/task_status",
    response_model=GameTaskStatusOut,
    summary="查询游戏安装或更新任务",
)
async def task_status(payload: GameTaskStatusIn = Body(...)) -> GameTaskStatusOut:
    try:
        tasks = await _get_game_center_service().get_operation_tasks(payload.gameId)
        return _to_task_status(payload.gameId, tasks.get(payload.gameId))
    except Exception as exc:
        code, message = _error(exc)
        return GameTaskStatusOut(
            code=code,
            status="error",
            message=message,
            gameId=payload.gameId,
        )


@router.post("/launch", response_model=GameOperationOut, summary="启动游戏")
async def launch_game(payload: GameActionIn = Body(...)) -> GameOperationOut:
    try:
        provider = await _get_game_center_service().launch_game(
            payload.gameId,
            expected_revision=payload.expectedRevision,
        )
        return GameOperationOut(provider=provider)
    except Exception as exc:
        code, message = _error(exc)
        return GameOperationOut(code=code, status="error", message=message)


@router.post("/close", response_model=GameOperationOut, summary="关闭游戏")
async def close_game(payload: GameActionIn = Body(...)) -> GameOperationOut:
    try:
        provider = await _get_game_center_service().close_game(
            payload.gameId,
            expected_revision=payload.expectedRevision,
        )
        return GameOperationOut(provider=provider)
    except Exception as exc:
        code, message = _error(exc)
        return GameOperationOut(code=code, status="error", message=message)


__all__ = ["router"]
