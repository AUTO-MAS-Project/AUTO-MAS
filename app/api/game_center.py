#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.


from fastapi import APIRouter, Body

from app.plugins import PluginManager
from app.models.schema import (
    OutBase,
    GameConfig,
    GameConfigIndexItem,
    GameGetIn,
    GameGetOut,
    GameAddIn,
    GameCreateOut,
    GameUpdateIn,
    GameDeleteIn,
    GameReorderIn,
    GamePresetItem,
    GamePresetsOut,
    GameOperateIn,
    GameCheckOut,
    GameInstallLocalApkIn,
    GameTaskStatusOut,
)


def _get_game_center_service():
    service = PluginManager.service.get("game_center")
    if service is None:
        raise RuntimeError("game_center service is unavailable")
    return service


def _error_code(exc: Exception) -> int:
    return 503 if "service is unavailable" in str(exc) else 500


def _err(exc: Exception) -> str:
    return f"{type(exc).__name__}: {str(exc)}"


router = APIRouter(prefix="/api/game_center", tags=["游戏中心"])


@router.post(
    "/get",
    tags=["Get"],
    summary="查询游戏中心配置",
    response_model=GameGetOut,
    status_code=200,
)
async def get_game(game: GameGetIn = Body(...)) -> GameGetOut:
    try:
        index, data = await _get_game_center_service().get_config(game.gameId)
        index = [GameConfigIndexItem(**_) for _ in index]
        data = {uid: GameConfig(**cfg) for uid, cfg in data.items()}
    except Exception as e:
        return GameGetOut(
            code=_error_code(e), status="error", message=_err(e), index=[], data={}
        )
    return GameGetOut(index=index, data=data)


@router.post(
    "/add",
    tags=["Add"],
    summary="添加游戏项",
    response_model=GameCreateOut,
    status_code=200,
)
async def add_game(game: GameAddIn = Body(default=GameAddIn())) -> GameCreateOut:
    try:
        uid, config = await _get_game_center_service().add(game.preset)
        data = GameConfig(**(await config.toDict()))
    except Exception as e:
        return GameCreateOut(
            code=_error_code(e),
            status="error",
            message=_err(e),
            gameId="",
            data=GameConfig(**{}),
        )
    return GameCreateOut(gameId=str(uid), data=data)


@router.post(
    "/update",
    tags=["Update"],
    summary="更新游戏项",
    response_model=OutBase,
    status_code=200,
)
async def update_game(game: GameUpdateIn = Body(...)) -> OutBase:
    try:
        await _get_game_center_service().update(
            game.gameId, game.data.model_dump(exclude_unset=True)
        )
    except Exception as e:
        return OutBase(code=_error_code(e), status="error", message=_err(e))
    return OutBase()


@router.post(
    "/delete",
    tags=["Delete"],
    summary="删除游戏项",
    response_model=OutBase,
    status_code=200,
)
async def delete_game(game: GameDeleteIn = Body(...)) -> OutBase:
    try:
        await _get_game_center_service().delete(game.gameId)
    except Exception as e:
        return OutBase(code=_error_code(e), status="error", message=_err(e))
    return OutBase()


@router.post(
    "/order",
    tags=["Update"],
    summary="重新排序游戏项",
    response_model=OutBase,
    status_code=200,
)
async def reorder_game(game: GameReorderIn = Body(...)) -> OutBase:
    try:
        await _get_game_center_service().reorder(game.indexList)
    except Exception as e:
        return OutBase(code=_error_code(e), status="error", message=_err(e))
    return OutBase()


@router.post(
    "/presets",
    tags=["Get"],
    summary="获取内置游戏预设",
    response_model=GamePresetsOut,
    status_code=200,
)
async def get_presets() -> GamePresetsOut:
    try:
        presets = [
            GamePresetItem(**p) for p in _get_game_center_service().presets()
        ]
    except Exception as e:
        return GamePresetsOut(
            code=_error_code(e), status="error", message=_err(e), presets=[]
        )
    return GamePresetsOut(presets=presets)


# ======================== 操作类路由 ========================


