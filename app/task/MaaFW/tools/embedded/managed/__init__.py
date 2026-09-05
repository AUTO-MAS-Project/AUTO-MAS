"""第三层（资源共享 managed）服务层 —— **已落库，尚未接线**。

三层规划 §4 的第三层：MAS 管理不可变 Project Store 与精确 Runtime Pool，
依赖去重与路由，lease / reference / pin / GC。**前置是第二层稳定**，
而第二层（本次移植）尚未经过真机验证，因此本目录：

- 不被 ``task_manager`` 或任何 manager 引用
- 不暴露任何 UI，``Project.Source = managed`` 这条轴根本没有加进 Config 模型
- 与 ``tools/core/automas_maafw_project_store`` / ``automas_maafw_runtime_pool``
  同样处于"落库不接线"状态（阶段 1 落库时也是如此）

落库的是插件 ``automas_script_maafw_managed`` 中**零宿主耦合**的两个模块
（``services`` 2,612 行 + ``environment_service`` 897 行）。该包另外三个文件
（``plugin`` 5,606 / ``schema`` 805 / ``adapter`` 721，共 7,132 行）依赖
``app.plugins`` 插件 HTTP 宿主层，按移植指南 §4 规则 6 不搬。
"""

from __future__ import annotations

from .environment_service import MaaFWManagedEnvironmentService
from .services import (
    ManagedServiceError,
    ManagedServiceGateway,
    managed_project_identity,
)

__all__ = [
    "MaaFWManagedEnvironmentService",
    "ManagedServiceError",
    "ManagedServiceGateway",
    "managed_project_identity",
]
