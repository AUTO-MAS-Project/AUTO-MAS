"""宿主内置的 MaaFW Core 服务实现。

这些模块来自 MaaFW 插件仓的领域包，但在普通 AUTO-MAS 宿主中作为
内部实现随程序发布，不参与插件发现或插件生命周期。
"""

from importlib import import_module

# 惰性导出：本文件同时位于第一层热路径与第二层 worker 的导入链上。
# automas_maafw_project_update 会 import httpx，而 worker 子进程跑在只有
# maafw 与项目依赖的隔离 venv 里，急切 re-export 会让 worker 直接起不来。
_LAZY_EXPORTS = {
    "MaaFWInterfaceService": (
        ".automas_maafw_interface",
        "MaaFWInterfaceService",
    ),
    "MaaFWProjectUpdateService": (
        ".automas_maafw_project_update",
        "MaaFWProjectUpdateService",
    ),
}


def __getattr__(name: str):
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = _LAZY_EXPORTS[name]
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))


__all__ = [
    "MaaFWInterfaceService",
    "MaaFWProjectUpdateService",
]
