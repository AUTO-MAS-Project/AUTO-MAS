"""HSR 托管和原生用户的单轮历史结论。"""

from app.core.history import history_store
from app.core.ws import Publisher, protocol
from app.models.schema import HistoryWrite, WSTaskNoticeData
from app.utils import UTC4, get_logger

logger = get_logger("HSR 历史记录")


async def save_hsr_user_history(
    *, task_info, script_info, user_item, cancelled: bool
) -> None:
    records = []
    for started_at, log_item in user_item.iter_history_logs():
        if log_item.status in {
            "HSR 正常运行中",
            "HSR 脚本原生来源运行中",
            "未开始监看日志",
        }:
            log_item.status = "任务被用户手动中止" if cancelled else "HSR 用户未完成"
        status = (
            "success"
            if log_item.status
            in {"HSR 用户任务完成", "HSR 失败任务补跑完成", "HSR 脚本原生来源完成"}
            else "skipped"
            if log_item.status == "HSR 本轮无需执行，已跳过"
            else "cancelled"
            if log_item.status == "任务被用户手动中止"
            else "error"
        )
        records.append(
            HistoryWrite(
                time=started_at.astimezone(UTC4),
                username=user_item.name,
                script_name=script_info.name,
                status=status,
                message=log_item.status,
                logs="".join(log_item.content),
            )
        )
    if not records:
        return
    try:
        attachments = await task_info.collect_user_history_attachments(
            script_info, user_item
        )
        records[-1].attachments.extend(attachments)
    except Exception:
        logger.opt(exception=True).warning(
            "收集用户历史附件失败，继续保存日志与执行结果"
        )
    try:
        for record in records:
            try:
                await history_store.record(record)
            except Exception as error:
                logger.opt(exception=True).warning(f"保存历史失败：{error}")
                try:
                    await Publisher.send(
                        id=task_info.task_id,
                        type=protocol.TASK_NOTICE,
                        data=WSTaskNoticeData(
                            level="warning", message=f"历史记录保存失败：{error}"
                        ),
                    )
                except Exception:
                    logger.opt(exception=True).warning("发送历史保存失败提示时出现异常")
    finally:
        await task_info.discard_user_history_capture(script_info, user_item)
