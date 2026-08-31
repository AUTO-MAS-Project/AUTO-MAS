"""OK-NTE 节点日志采集参数与收尾解析。"""

import ast
import re

from app.log_box.logtype import LogType

OKNTE_PUSH_RULES: list[tuple[str, str] | tuple[str, str, str]] = [
    (r"任务完成: (.+)", r'"✅ 成功: " + $((?:任务完成: )(.+))'),
    (r"任务失败: (.+)", r'"❌ 失败: " + $((?:任务失败: )(.+))'),
    (r"info_set skipped \[(.*)\]", r'"SKIP:" + $((?:info_set skipped \[)(.*)\])'),
    (r"当前体力 (\d+)", r'"CUR:" + $((?:当前体力 )(\d+))'),
    (r"体力消耗目标 (\d+)", r'"TGT:" + $((?:体力消耗目标 )(\d+))'),
]

_OKNTE_STATUS_RANK = {"✅ 成功": 1, "⏭ 跳过": 2, "❌ 失败": 3}


def _parse_skip_list(payload: str) -> list[str]:
    """把逗号分隔的 Python 字面量片段解析为节点名列表。"""

    try:
        value = ast.literal_eval(f"[{payload}]")
    except Exception:
        return []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


def oknte_resolve(results: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """合并 OK-NTE 节点状态，并计算最后一次采集到的剩余体力。"""

    order: list[str] = []
    states: dict[str, tuple[int, str]] = {}
    cur_stamina: int | None = None
    target_stamina: int | None = None

    def mark(status: str, node: str) -> None:
        if node in order:
            order.remove(node)
        order.append(node)
        rank = _OKNTE_STATUS_RANK[status]
        if rank > states.get(node, (0, ""))[0]:
            states[node] = rank, status

    for _, text in results:
        match = re.match(r"^(✅ 成功|⏭ 跳过|❌ 失败): (.*)$", text)
        if match:
            mark(match.group(1), match.group(2))
        elif text.startswith("SKIP:"):
            for node in _parse_skip_list(text[5:]):
                mark("⏭ 跳过", node)
        elif text.startswith("CUR:"):
            try:
                cur_stamina = int(text[4:])
            except ValueError:
                pass
        elif text.startswith("TGT:"):
            try:
                target_stamina = int(text[4:])
            except ValueError:
                pass

    output = [(LogType.NORMAL, f"{states[node][1]}: {node}") for node in order]
    if cur_stamina is not None and target_stamina is not None:
        output.append(
            (LogType.NORMAL, f"⚡️ 剩余体力: {max(cur_stamina - target_stamina, 0)}")
        )
    return output
