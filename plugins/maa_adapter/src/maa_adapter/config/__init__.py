"""MAA 配置模型的统一导出，保持持久类型名和配置身份。"""

from .plan import MaaPlanConfig, PlanDaysConfig
from .script import MaaConfig
from .user import MaaUserConfig

UserConfigType = MaaUserConfig
__all__ = [
    "MaaConfig",
    "MaaPlanConfig",
    "MaaUserConfig",
    "PlanDaysConfig",
    "UserConfigType",
]
