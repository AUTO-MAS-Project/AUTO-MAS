"""用户收尾共用的历史输入、统计通知和保存流程。"""

from collections.abc import Sequence
from datetime import datetime
from typing import Literal

from pydantic import TypeAdapter

from app.core.history import aggregate_history, history_store
from app.core.ws import Publisher, protocol
from app.models.schema import (
    HistoryAggregationItem,
    HistoryStatistic,
    HistoryWrite,
    WSTaskNoticeData,
)
from app.utils import get_logger
from app.utils.constants import UTC4

logger = get_logger("任务历史记录")
_statistic_adapter = TypeAdapter(HistoryStatistic)


def statistic(kind: Literal["counter", "snapshot", "keyed_snapshot"], value):
    """专项显式声明统计合并规则，并在交给存储前验证。"""
    return _statistic_adapter.validate_python({"kind": kind, "value": value})


def build_record(
    *,
    script_info,
    user_info,
    started_at: datetime,
    log_item,
    status: Literal["success", "error", "skipped", "cancelled"],
    message: str | None = None,
    data: dict[str, HistoryStatistic] | None = None,
) -> HistoryWrite:
    """保留专项明确给出的单轮结论，服务器日由任务侧显式选择。"""
    if started_at.tzinfo is None or started_at.utcoffset() is None:
        raise ValueError("历史开始时间必须带有效时区")
    return HistoryWrite(
        time=started_at.astimezone(UTC4),
        username=user_info.name,
        script_name=script_info.name,
        status=status,
        message=log_item.status if message is None else message,
        logs="".join(log_item.content),
        data=data or {},
    )


def aggregate_statistics(records: Sequence[HistoryWrite]) -> dict:
    """通知复用历史的纯聚合；诊断留在本轮日志，不伪造业务统计。"""
    aggregate = aggregate_history(
        [
            HistoryAggregationItem(time=record.time, data=record.data)
            for record in records
        ]
    )
    for error in aggregate.errors:
        diagnostic = f"统计聚合失败（{error.key}）：{error.message}"
        logger.warning(diagnostic)
        for index in error.input_indices:
            if diagnostic not in records[index].logs:
                records[index].logs += f"\n{diagnostic}\n"
    return {key: entry.value for key, entry in aggregate.data.items()}


async def save_user_history(*, task_info, script_info, user_info, records) -> None:
    """在用户终态收集回放，逐条保存；一条失败不阻断其余历史与收尾。"""
    if not records:
        return
    aggregate_statistics(records)
    try:
        attachments = await task_info.collect_user_history_attachments(
            script_info, user_info
        )
        records[-1].attachments.extend(attachments)
    except Exception:
        logger.opt(exception=True).warning(
            "收集用户历史附件失败，继续保存日志与执行结果"
        )
    try:
        for record in records:
            try:
                await history_store.save(record)
            except Exception as error:
                logger.opt(exception=True).warning(
                    f"保存 {script_info.name}/{user_info.name} 历史失败：{error}"
                )
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
        await task_info.discard_user_history_capture(script_info, user_info)
