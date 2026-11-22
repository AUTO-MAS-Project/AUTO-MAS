from __future__ import annotations

from importlib import import_module

# 惰性导出：本包里建计划的几个模块（run_plan、models、pipeline_override、hotkey、
# task_selection、plan_transforms）归解析一侧，导入它们会先执行本文件；这里要是急着
# 导入 environment / service，建计划的导入闭包里就带上了 agent 环境与运行池。
_LAZY_EXPORTS = {
    "MaaFWDeviceConfig": ".models",
    "MaaFWResolvedPath": ".models",
    "MaaFWResourceBundlePlan": ".models",
    "MaaFWRunPlan": ".models",
    "MaaFWRunResult": ".models",
    "MaaFWRunnerJobPayload": ".models",
    "MaaFWSkippedTaskPlan": ".models",
    "MaaFWTaskRunPlan": ".models",
    "MaaFWRunPlanError": ".run_plan",
    "build_maafw_run_plan": ".run_plan",
}


def __getattr__(name: str):
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(_LAZY_EXPORTS[name], __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))


__all__ = [
    "MaaFWDeviceConfig",
    "MaaFWResolvedPath",
    "MaaFWResourceBundlePlan",
    "MaaFWRunPlan",
    "MaaFWRunPlanError",
    "MaaFWRunResult",
    "MaaFWRunnerJobPayload",
    "MaaFWSkippedTaskPlan",
    "MaaFWTaskRunPlan",
    "build_maafw_run_plan",
]
