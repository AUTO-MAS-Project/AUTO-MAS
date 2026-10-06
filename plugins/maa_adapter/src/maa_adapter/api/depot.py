"""兼容：业务实现仍在 service.py，按域再导出。"""
from .service import (
    get_depot_inventory,
    get_depot_items,
    get_depot_stage_candidates,
)

__all__ = [
    "get_depot_inventory",
    "get_depot_items",
    "get_depot_stage_candidates",
]
