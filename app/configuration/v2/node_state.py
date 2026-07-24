"""ConfigNode 激活生命周期枚举。"""

from __future__ import annotations

from enum import Enum


class NodeState(str, Enum):
    """节点激活状态。

    - ``INACTIVE``：未激活（``model_validate`` / 构造后）
    - ``INITIALIZING``：初始化中（``activate()`` 的 ``_activate_from_payload`` 阶段）
    - ``ACTIVE``：已激活（``activate()`` 完成后）
    """

    INACTIVE = "inactive"
    INITIALIZING = "initializing"
    ACTIVE = "active"
