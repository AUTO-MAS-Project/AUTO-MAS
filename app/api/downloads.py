"""下载传输管理接口；应用退出 ALL 仅由宿主调用。"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.downloads import Downloads
from app.models.schema import DownloadRequest, DownloadSnapshot, OutBase
from app.utils.common.fluxdown_cli import FluxdownCancelUnconfirmed


class DownloadAcquireIn(BaseModel):
    owner: str
    request: DownloadRequest


class DownloadReleaseIn(BaseModel):
    owner: str
    url: str


class DownloadListIn(BaseModel):
    owner: str | None = None


class DownloadAcquireOut(OutBase):
    accepted: bool = False
    data: DownloadSnapshot | None = None


class DownloadOut(OutBase):
    data: DownloadSnapshot


class DownloadListOut(OutBase):
    data: list[DownloadSnapshot] = Field(default_factory=list)


router = APIRouter(prefix="/api/download", tags=["下载管理"])


@router.post("/request", response_model=DownloadAcquireOut)
async def request_download(body: DownloadAcquireIn) -> DownloadAcquireOut:
    """申请指定身份的下载并登记使用者，返回受理结果和当前状态；取消未确认或中心不可用时返回对应错误。"""
    try:
        accepted = Downloads.request(body.request, owner=body.owner)
        return DownloadAcquireOut(accepted=accepted, data=Downloads.query(body.request))
    except FluxdownCancelUnconfirmed:
        return DownloadAcquireOut(
            code=409, status="error", message="download_writer_unconfirmed"
        )
    except RuntimeError as error:
        return DownloadAcquireOut(code=503, status="error", message=str(error))


@router.post("/query", response_model=DownloadOut)
async def query_download(body: DownloadRequest) -> DownloadOut:
    """查询指定 URL 与文件身份的下载快照，返回状态、进度及成功产物路径。"""
    return DownloadOut(data=Downloads.query(body))


@router.post("/wait", response_model=DownloadOut)
async def wait_download(body: DownloadRequest) -> DownloadOut:
    """等待指定下载结束并返回结果快照，失败或取消通过快照状态交给前端处理。"""
    return DownloadOut(data=await Downloads.wait(body))


@router.post("/list", response_model=DownloadListOut)
async def list_downloads(body: DownloadListIn) -> DownloadListOut:
    """按可选使用者筛选下载记录，返回各任务的最新状态。"""
    return DownloadListOut(data=Downloads.list(owner=body.owner))


@router.post("/release", response_model=OutBase)
async def release_download(body: DownloadReleaseIn) -> OutBase:
    """释放使用者对 URL 的引用；最后一个使用者释放时取消未完成下载，并反馈停写是否确认。"""
    if not await Downloads.release(body.url, owner=body.owner):
        return OutBase(code=409, status="error", message="download_writer_unconfirmed")
    return OutBase()
