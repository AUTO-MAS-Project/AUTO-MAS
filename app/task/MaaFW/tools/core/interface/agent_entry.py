"""agent 入口脚本的 CFA 兜底规则；导入投影与运行时 agent 命令共用这一处。

CFA（MFW-PyQt6）解析 agent 入口时（``interface_manager._resolve_agent_entry``），child_args
里的入口脚本解析不到存在的文件，就退回 ``<interface 所在目录>/agent/main.py``。它的源码热更新
把 tag 源码的 ``assets/`` 平铺到包根、``agent/`` 放包根，却不改 child_args，于是包根
interface 里留着源码仓写法 ``../agent/main.py``——CFA 靠这个兜底照常能跑。
"""

from __future__ import annotations

#: 兜底入口，相对 interface 所在目录。
CFA_FALLBACK_AGENT_ENTRY = "agent/main.py"

_PYTHON_ENTRY_SUFFIXES = (".py", ".pyw")


def is_python_entry_arg(value: str) -> bool:
    """child_args 里的这一项是不是 Python 入口脚本路径（按后缀）。"""

    return value.strip().strip('"').strip("'").lower().endswith(_PYTHON_ENTRY_SUFFIXES)


def describe_cfa_agent_entry_fallback(raw_arg: str, used: str) -> str:
    """兜底生效时给人看的说明。"""

    return (
        f"agent 入口 {raw_arg} 在项目里找不到（越出项目目录或文件不存在），"
        f"这是 CFA 源码热更新后的布局，已按 CFA 的做法改用 {used}"
    )
