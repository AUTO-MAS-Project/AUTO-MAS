"""OK-NTE 节点日志采集参数（log_box 实例的喂参方）

OK-NTE 专项作为 log_box 的一个实例：本模块只提供参数（日志路径、规则、后置
处理器），日志获取、规则匹配、后置处理与推送全部由 log_box 完成。

规则说明（从 ok-nte 源码 `src/tasks/daily/DailyRoutineTask.py` 推导，与
working/logs/ok-script.log 实际输出吻合，无需前置翻译——日志文本已是中文）：

- 节点级成功/失败：`DailyRoutineTask:任务完成: 节点` / `任务失败: 节点`，
  由 `_execute_routine_item` 对每个已启用的日常子任务直接落日志，节点名即
  success/failed 列表里的中文名。
- 跳过列表：收尾 `_print_result()` 统一输出
  `info_set skipped ['节点', ...]`（含互斥组里被排挤的项与禁用项）。
- 整体异常兜底：`run()` 的 except 分支额外打 `info_set 当前失败任务` 并
  `log_error("DailyRoutineTask error", err)`，随后 `_print_result()`；对应
  节点已由「任务失败:」行体现，这里不再单独加规则。
- 体力追踪：副本/异象任务开始时经 `BaseNTETask.get_stamina()` 落「当前体力」，
  开刷前据「体力消耗目标」决定刷多少把；每个耗体任务开始时都会重读一次当前
  体力，故最后一次「当前体力 − 体力消耗目标」即刷完全部本后的剩余体力。

规则产出「状态标记」，最终状态由 oknte_resolve 后处理解析并聚合：
  - "✅ 成功: 节点" = 成功
  - "⏭ 跳过: 节点" = 跳过（如互斥组未选中项）
  - "❌ 失败: 节点" = 失败
状态优先级 失败 > 跳过 > 成功；节点顺序按最后一次出现排列。体力相关行
（CUR/TGT 标记）不进入节点聚合，resolve 据此追加一行「⚡️ 剩余体力」。
"""

import ast
import re

from app.log_box.logtype import LogType

# 推送规则：(匹配正则, 提取表达式 [, 日志类型])；匹配与提取均在原始日志行。
# 顺序敏感：失败/成功/跳过/体力目标标记各自独立成行，聚合顺序由后处理器保持执行序。
OKNTE_PUSH_RULES: list[tuple[str, str] | tuple[str, str, str]] = [
    # 节点级状态（每个启用的日常子任务都会走到「任务完成」或「任务失败」）
    (r"任务完成: (.+)", r'"✅ 成功: " + $((?:任务完成: )(.+))'),
    (r"任务失败: (.+)", r'"❌ 失败: " + $((?:任务失败: )(.+))'),
    # 跳过列表：收尾 info_set skipped ['a', 'b']，解析为逐个「⏭ 跳过: 节点」
    (r"info_set skipped \[(.*)\]", r'"SKIP:" + $((?:info_set skipped \[)(.*)\])'),
    # 体力追踪：当前体力 + 本次实际消耗目标；resolve 据此计算刷完剩余体力
    (r"当前体力 (\d+)", r'"CUR:" + $((?:当前体力 )(\d+))'),
    (r"体力消耗目标 (\d+)", r'"TGT:" + $((?:体力消耗目标 )(\d+))'),
]

# 状态优先级：失败 > 跳过 > 成功
_OKNTE_STATUS_RANK = {"✅ 成功": 1, "⏭ 跳过": 2, "❌ 失败": 3}


def _oknte_parse_skip_list(payload: str) -> list[str]:
    """把 `'A', 'B'` 这类 Python 列表字面量片段解析为节点名列表。"""
    try:
        value = ast.literal_eval(f"[{payload}]")
    except Exception:
        return []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


def oknte_resolve(
    results: list[tuple[str, str, float]]
) -> list[tuple[str, str, float]]:
    """后处理：按节点解析最终状态（失败 > 跳过 > 成功），保持最后一次出现顺序

    输入/输出均为 ``(log_type, text, ts)`` 元组（与 log_box `_PostProcessor`
    契约一致），日志类型与采集时间戳随元组一并保留。规则产出三类标记：「状态:
    节点」、SKIP 列表（拆成逐个「⏭ 跳过: 节点」）与体力 CUR/TGT（不参与节点
    聚合）。每次耗体任务开始时都会重读「当前体力」，故取最后一次 CUR 与 TGT
    之差作为刷完剩余体力，追加在报告末尾（时间戳取 TGT 采集时刻）。
    """
    order: list[str] = []
    states: dict[str, tuple[int, str]] = {}
    ts_of: dict[str, float] = {}
    cur_stamina: int | None = None
    target_stamina: int | None = None
    target_ts: float = 0.0

    def _mark(status: str, node: str, ts: float) -> None:
        rank = _OKNTE_STATUS_RANK[status]
        if node in states:
            order.remove(node)  # 移至末尾：保留最后一次出现顺序
        order.append(node)
        if rank >= states.get(node, (0, ""))[0]:
            states[node] = (rank, status)
            ts_of[node] = ts

    for _, text, ts in results:
        m = re.match(r"^(✅ 成功|⏭ 跳过|❌ 失败): (.*)$", text)
        if m:
            _mark(m.group(1), m.group(2), ts)
        elif text.startswith("SKIP:"):
            for node in _oknte_parse_skip_list(text[len("SKIP:"):]):
                _mark("⏭ 跳过", node, ts)
        elif text.startswith("CUR:"):
            try:
                cur_stamina = int(text[len("CUR:"):])
            except ValueError:
                pass
        elif text.startswith("TGT:"):
            try:
                target_stamina = int(text[len("TGT:"):])
                target_ts = ts
            except ValueError:
                pass
        else:
            # 仅接受显式状态标记；未知文本不纳入报告，避免把意外的提取结果
            # 误判为成功（当前规则均输出显式标记，命中此处说明规则输出异常）
            continue

    result = [
        (LogType.NORMAL, f"{states[node][1]}: {node}", ts_of[node])
        for node in order
    ]
    # 规则均产出普通类型，节点级失败由文本「❌ 失败:」体现，不依赖逐条类型过滤
    if cur_stamina is not None and target_stamina is not None:
        result.append(
            (
                LogType.NORMAL,
                f"⚡️ 剩余体力: {max(cur_stamina - target_stamina, 0)}",
                target_ts,
            )
        )
    return result