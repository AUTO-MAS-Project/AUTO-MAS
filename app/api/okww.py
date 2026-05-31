#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

from fastapi import APIRouter, Body
from pydantic import BaseModel, Field

from app.task.Okww.wuthering_game_path import validate_wuthering_game_root_selection

router = APIRouter(prefix="/api/okww", tags=["OK-WW 专项"])


class OkwwValidateGameRootIn(BaseModel):
    pickedFolder: str = Field(..., description="用户选择的文件夹路径")


class OkwwValidateGameRootOut(BaseModel):
    valid: bool
    message: str = ""


@router.post(
    "/validate-game-root",
    summary="校验鸣潮游戏根目录（Okww 专项）",
    response_model=OkwwValidateGameRootOut,
    status_code=200,
)
async def validate_game_root(
    body: OkwwValidateGameRootIn = Body(...),
) -> OkwwValidateGameRootOut:
    valid, message = validate_wuthering_game_root_selection(body.pickedFolder)
    return OkwwValidateGameRootOut(valid=valid, message=message)
