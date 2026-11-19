"""@@LOGBOX@@ 结果标记：脚本子进程宿主下的结果回传通道

脚本子进程无法直接写 MAS 内存中的 push_log，调用方把处理好的结果渲染为
@@LOGBOX@@ 受控 stdout 标记回传；MAS 侧 check_log 单行嗅探后写入
cur_user_item.push_log。MAS 进程宿主（专项适配器）直接注入 sink，不走标记。
"""

from __future__ import annotations

import json

from app.utils.common.log.legacy_protocol import MSG_PREFIX, parse_marker

__all__ = ["MSG_PREFIX", "emit", "parse_marker", "render_flush", "render_push"]


def render_push(text: str, log_type: str) -> str:
    """渲染 push 标记行：@@LOGBOX@@{"op":"push","type":...,"text":...}"""
    payload = json.dumps(
        {"op": "push", "type": log_type, "text": text},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"{MSG_PREFIX}{payload}"


def render_flush() -> str:
    """渲染 flush 标记行：@@LOGBOX@@{"op":"flush"}"""
    payload = json.dumps({"op": "flush"}, separators=(",", ":"))
    return f"{MSG_PREFIX}{payload}"


def emit(line: str) -> None:
    """脚本子进程宿主下把标记行写入 stdout"""
    print(line, flush=True)
