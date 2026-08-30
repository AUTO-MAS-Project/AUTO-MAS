"""MaaFW 内置运行集成层。

把 ``tools/core`` 下的运行时库编排成 MAS 的任务执行形态：在 MAS 自己的
worker 子进程内加载项目的 MaaFramework 直接驱动，不启动项目自带的 UI 外壳。

``runner_task`` 会 import ``maa``（经 runner 包），因此**不在这里 re-export**，
由调用方按需延迟导入，避免把 DLL 拉进主进程。
"""

from __future__ import annotations

from .project_path import (
    normalize_project_path,
    release_project_path,
    try_reserve_project_path,
)
from .registry import MaaFWRegistryService
from .runtime_route import (
    MaaFWManagedExecutionRoute,
    MaaFWRuntimePoolRoute,
    MaaFWRuntimeRouteError,
)

__all__ = [
    "MaaFWManagedExecutionRoute",
    "MaaFWRegistryService",
    "MaaFWRuntimePoolRoute",
    "MaaFWRuntimeRouteError",
    "normalize_project_path",
    "release_project_path",
    "try_reserve_project_path",
]
