#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


from importlib import import_module

# 惰性导出（与 app/core/__init__.py 同一 idiom）。
#
# 这里必须惰性：第二层的 worker 子进程用的是 runtime pool 的隔离 venv
# （只有 maafw 与项目依赖），它以 `-m app.task.MaaFW.tools.core.
# automas_maafw_runner.worker` 启动时，Python 会先执行本文件；若在此
# 急切导入九个 manager，就会连带拉起 app.core -> httpx/loguru/fastapi，
# 而那些包在隔离 venv 里并不存在，worker 起不来。
#
# 顺带也让宿主启动少导入一批模块。属性访问语义不变：
# `import app.task as task; task.MaaFWManager` 照常可用。
_LAZY_EXPORTS = {
    "MaaManager": (".MAA", "MaaManager"),
    "MaaEndManager": (".MaaEnd", "MaaEndManager"),
    "SrcManager": (".SRC", "SrcManager"),
    "M9AManager": (".M9A", "M9AManager"),
    "GeneralManager": (".general", "GeneralManager"),
    "OkwwManager": (".Okww", "OkwwManager"),
    "OkNteManager": (".OkNte", "OkNteManager"),
    "HSRManager": (".HSR", "HSRManager"),
    "BetterGIManager": (".BetterGI", "BetterGIManager"),
    "MaaFWEmbeddedManager": (".MaaFW.embedded_manager", "MaaFWEmbeddedManager"),
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
    "MaaManager",
    "SrcManager",
    "M9AManager",
    "GeneralManager",
    "MaaEndManager",
    "OkwwManager",
    "OkNteManager",
    "HSRManager",
    "BetterGIManager",
    "MaaFWEmbeddedManager",
]
