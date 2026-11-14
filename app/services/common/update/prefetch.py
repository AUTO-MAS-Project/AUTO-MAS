"""托管准备只读复用下载中心产物；改写和安装总是使用调用方副本。"""

import asyncio
import shutil
from contextvars import ContextVar
from pathlib import Path

prefetch_paths: ContextVar[dict[str, str]] = ContextVar("prefetch_paths", default={})


async def copy_prefetched(url: str, destination: Path) -> bool:
    """将当前任务的预下载产物复制到调用方目录，保留共享缓存原文件。

    收到取消时先等待复制线程停止写入，再向调用方传播取消。

    Returns:
        成功复制返回 True；未登记对应 URL 或缓存文件已不存在时返回 False，
        由调用方继续正常下载。
    """
    source = prefetch_paths.get().get(url)
    if source is None or not Path(source).is_file():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    worker = asyncio.create_task(
        asyncio.to_thread(shutil.copyfile, source, destination)
    )
    try:
        await asyncio.shield(worker)
    except asyncio.CancelledError:
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                continue
        worker.result()
        raise
    return True
