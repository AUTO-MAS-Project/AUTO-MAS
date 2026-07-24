"""稳定信封的 WS 发布器、状态缓存与事务 outbox。"""

from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.utils import get_logger

from . import protocol

logger = get_logger("WS发布器")


class MergeableStateCache:
    """按 ``(id, type)`` 保存可合并状态的最新值。"""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], dict[str, Any]] = {}
        self._revisions: dict[tuple[str, str], int] = {}
        self._global_revision = 0

    def update(self, id: str, type: str, data: dict[str, Any]) -> int:
        if type not in protocol.MERGEABLE_TYPES:
            return self._global_revision
        key = (id, type)
        self._global_revision += 1
        self._cache[key] = copy.deepcopy(data)
        self._revisions[key] = self._global_revision
        return self._global_revision

    def get(
        self,
        id: str,
        type: str | None = None,
    ) -> dict[str, Any] | None:
        """读取状态；省略 ``type`` 时兼容按事件名读取。"""

        if type is not None:
            value = self._cache.get((id, type))
            return copy.deepcopy(value) if value is not None else None
        for (message_id, message_type), value in reversed(tuple(self._cache.items())):
            if message_type == id:
                return copy.deepcopy(value)
        return None

    def snapshot(self) -> dict[str, dict[str, dict[str, Any]]]:
        """返回 ``type -> id -> data``，避免不同实例互相覆盖。"""

        result: dict[str, dict[str, dict[str, Any]]] = {}
        for (message_id, message_type), value in self._cache.items():
            result.setdefault(message_type, {})[message_id] = copy.deepcopy(value)
        return result

    @property
    def revision(self) -> int:
        return self._global_revision

    def clear(self) -> None:
        self._cache.clear()
        self._revisions.clear()
        self._global_revision = 0


@dataclass(slots=True)
class OutboxEntry:
    id: str
    type: str
    data: dict[str, Any]
    transaction_id: str


class PostCommitOutbox:
    """按 transaction/task 分桶，提交与回滚只处理自己的事件。"""

    def __init__(self) -> None:
        self._buckets: dict[str, list[OutboxEntry]] = {}
        self._lock = asyncio.Lock()

    @property
    def _pending(self) -> list[OutboxEntry]:
        """兼容旧测试的只读扁平视图。"""

        return [entry for entries in self._buckets.values() for entry in entries]

    @staticmethod
    def bucket_key(transaction_id: str | None = None) -> str:
        if transaction_id is not None:
            return f"transaction:{transaction_id}"
        task = asyncio.current_task()
        return f"task:{id(task)}" if task is not None else "task:none"

    async def enqueue(
        self,
        entry: OutboxEntry,
        *,
        transaction_id: str | None = None,
    ) -> None:
        key = self.bucket_key(transaction_id)
        async with self._lock:
            self._buckets.setdefault(key, []).append(entry)

    async def flush(
        self,
        *,
        transaction_id: str | None = None,
    ) -> list[OutboxEntry]:
        key = self.bucket_key(transaction_id)
        async with self._lock:
            return self._buckets.pop(key, [])

    async def discard(self, *, transaction_id: str | None = None) -> None:
        key = self.bucket_key(transaction_id)
        async with self._lock:
            count = len(self._buckets.pop(key, []))
        if count:
            logger.debug(f"outbox 回滚，丢弃 {count} 条待发布消息")

    async def discard_all(self) -> None:
        async with self._lock:
            self._buckets.clear()


