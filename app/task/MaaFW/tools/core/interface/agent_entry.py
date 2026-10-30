"""agent 入口脚本的 CFA 兜底规则；导入投影与运行时 agent 命令共用这一处。

CFA（MFW-PyQt6）解析 agent 入口时（``interface_manager._resolve_agent_entry``），child_args
里的入口脚本解析不到存在的文件，就退回 ``<interface 所在目录>/agent/main.py``。它的源码热更新
把 tag 源码的 ``assets/`` 平铺到包根、``agent/`` 放包根，却不改 child_args，于是包根
interface 里留着源码仓写法 ``../agent/main.py``——CFA 靠这个兜底照常能跑。

这里只接「相对写法经 ``..`` 越出 interface 所在目录」这一种：在目录里却不存在的入口、
绝对路径 / 盘符路径的入口都照旧处理，免得声明错了入口的项目悄悄改跑另一个脚本。
"""

from __future__ import annotations

#: 兜底入口，相对 interface 所在目录。
CFA_FALLBACK_AGENT_ENTRY = "agent/main.py"

_PYTHON_ENTRY_SUFFIXES = (".py", ".pyw")


def is_python_entry_arg(value: str) -> bool:
    """child_args 里的这一项是不是 Python 入口脚本路径（按后缀；``--config=a.py`` 这类选项不算）。"""

    text = value.strip().strip('"').strip("'")
    return not text.startswith("-") and text.lower().endswith(_PYTHON_ENTRY_SUFFIXES)


def is_relative_entry_path(value: str) -> bool:
    """入口参数是不是相对写法（只有相对写法经 ``..`` 越出 interface 所在目录才按 CFA 兜底）。

    ``{PROJECT_DIR}`` / ``${PROJECT_DIR}`` 前缀算相对写法（投影把它剥成相对路径，运行时替换成
    项目目录）；绝对路径、盘符路径不算——它们照原来的口径处理（投影报「必须是项目内的相对
    路径」，运行时原样交给解释器），不改跑兜底入口。判据与投影的
    ``_normalize_declared_path`` 认绝对路径的那一步相同。
    """

    text = str(value).strip().strip('"').strip("'").replace("\\", "/")
    text = text.replace("${PROJECT_DIR}", "{PROJECT_DIR}")
    if text.startswith("{PROJECT_DIR}"):
        text = text[len("{PROJECT_DIR}") :].lstrip("/")
    return not (text.startswith("/") or (len(text) > 1 and text[1] == ":"))


def describe_cfa_agent_entry_fallback(raw_arg: str, used: str) -> str:
    """兜底生效时给人看的说明。"""

    return (
        f"agent 入口 {raw_arg} 越出了项目目录，这是源码形态平铺后（或 CFA 源码热更新后）"
        f"的布局，已改用项目里的 {used}"
    )


def flattened_entry_path(raw_arg: str) -> str | None:
    """越出项目目录的相对入口在平铺布局里的位置：去掉开头的 ``./`` 与 ``../``。

    源码仓把 interface 放在 ``assets/``、agent 放在它外面（``./../agent/main.py``）；导入时
    ``assets/`` 提升到副本根、``agent/`` 也放在副本根（见 ``projection.ProjectionRules.output_path``），
    于是入口就在 ``<项目>/agent/main.py``——interface 不改，运行时按这条找。CFA 的固定兜底
    ``agent/main.py`` 是它的特例。去完什么都不剩、或中间还有 ``..`` 时返回 None。
    """

    text = str(raw_arg).strip().strip('"').strip("'").replace("\\", "/")
    text = text.replace("${PROJECT_DIR}", "{PROJECT_DIR}")
    if text.startswith("{PROJECT_DIR}"):
        text = text[len("{PROJECT_DIR}") :].lstrip("/")
    parts = [part for part in text.split("/") if part not in ("", ".")]
    while parts and parts[0] == "..":
        parts.pop(0)
    if not parts or ".." in parts:
        return None
    return "/".join(parts)


#: 项目自带 Python 的固定位置写法，与 ``agent_env.planner._is_bundled_python_pattern`` 同一判据。
_BUNDLED_PYTHON_SUFFIX = "python/python.exe"


def bundled_python_escape_path(raw_exec: str) -> str | None:
    """pretask 的 ``exec`` 经开头的 ``..`` 越出项目目录、指向项目自带的 Python 时，它在项目里的位置。

    MFABD2 发行包的 pretask 写 ``"exec": "../../python/python.exe"``：它按 MFAA 实测的工作目录
    ``resource/base`` 上跳两级，指的就是包根的 ``python/python.exe``（agent 用的同一个解释器），
    按协议的 interface 所在目录解析却越出了项目根。与 agent 入口同一条平铺规则
    （:func:`flattened_entry_path`）映射回项目里；只认 ``python/python.exe`` 结尾的相对写法
    （与 agent 判定「项目自带 Python」同一判据），绝对路径、其它程序一律返回 None——
    越界的任意可执行文件不放行，由调用方跳过这条 pretask。
    """

    if not is_relative_entry_path(raw_exec):
        return None
    text = str(raw_exec).strip().strip('"').strip("'").replace("\\", "/")
    text = text.replace("${PROJECT_DIR}", "{PROJECT_DIR}")
    if text.startswith("{PROJECT_DIR}"):
        text = text[len("{PROJECT_DIR}") :].lstrip("/")
    parts = [part for part in text.split("/") if part not in ("", ".")]
    if not parts or parts[0] != "..":
        return None
    if not text.casefold().endswith(_BUNDLED_PYTHON_SUFFIX):
        return None
    return flattened_entry_path(raw_exec)


def describe_pretask_python_fallback(raw_exec: str, used: str) -> str:
    """pretask 的解释器越界、改用项目自带 Python 时给人看的说明（投影与运行计划共用）。"""

    return (
        f"运行前设置的解释器 {raw_exec} 越出了项目目录（按发行包布局它就是项目自带的 Python），"
        f"已改用项目里的 {used}"
    )


def describe_pretask_exec_outside(raw_exec: str) -> str:
    """pretask 的可执行文件在项目目录之外、不运行它时给人看的说明（投影与运行计划共用）。"""

    return (
        f"运行前设置的可执行文件 {raw_exec} 在项目目录之外，AUTO-MAS 不运行项目目录外的程序，"
        "运行时跳过这一项运行前设置"
    )


#: 源码仓里 agent 的开发者写法 ``uv run agent/main.py``：AUTO-MAS 不支持（见 :func:`describe_uv_agent`）。
UV_LAUNCHER_NAMES = frozenset({"uv", "uv.exe", "uvx", "uvx.exe"})


def is_uv_launcher(child_exec: str) -> bool:
    """agent 的 ``child_exec`` 是不是 uv / uvx（不管写的是裸名字还是路径）。"""

    name = str(child_exec or "").strip().strip('"').strip("'").replace("\\", "/")
    return name.rsplit("/", 1)[-1].casefold() in UV_LAUNCHER_NAMES


def describe_uv_agent(label: str) -> str:
    """agent 用 uv 启动时给用户的报错。"""

    return (
        f"{label} 用 uv 启动（uv run …），这是源码仓的开发者写法，AUTO-MAS 不支持："
        "uv 会按项目自己的锁文件另建环境，里面的 maafw 未必与运行用的 MaaFramework 同版本，"
        "Agent 会连不上。请把 child_exec 改成 python（AUTO-MAS 按 requirements.txt 给它建"
        "隔离环境，maafw 钉成运行用的版本），或导入打包好的发行包"
    )
