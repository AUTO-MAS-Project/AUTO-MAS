import importlib
import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.core import Config
from app.core.script_types import script_type_registry
from app.models.script_api import ScriptTypeGetOut

router = APIRouter(prefix="/api/script-types", tags=["脚本类型"])


def _detect_icon_media_type(content: bytes, relative_path: str) -> str:
    """根据文件签名识别常用图标格式，扩展名仅作兼容回退。"""

    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith((b"\x00\x00\x01\x00", b"\x00\x00\x02\x00")):
        return "image/x-icon"

    media_type, _ = mimetypes.guess_type(relative_path)
    return media_type or "application/octet-stream"


@router.post("/get", summary="获取脚本类型描述", response_model=ScriptTypeGetOut)
async def get_script_types() -> ScriptTypeGetOut:
    try:
        data = await Config.get_script_type_descriptors()
    except Exception as e:
        return ScriptTypeGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {e}",
            data=[],
        )
    return ScriptTypeGetOut(data=data)


@router.get("/{type_key}/icon", summary="获取脚本类型图标")
async def get_script_type_icon(type_key: str) -> Response:
    """根据脚本类型键返回插件声明的图标资源。

    icon_path 格式为 ``package_name:relative/path``，例如
    ``automas_script_maafw_pack_m9a:assets/m9a.png``。
    """
    try:
        provider = script_type_registry.get(type_key)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"未注册的脚本类型: {type_key}")

    icon_path = provider.icon_path
    if not icon_path:
        raise HTTPException(status_code=404, detail=f"脚本类型 {type_key} 未声明图标资源")

    if ":" not in icon_path:
        raise HTTPException(status_code=404, detail=f"脚本类型 {type_key} 图标路径格式无效")

    package_name, relative_path = icon_path.split(":", 1)

    try:
        mod = importlib.import_module(package_name)
        mod_dir = Path(mod.__path__[0])
        icon_file = mod_dir / relative_path
        content = icon_file.read_bytes()
    except Exception:
        raise HTTPException(status_code=404, detail=f"图标资源不存在: {icon_path}")

    return Response(
        content=content,
        media_type=_detect_icon_media_type(content, relative_path),
    )
