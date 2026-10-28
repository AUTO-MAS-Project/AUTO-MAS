"""用户历史收尾管线；存储、附件采集与任务反馈由宿主注入。"""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from app.models.schema import HistoryAttachmentInput, HistoryRecord, HistoryWrite
from app.utils import get_logger

logger = get_logger("任务历史")


@dataclass(frozen=True)
class UserHistoryDependencies:
    """绑定到本次用户执行的副作用，不持有任务或配置对象。"""

    record: Callable[[HistoryWrite], Awaitable[HistoryRecord]]
    collect_attachments: Callable[[], Awaitable[list[HistoryAttachmentInput]]]
    discard_capture: Callable[[], Awaitable[None]]
    report_failure: Callable[[str], Awaitable[None]]
    log_warning: Callable[[str], None]


async def save_user_history(
    records: Sequence[HistoryWrite], *, dependencies: UserHistoryDependencies
) -> None:
    """按原顺序保存历史，将采集附件追加到末条记录并最终释放采集副本。

    条目的判定、日志和已有附件由专项提供。本函数会追加末条记录的附件，
    不改变其余字段；附件或单条保存失败仍继续，取消向上传播且执行清理。
    空批次不采集、不落库，只释放已存在的采集副本。
    """

    try:
        if not records:
            return
        try:
            attachments = await dependencies.collect_attachments()
            records[-1].attachments.extend(attachments)
        except Exception as error:
            dependencies.log_warning(
                f"收集用户历史附件失败，继续保存日志与执行结果：{error}"
            )

        for record in records:
            try:
                await dependencies.record(record)
            except Exception as error:
                dependencies.log_warning(f"保存历史失败：{error}")
                try:
                    await dependencies.report_failure(f"历史记录保存失败：{error}")
                except Exception:
                    logger.opt(exception=True).warning("发送历史保存失败提示时出现异常")
    finally:
        await dependencies.discard_capture()
