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
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager

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
    # 用户在 MAS 里填的代理（Update.ProxyAddress）此前从没交给过 uv / pip：装依赖、
    # 下载解释器都在裸连。所有 MFW 子进程环境都从这里派生，所以代理只在这一处注入，
    # 取当前线程登记的作用域值（见 subprocess_proxy_scope）。
    return apply_proxy_environment(env, current_subprocess_proxy())


#: 注入代理时写入的三个变量（同一值）。uv（reqwest）与 pip 都认这三个。
PROXY_ENVIRONMENT_KEYS: tuple[str, ...] = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")
#: 注入代理时必须豁免的回环地址。已证实验：uv 对 ``127.0.0.1`` 也走 ``HTTP(S)_PROXY``，
#: 且 ``NO_PROXY=localhost`` 不豁免 ``127.0.0.1``——Runtime 的回环包索引中继
#: ``http://127.0.0.1:<port>/simple/`` 会被推去代理，必须两条都写。
LOOPBACK_NO_PROXY_HOSTS: tuple[str, ...] = ("127.0.0.1", "localhost")


def apply_proxy_environment(
    env: Mapping[str, str], proxy_url: str | None
) -> dict[str, str]:
    """把代理地址写进子进程环境副本；``proxy_url`` 为空时原样返回。

    非空时 ``HTTP_PROXY`` / ``HTTPS_PROXY`` / ``ALL_PROXY`` 都设成同一值（含
    ``user:pw@`` 也原样写，凭据由调用方保证不进日志）；``NO_PROXY`` 取现有值
    （``NO_PROXY`` / ``no_proxy`` 都看）与回环地址的并集，逗号拼接、保序去重。
    为空时不动任何变量：用户系统环境里自己配的代理变量照旧生效。
    """

    proxy = str(proxy_url or "").strip()
    result = dict(env)
    if not proxy:
        return result
    for key in PROXY_ENVIRONMENT_KEYS:
        result[key] = proxy
        lower = key.lower()
        if lower in result:
            # POSIX 下两种大小写可以并存，不同值时各工具取哪个没有定数；既然
            # 用户显式配了代理，就让两份一致。
            result[lower] = proxy
    hosts: list[str] = []
    for key in ("NO_PROXY", "no_proxy"):
        for item in str(result.get(key) or "").split(","):
            host = item.strip()
            if host and host not in hosts:
                hosts.append(host)
    for host in LOOPBACK_NO_PROXY_HOSTS:
        if host not in hosts:
            hosts.append(host)
    merged = ",".join(hosts)
    result["NO_PROXY"] = merged
    if "no_proxy" in result:
        result["no_proxy"] = merged
    return result


# 代理串按线程登记：环境准备整段跑在一个 ``asyncio.to_thread`` 工作线程（或更新事务
# 的回调线程）里，各处只需从这里取，不用把 proxy_url 穿过 installer / agent_env 的
# 每个签名。核心包不许读 ``Config``，进入作用域的动作只在宿主侧
# （``tools/embedded``、``embedded_manager``、``api``）的同步函数体内做。
_SUBPROCESS_PROXY_STATE = threading.local()


@contextmanager
def subprocess_proxy_scope(proxy_url: str | None) -> Iterator[None]:
    """在当前线程上登记子进程代理；``None`` / 空串表示本段不注入代理。"""

    previous = getattr(_SUBPROCESS_PROXY_STATE, "proxy_url", None)
    _SUBPROCESS_PROXY_STATE.proxy_url = str(proxy_url or "").strip() or None
    try:
        yield
    finally:
        _SUBPROCESS_PROXY_STATE.proxy_url = previous


def current_subprocess_proxy() -> str | None:
    return getattr(_SUBPROCESS_PROXY_STATE, "proxy_url", None)