@router.post(
    "/check",
    tags=["Update"],
    summary="检查游戏更新",
    response_model=GameCheckOut,
    status_code=200,
)
async def check_game(game: GameOperateIn = Body(...)) -> GameCheckOut:
    try:
        result = await _get_game_center_service().check(game.gameId)
        if result.get("code") != 200:
            return GameCheckOut(
                code=result.get("code", 500),
                status=result.get("status", "error"),
                message=result.get("message", ""),
            )
        return GameCheckOut(
            code=200,
            status="ok",
            local_version=result.get("local_version", ""),
            latest_version=result.get("latest_version", ""),
            needs_update=result.get("needs_update", False),
            installed=result.get("installed", False),
        )
    except Exception as e:
        return GameCheckOut(code=_error_code(e), status="error", message=_err(e))


@router.post(
    "/install",
    tags=["Update"],
    summary="安装或更新游戏 (后台任务)",
    response_model=OutBase,
    status_code=200,
)
async def install_game(game: GameOperateIn = Body(...)) -> OutBase:
    try:
        result = await _get_game_center_service().install(game.gameId)
        return OutBase(
            code=result.get("code", 500),
            status=result.get("status", "error"),
            message=result.get("message", ""),
        )
    except Exception as e:
        return OutBase(code=_error_code(e), status="error", message=_err(e))


@router.post(
    "/cancel",
    tags=["Update"],
    summary="取消安装/更新任务",
    response_model=OutBase,
    status_code=200,
)
async def cancel_game(game: GameOperateIn = Body(...)) -> OutBase:
    try:
        result = await _get_game_center_service().cancel(game.gameId)
        return OutBase(
            code=result.get("code", 200),
            status=result.get("status", "ok"),
            message=result.get("message", ""),
        )
    except Exception as e:
        return OutBase(code=_error_code(e), status="error", message=_err(e))


@router.post(
    "/launch",
    tags=["Update"],
    summary="启动游戏",
    response_model=OutBase,
    status_code=200,
)
async def launch_game(game: GameOperateIn = Body(...)) -> OutBase:
    try:
        result = await _get_game_center_service().launch(game.gameId)
        return OutBase(
            code=result.get("code", 500),
            status=result.get("status", "error"),
            message=result.get("message", ""),
        )
    except Exception as e:
        return OutBase(code=_error_code(e), status="error", message=_err(e))


@router.post(
    "/close",
    tags=["Update"],
    summary="关闭游戏",
    response_model=OutBase,
    status_code=200,
)
async def close_game(game: GameOperateIn = Body(...)) -> OutBase:
    try:
        result = await _get_game_center_service().close(game.gameId)
        return OutBase(
            code=result.get("code", 500),
            status=result.get("status", "error"),
            message=result.get("message", ""),
        )
    except Exception as e:
        return OutBase(code=_error_code(e), status="error", message=_err(e))


@router.post(
    "/open_official_launcher",
    tags=["Update"],
    summary="打开官方启动器 (鹰角回退)",
    response_model=OutBase,
    status_code=200,
)
async def open_official_launcher(game: GameOperateIn = Body(...)) -> OutBase:
    try:
        result = await _get_game_center_service().open_official_launcher(
            game.gameId
        )
        return OutBase(
            code=result.get("code", 500),
            status=result.get("status", "error"),
            message=result.get("message", ""),
        )
    except Exception as e:
        return OutBase(code=_error_code(e), status="error", message=_err(e))


@router.post(
    "/install_local_apk",
    tags=["Update"],
    summary="手动安装本地 APK (ADB 游戏)",
    response_model=OutBase,
    status_code=200,
)
async def install_local_apk(
    game: GameInstallLocalApkIn = Body(...),
) -> OutBase:
    try:
        result = await _get_game_center_service().install_local_apk(
            game.gameId, game.apkPath
        )
        return OutBase(
            code=result.get("code", 500),
            status=result.get("status", "error"),
            message=result.get("message", ""),
        )
    except Exception as e:
        return OutBase(code=_error_code(e), status="error", message=_err(e))


@router.post(
    "/task_status",
    tags=["Get"],
    summary="查询任务状态 (轮询兜底)",
    response_model=GameTaskStatusOut,
    status_code=200,
)
async def task_status(game: GameOperateIn = Body(...)) -> GameTaskStatusOut:
    try:
        result = _get_game_center_service().task_status(game.gameId)
        return GameTaskStatusOut(
            code=200,
            status="ok",
            running=result.get("running", False),
            phase=result.get("phase", ""),
            percent=result.get("percent", 0.0),
            downloaded=result.get("downloaded", 0),
            total=result.get("total", 0),
            speed=result.get("speed", 0.0),
            detail=result.get("detail", ""),
        )
    except Exception as e:
        return GameTaskStatusOut(
            code=_error_code(e), status="error", detail=_err(e)
        )
