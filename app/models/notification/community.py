"""通知消费的签到结果；机器状态与原有展示文字分开。"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

CommunityNotificationStatus = Literal[
    "success", "already_signed", "risk_control", "failed"
]

_LEGACY_STATUSES: dict[str, CommunityNotificationStatus] = {
    "成功": "success",
    "已签到": "already_signed",
    "风控": "risk_control",
}


@dataclass(frozen=True)
class CommunityNotificationResult:
    account: str
    account_uid: str
    game: str
    platform: str
    status: CommunityNotificationStatus
    reward: str = ""
    reason: str = ""
    status_text: str = "失败"

    @property
    def succeeded(self) -> bool:
        # _completed 是签到业务的完成判据，不等于领取奖励成功。
        return self.status in ("success", "already_signed")

    @classmethod
    def from_legacy(cls, item: Mapping[str, object]) -> "CommunityNotificationResult":
        """只在通知入口投影旧结果，不参与签到成功、日期或落盘判断。"""

        status_text = str(item.get("status", "失败"))
        return cls(
            account=str(item.get("account", "") or ""),
            account_uid=str(item.get("account_uid", "") or ""),
            game=str(item.get("game", "") or ""),
            platform=str(item.get("platform", "未知") or "未知"),
            status=_LEGACY_STATUSES.get(status_text, "failed"),
            status_text=status_text,
            reward=str(item.get("reward", "") or ""),
            reason=str(item.get("reason", "") or ""),
        )


def community_notification_results(
    results: Iterable[Mapping[str, object]],
) -> tuple[CommunityNotificationResult, ...]:
    """固定通知输入快照，保留原有占位结果过滤规则。"""

    return tuple(
        CommunityNotificationResult.from_legacy(item)
        for item in results
        if not item.get("_notification_only")
    )
