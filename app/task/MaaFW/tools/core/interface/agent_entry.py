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
