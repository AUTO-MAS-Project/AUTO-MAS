"""社区能力共享锁与缓存的唯一管理器。"""

from app.core.community.scheduling import CommunityScheduleOperations
from app.core.community.sign import CommunitySignOperations


class CommunityManager(CommunitySignOperations, CommunityScheduleOperations):
    def __init__(self) -> None:
        CommunitySignOperations.__init__(self)
        CommunityScheduleOperations.__init__(self)
