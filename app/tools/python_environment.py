"""子进程共用的 Python 环境隔离；只依赖标准库。"""

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
        # worker 自己拿到的 binding / DLL 指向（见 runtime_pool/binding.py 的
        # BINDING_ENVIRONMENT_KEYS）不能再往下传：worker 在进程内派生 agent 子进程、
        # agent 的 pip 检测都从这里起步，透传会让 agent 侧的 maa/agent/__init__.py 拿
        # runner 的 DLL 目录去 Library.open(agent_server=True)——目标副本缺
        # MaaAgentServer.dll 就「Agent 进程已退出」。worker 的 build_runner_environment
        # 先剥后设，剥掉不影响 worker 自己。
        "MAAFW_BINARY_PATH",
        "AUTO_MAS_MAAFW_BINDING_DIR",
        "AUTO_MAS_MAAFW_NATIVE_DIR",
    }
)


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
    env = {
        name: value for name, value in source.items() if not is_isolated_host_key(name)
    }
    return env
