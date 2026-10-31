"""通知渲染执行器：纯文本快路径与有界后台渲染共用同一内容契约。"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from weakref import WeakKeyDictionary

from app.core.notify import content as _notification_render
from app.models.notification import (
    NOTIFICATION_IMAGE_URI_PATTERN,
    DeferredContent,
    NotificationCapabilities,
    NotifyPayload,
    RenderedNotification,
    SummaryPolicy,
)


class AsyncNotificationRenderer:
    def __init__(self, *, workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="notification-render"
        )
        self._workers = workers
        self._slots: WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = (
            WeakKeyDictionary()
        )
        self._inflight: set[asyncio.Future[RenderedNotification]] = set()
        self._closed = False

    async def render(
        self,
        payload: NotifyPayload,
        capabilities: NotificationCapabilities,
        *,
        summary_policy: SummaryPolicy = "never",
        use_summary_title: bool = False,
    ) -> RenderedNotification:
        if self._closed:
            raise RuntimeError("通知渲染器已关闭")
        if (
            summary_policy == "preferred"
            and payload.summary is not None
            and payload.summary.text
        ):
            content = payload.summary.text
        else:
            content = None
            for content_format in capabilities.formats:
                content = getattr(payload, content_format, None)
                if content is not None:
                    break
        if (
            isinstance(content, str)
            and len(content) <= 8192
            and NOTIFICATION_IMAGE_URI_PATTERN.search(content) is None
            and (
                payload.images == ()
                or isinstance(payload.images, DeferredContent)
                and not capabilities.image_presentations
            )
        ):
            return _notification_render.render_for_target(
                payload,
                capabilities,
                summary_policy=summary_policy,
                use_summary_title=use_summary_title,
            )

        # 冷导入、模板编译及插件装配先在事件循环上完成，线程只生成内容。
        for content_format in capabilities.formats:
            content = getattr(payload, content_format, None)
            if isinstance(content, DeferredContent):
                content.prepare_for_render()
        if isinstance(payload.images, DeferredContent):
            payload.images.prepare_for_render()

        render = partial(
            _notification_render.render_for_target,
            payload,
            capabilities,
            summary_policy=summary_policy,
            use_summary_title=use_summary_title,
        )
        loop = asyncio.get_running_loop()
        slots = self._slots.get(loop)
        if slots is None:
            for previous in list(self._slots):
                if previous.is_closed():
                    del self._slots[previous]
            slots = asyncio.Semaphore(self._workers)
            self._slots[loop] = slots
        await slots.acquire()
        try:
            future = loop.run_in_executor(self._executor, render)
        except BaseException:
            slots.release()
            raise
        self._inflight.add(future)

        def completed(done: asyncio.Future[RenderedNotification]) -> None:
            self._inflight.discard(done)
            slots.release()
            if not done.cancelled():
                done.exception()

        future.add_done_callback(completed)
        # 取消等待不会取消实际线程；许可与句柄在底层工作真正结束时才回收。
        return await asyncio.shield(future)

    def close(self) -> None:
        """拒绝新工作；运行中的纯内容计算可结束，不再访问配置或传输资源。"""

        self._closed = True
        self._executor.shutdown(wait=False, cancel_futures=True)
