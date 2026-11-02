"""主界面提示的发送与启动暂存；配置对象只提供暂存队列。"""

from typing import Any, Protocol

from app.utils import get_logger

logger = get_logger("系统通知")


class NoticeOwner(Protocol):
    startup_notices: list[dict[str, Any]]


async def push(owner: NoticeOwner, *, level: str, title: str, lines: list[str]) -> None:
    from app.core import Publisher
    from app.core.ws import protocol
    from app.models.schema import WSSystemNoticeData

    notice = {"level": level, "title": title, "lines": list(lines)}
    try:
        sent = await Publisher.send(
            id=protocol.ID_MAIN,
            type=protocol.SYSTEM_NOTICE,
            data=WSSystemNoticeData(**notice),
        )
    except Exception as exc:
        logger.warning(f"系统通知发送失败，改为下次连接时发送：{exc}")
        sent = False
    if not sent:
        owner.startup_notices.append(notice)


async def flush(owner: NoticeOwner) -> None:
    from app.core import Publisher
    from app.core.ws import protocol
    from app.models.schema import WSSystemNoticeData

    pending, owner.startup_notices = owner.startup_notices, []
    try:
        while pending:
            try:
                sent = await Publisher.send(
                    id=protocol.ID_MAIN,
                    type=protocol.SYSTEM_NOTICE,
                    data=WSSystemNoticeData(**pending[0]),
                )
            except Exception as exc:
                logger.warning(f"系统通知发送失败，改为下次连接时发送：{exc}")
                sent = False
            if not sent:
                break
            pending.pop(0)
    finally:
        # 保留取消或断线时未发送的条目，并排在期间新增的提示之前。
        owner.startup_notices[:0] = pending
