"""MFW 项目本地资源服务。

只服务一件事：把 MFW 项目目录内的图片按需读给前端。任务说明（interface 的
``doc`` / ``description``）是 markdown，里面的图片写的是**项目内相对路径**，
浏览器没法直接读本地文件，必须由后端转一手。

前端侧对应 ``buildMaaFWAssetUrl``：它已经拦掉了绝对路径、UNC、上跳与远程 URL，
但那只是省一次往返，安全边界在本模块 —— 请求可以绕过前端直接打过来。
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api/maafw", tags=["MFW"])

_MAAFW_IMAGE_SUFFIXES = {
    ".avif",
    ".bmp",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".png",
    ".svg",
    ".webp",
}
"""允许外发的图片后缀。

白名单而非黑名单：这个端点的 root 由请求方给定，等于把「读任意目录下的文件」
的能力暴露出去了，只能靠「必须在 root 内」+「必须是图片」两道闸门把它收窄成
「读项目内的图片」。放开成任意后缀就变成了任意文件读取。
"""


def _maafw_asset_file_path(root: str, asset_path: str) -> Path:
    """把 (项目根, 项目内相对路径) 解析成一个可安全外发的图片绝对路径。"""

    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise ValueError("MFW 项目目录不存在")

    normalized_asset_path = asset_path.replace("\\", "/").strip()
    relative_path = Path(normalized_asset_path)
    if (
        not normalized_asset_path
        or relative_path.is_absolute()
        or ".." in relative_path.parts
    ):
        raise ValueError("MFW 资源路径非法")

    file_path = (root_path / relative_path).resolve()
    # 逐段比对而不是比字符串前缀：符号链接与 ..（上面已挡）之外，
    # 大小写与短路径名的差异也会让前缀比较判错。
    if root_path not in file_path.parents:
        raise ValueError("MFW 资源路径越界")
    if file_path.suffix.casefold() not in _MAAFW_IMAGE_SUFFIXES:
        raise ValueError("仅支持 MFW 图片资源")
    if not file_path.is_file():
        raise FileNotFoundError("MFW 图片资源不存在")
    return file_path


@router.get("/asset", response_class=FileResponse)
async def get_maafw_asset(
    root: str = Query(..., description="MFW 项目根目录"),
    path: str = Query(..., description="项目根目录内的相对图片路径"),
) -> FileResponse:
    """读取 MFW 项目目录内的一张图片。"""

    try:
        file_path = _maafw_asset_file_path(root, path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(file_path)
