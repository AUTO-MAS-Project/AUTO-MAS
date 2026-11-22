from __future__ import annotations

from importlib import import_module

# 惰性导出：只留执行侧的名字。建计划的几个模块（run_plan、models、pipeline_override、
# hotkey、task_selection、plan_transforms）已进解析库 ``maafw_interface.runner``，
# 解析侧的名字从那里取；这里不急着导入 environment / service，免得只导入 worker
# 协议时就带上 agent 环境与运行池。
_LAZY_EXPORTS = {
    "MaaFWRunnerEnvironment": ".environment",
    "release_runner_environment": ".environment",
    "MaaFWRunnerService": ".service",
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
    "MaaFWRunnerEnvironment",
    "MaaFWRunnerService",
    "release_runner_environment",
]