class WSPublisher:
    def __init__(self) -> None:
        self._cache = MergeableStateCache()
        self._outbox = PostCommitOutbox()
        self._ws_manager: Any = None
        self._flush_lock = asyncio.Lock()

    def set_ws_manager(self, manager: Any) -> None:
        self._ws_manager = manager

    @property
    def cache(self) -> MergeableStateCache:
        return self._cache

    @property
    def outbox(self) -> PostCommitOutbox:
        return self._outbox

    async def send(
        self,
        id: str,
        type: str,
        data: BaseModel | dict[str, Any] | None = None,
    ) -> bool:
        """使用稳定 ``{id,type,data}`` 信封发送消息。"""

        payload = data.model_dump() if isinstance(data, BaseModel) else dict(data or {})
        message_id = str(id or "")
        message = protocol.build_message(message_id, type, payload)
        try:
            message_size = protocol.message_size_bytes(message)
        except (TypeError, ValueError) as exc:
            logger.warning(
                "WS 发布消息无法 JSON 序列化，已拒绝缓存和发送: "
                f"id={message_id}, type={type}, "
                f"error={exc.__class__.__name__}: {exc}"
            )
            return False

        if message_size > protocol.DEFAULT_MAX_MESSAGE_BYTES:
            logger.warning(
                "WS 发布消息超过应用层上限，已拒绝缓存和发送: "
                f"id={message_id}, type={type}, "
                f"limit={protocol.DEFAULT_MAX_MESSAGE_BYTES}"
            )
            return False

        self._cache.update(message_id, type, payload)
        if self._ws_manager is None:
            return False
        sent = await self._ws_manager.send_json(message)
        if not sent:
            logger.debug(f"主连接未就绪，消息未发送: id={message_id}, type={type}")
        return bool(sent)

    async def publish(
        self,
        type: str,
        data: BaseModel | dict[str, Any] | None = None,
        *,
        id: str = "Config",
        root_id: str | None = None,
        transaction_id: str | None = None,
    ) -> bool:
        """发布消息；带事务 ID 时先进入对应 outbox 桶。"""

        message_id = root_id or id
        payload = data.model_dump() if isinstance(data, BaseModel) else dict(data or {})
        if transaction_id is not None:
            return await self.enqueue(
                message_id,
                type,
                payload,
                transaction_id=transaction_id,
            )
        return await self.send(message_id, type, payload)

    async def send_legacy(
        self,
        id: str,
        type: str,
        data: dict[str, Any],
    ) -> bool:
        """旧 Config 发送必须原样保留，不执行按 id 的猜测映射。"""

        return await self.send(str(id), type, data)

    async def enqueue(
        self,
        id: str,
        type: str | dict[str, Any],
        data: dict[str, Any] | None = None,
        *,
        root_id: str | None = None,
        transaction_id: str | None = None,
    ) -> bool:
        """将消息加入当前事务桶。

        新接口为 ``enqueue(id, type, data)``；同时兼容早期
        ``enqueue(type, data, root_id=...)`` 调用。
        """

        if isinstance(type, dict) and data is None:
            message_id = root_id or "Config"
            message_type = id
            payload = type
        else:
            message_id = root_id or id
            message_type = str(type)
            payload = dict(data or {})

        effective_transaction_id = (
            transaction_id
            if transaction_id is not None
            else PostCommitOutbox.bucket_key()
        )
        await self._outbox.enqueue(
            OutboxEntry(
                id=str(message_id),
                type=message_type,
                data=copy.deepcopy(payload),
                transaction_id=effective_transaction_id,
            ),
            transaction_id=transaction_id,
        )
        return True

    async def flush_outbox(self, transaction_id: str | None = None) -> None:
        # A transaction releases the configuration lock before transport I/O.
        # Serialize the post-commit drain so a slow earlier transaction cannot
        # be overtaken by a later commit on the wire.
        async with self._flush_lock:
            entries = await self._outbox.flush(transaction_id=transaction_id)
            for entry in entries:
                await self.send(entry.id, entry.type, entry.data)

    async def discard_outbox(self, transaction_id: str | None = None) -> None:
        await self._outbox.discard(transaction_id=transaction_id)

    def snapshot_payload(self) -> dict[str, Any]:
        return {
            "revision": self._cache.revision,
            "states": self._cache.snapshot(),
        }

    async def send_snapshot(self) -> bool:
        return await self.send(
            protocol.ID_MAIN,
            protocol.SNAPSHOT_RESPONSE,
            self.snapshot_payload(),
        )


ws_publisher = WSPublisher()
Publisher = ws_publisher
