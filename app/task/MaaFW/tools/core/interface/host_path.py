"""给项目子进程的 ``PATH`` 去掉宿主 venv 的脚本目录。

建计划按 ``PATH`` 解析 pretask 的裸命令、宿主跑 pretask 时拼子进程环境都用它；只用标准库，
随建计划归解析这一侧。宿主环境变量的剔除名单（``PYTHON*``、代理等）是另一回事，在
``runtime_pool.host_environment``。
"""

from __future__ import annotations

import os
import sys


def _host_venv_script_dirs() -> set[str]:
    """宿主所在 venv（以及 ``VIRTUAL_ENV`` 指的环境）的脚本目录，``normcase`` 后的绝对路径。"""

    prefixes: list[str] = []
    if sys.prefix != sys.base_prefix:
        prefixes.append(sys.prefix)
    virtual_env = os.environ.get("VIRTUAL_ENV")
    if virtual_env:
        prefixes.append(virtual_env)
    scripts = "Scripts" if os.name == "nt" else "bin"
    return {
        os.path.normcase(os.path.abspath(os.path.join(prefix, scripts)))
        for prefix in prefixes
    }


def path_without_host_venv(path_value: str | None) -> str | None:
    """``PATH`` 去掉宿主 venv 的脚本目录。

    Runtime 用 ``uv run`` 起后端，``.venv\\Scripts`` 排在 PATH 最前：交给项目子进程（pretask）
    的 PATH、以及按 PATH 解析裸命令（``"exec": "python"``）时不去掉它，``python`` 就落到 MAS
    自己的解释器上，项目要的第三方包一个都没有。
    """

    if not path_value:
        return path_value
    excluded = _host_venv_script_dirs()
    if not excluded:
        return path_value
    kept = [
        entry
        for entry in path_value.split(os.pathsep)
        if entry and os.path.normcase(os.path.abspath(entry.strip('"'))) not in excluded
    ]
    return os.pathsep.join(kept)
