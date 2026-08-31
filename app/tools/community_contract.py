#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


"""游戏社区内部结果契约，不依赖 API、前端或通知渠道。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping


CredentialState = Literal["empty", "valid", "incomplete", "invalid"]
ActivityState = Literal[
    "success",
    "empty",
    "limited",
    "unavailable",
    "failed",
]


class CommunitySignInProgressError(RuntimeError):
    """游戏社区签到已在执行。"""


@dataclass(frozen=True)
class CredentialStatus:
    """凭据本地校验摘要，不包含凭据值。"""

    token_field: str
    state: CredentialState
    fields: tuple[str, ...] = ()
    reason: str = ""

    @property
    def configured(self) -> bool:
        """返回是否存在非空凭据。"""

        return self.state != "empty"

    @property
    def locally_valid(self) -> bool:
        """返回是否通过本地格式校验，不表示上游认证成功。"""

        return self.state == "valid"


@dataclass(frozen=True)
class CommunitySignResult:
    """签到结果的领域表示，同时兼容旧版字典字段。"""

    account: str
    account_uid: str
    game: str
    platform: str
    status: str
    reward: str = ""
    reason: str = ""
    completed: bool = False
    notification_only: bool = False

    @classmethod
    def from_legacy(
        cls,
        item: Mapping[str, Any],
        *,
        fallback_account: str = "未知用户",
        fallback_uid: str = "",
    ) -> "CommunitySignResult":
        """从既有结果字典读取领域结果，不改变外部字段语义。"""

        account = str(item.get("account") or fallback_account)
        if account == "未知用户":
            account = fallback_account
        return cls(
            account=account,
            account_uid=str(item.get("account_uid") or fallback_uid),
            game=str(item.get("game") or ""),
            platform=str(item.get("platform") or "未知"),
            status=str(item.get("status") or "失败"),
            reward=str(item.get("reward") or ""),
            reason=str(item.get("reason") or ""),
            completed=bool(item.get("_completed")),
            notification_only=bool(item.get("_notification_only")),
        )

    def to_legacy(self) -> dict[str, Any]:
        """转换回旧版签到结果字典，供现有 API 与通知继续消费。"""

        result: dict[str, Any] = {
            "account": self.account,
            "account_uid": self.account_uid,
            "game": self.game,
            "platform": self.platform,
            "status": self.status,
            "reward": self.reward,
            "reason": self.reason,
        }
        if self.completed:
            result["_completed"] = True
        if self.notification_only:
            result["_notification_only"] = True
        return result


@dataclass(frozen=True)
class CommunityActivitySnapshot:
    """日常活跃度领域结果，供后续只读查询模块复用。"""

    account: str
    account_uid: str
    game: str
    platform: str
    status: ActivityState
    completed: int | None = None
    target: int | None = None
    tasks: tuple[Mapping[str, Any], ...] = ()
    resources: tuple[Mapping[str, Any], ...] = ()
    reason: str = ""
    updated_at: str = ""
    role_name: str = ""
    role_uid: str = ""
    server: str = ""
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转换为与 API 无关的普通字典。"""

        return {
            "account": self.account,
            "account_uid": self.account_uid,
            "game": self.game,
            "platform": self.platform,
            "status": self.status,
            "completed": self.completed,
            "target": self.target,
            "tasks": [dict(task) for task in self.tasks],
            "resources": [dict(resource) for resource in self.resources],
            "reason": self.reason,
            "updated_at": self.updated_at,
            "role_name": self.role_name,
            "role_uid": self.role_uid,
            "server": self.server,
            "source": self.source,
        }
