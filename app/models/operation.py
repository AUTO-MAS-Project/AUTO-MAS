"""宿主命令的进程内运行快照，不持久化业务参数或插件对象。"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

type OperationState = Literal[
    "queued", "running", "cancelling", "succeeded", "failed", "cancelled"
]


class OperationInfo(BaseModel):
    operationId: UUID
    configUid: UUID
    field: str
    owner: UUID | None = None
    state: OperationState = "queued"
    cancellable: bool = True
    createdAt: datetime
    completedAt: datetime | None = None
    errorCode: str | None = None
