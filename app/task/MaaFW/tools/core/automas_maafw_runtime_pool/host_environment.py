"""MFW 专项各子进程共用的宿主环境隔离口径。

运行池的 uv / pip、worker、项目 agent 与 agent 的 pip 检测都从 ``os.environ`` 复制一份再改，
此前每处各维护一份 ``pop`` 名单且互不一致：``PYTHONHOME`` / ``PYTHONUSERBASE`` 都剔了，
``PYTHONWARNINGS=error``（第一条 DeprecationWarning 就崩）、``PYTHONOPTIMIZE``（断言被删）、
``PYTHONINSPECT``（进程退不出）、``PYTHONDEVMODE`` 却原样穿过去。受 Runtime 监督时这些已在
Runtime 边界按增补 2 C20 剔除，但旧启动链路（``AUTO_MAS_RUNTIME_MODE=off``）与开发态直接继承
宿主环境，后端必须自己守住同一条线。

口径与 Runtime 一致：所有 ``PYTHON`` 开头的宿主变量默认不放行（新版本解释器新增的也不放行），
只保留不改变「加载什么代码、以什么模式运行」的编码 / 缓冲 / 字节码落盘 / 用户站点开关；
激活中的虚拟环境标记、pip 的安装位置覆盖、颜色强制与 Rust 调试变量一并剔除。
``PIP_INDEX_URL`` / ``AUTO_MAS_*`` 等用户显式给 MFW 专项的开关不在名单内，仍按各处既有约定生效。
"""

from __future__ import annotations

import os
from collections.abc import Mapping

#: 宿主 ``PYTHON*`` 变量里仅有的放行项。
PASSTHROUGH_PYTHON_KEYS: frozenset[str] = frozenset(
    {
        "PYTHONIOENCODING",
        "PYTHONUTF8",
        "PYTHONUNBUFFERED",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONNOUSERSITE",
    }
)

#: ``PYTHON*`` 之外同样不从宿主继承的变量。
ISOLATED_HOST_KEYS: frozenset[str] = frozenset(
    {
        # 启动链路（Runtime → uv run → 后端）或用户终端里激活的环境指向：交给 uv / pip 前
        # 必须剔除，否则外部 uv 会把项目环境解析到 MAS 自己的 venv 上。
        "VIRTUAL_ENV",
        "VIRTUAL_ENV_PROMPT",
        "UV_PROJECT_ENVIRONMENT",
        "CONDA_PREFIX",
        "CONDA_DEFAULT_ENV",
        "__PYVENV_LAUNCHER__",
        # pip 的安装位置覆盖会把包装到 venv 之外。
        "PIP_TARGET",
        "PIP_PREFIX",
        "PIP_USER",
        # FORCE_COLOR / CLICOLOR_FORCE 会压过 uv 的 --color never 往日志里塞 ANSI 序列；
        # RUST_LOG 不加 -v 也会让 uv 往 stderr 倾倒 TRACE。
        "FORCE_COLOR",
        "CLICOLOR_FORCE",
        "CLICOLOR",
        "NO_COLOR",
        "RUST_LOG",
        "RUST_BACKTRACE",
        "RUST_MIN_STACK",
    }
)


#: 项目子进程（agent 与给它准备环境的 pip）写 Python 字节码缓存的目录名，放在项目根下。
#: 不设的话 pyc 会散进项目自带的 ``python/Lib`` 与 ``agent/``（M9A 一轮 2000 多个、15 MB），
#: 副本从此和导入时对不上；``PYTHONDONTWRITEBYTECODE`` 不是替代——那会让每次启动多 1–2 s 编译。
PROJECT_PYCACHE_DIR_NAME = ".pycache"


#: 前缀树里一个 pyc 的路径 = 前缀 + 去掉盘符的源码绝对路径，项目根会出现两遍；给源码相对
#: 路径（site-packages 里实测最深 72 字符）留的余量。超过 Windows 的 MAX_PATH 时解释器写 pyc
#: 静默失败、每次启动全量重编译，所以宁可不设前缀退回源码旁的 __pycache__。
_PYCACHE_RELATIVE_BUDGET = 90
_WINDOWS_MAX_PATH = 259


def _windows_long_paths_enabled() -> bool:
    if os.name != "nt":
        return True
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem"
        ) as key:
            return int(winreg.QueryValueEx(key, "LongPathsEnabled")[0]) == 1
    except OSError:
        return False


def project_pycache_prefix(project_path: str | os.PathLike[str]) -> str | None:
    """``<项目根>/.pycache``；项目根太长、又没开长路径支持时返回 None（不设前缀）。"""

    root = os.fspath(project_path)
    if (
        2 * len(root) + _PYCACHE_RELATIVE_BUDGET > _WINDOWS_MAX_PATH
        and not _windows_long_paths_enabled()
    ):
        return None
    return os.path.join(root, PROJECT_PYCACHE_DIR_NAME)


def set_project_pycache_prefix(
    env: dict[str, str], project_path: str | os.PathLike[str]
) -> None:
    """让 ``env`` 里的 Python 把 pyc 集中写到 ``<项目根>/.pycache``。冻结外壳会无视它，无害。

    安装路径长到前缀树会撞 MAX_PATH 时不设（pyc 退回源码旁的 ``__pycache__``，行为与从前一致）。
    """

    prefix = project_pycache_prefix(project_path)
    if prefix is None:
        env.pop("PYTHONPYCACHEPREFIX", None)
        return
    env["PYTHONPYCACHEPREFIX"] = prefix


def is_isolated_host_key(name: str) -> bool:
    """按 Windows 的大小写不敏感语义判断一个宿主变量是否不得下传。"""

    upper = name.upper()
    if upper.startswith("PYTHON"):
        return upper not in PASSTHROUGH_PYTHON_KEYS
    return upper in ISOLATED_HOST_KEYS


def strip_host_python_environment(
    environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """返回剔除了宿主 Python / uv 相关变量的环境副本；缺省从 ``os.environ`` 复制。

    调用方在返回值上再显式设置自己需要的 ``PYTHONPATH`` / ``VIRTUAL_ENV`` 等，
    这样每处只需要声明「我要什么」，不必各自记住「要剔什么」。
    """

    source = os.environ if environment is None else environment
    return {
        name: value for name, value in source.items() if not is_isolated_host_key(name)
    }
