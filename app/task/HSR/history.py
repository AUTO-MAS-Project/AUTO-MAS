"""HSR 托管和原生用户的单轮历史结论。"""

from app.task.history import build_record, save_user_history


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
            build_record(
                script_info=script_info,
                user_info=user_item,
                started_at=started_at,
                log_item=log_item,
                status=status,
            )
        )
    await save_user_history(
        task_info=task_info,
        script_info=script_info,
        user_info=user_item,
        records=records,
    )
