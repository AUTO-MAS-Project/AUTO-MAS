"""项目在 pipeline 节点上声明的 MAS 联动信号（``attach.auto_mas``）。

与项目约定：进游戏流程里识别「停服维护」「需要更新客户端」的节点写上

- 字符串：``"attach": {"auto_mas": "server_maintenance"}``——节点识别命中即该信号；
- 对象：``"attach": {"auto_mas": {"server_maintenance": ["<维护画面的文字>"],
  "client_update_required": ["<更新提示的文字>"]}}``——一个节点认多种画面，拿 OCR 识别
  文本逐个 ``re.search``。**不按键顺序**：MaaFW 的 ``get_node_data`` 不保留 attach 的
  键顺序（写的维护在前，读回来可能更新在前），固定先判维护、再判更新；两个都中按维护
  算——维护是暂时的，跳过比判失败安全。

写了 ``auto_mas`` 就是项目作者声明「在 MAS 下启用这个节点」：MAS 运行时一律强开，
叠在任务自身与全部选项的覆盖之后（项目自带的开关只对其他外壳有效）。
本模块只做纯逻辑（解析、匹配、强开覆盖），不碰 binding，worker 与测试都直接用。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

MAS_SIGNAL_ATTACH_KEY = "auto_mas"
SERVER_MAINTENANCE = "server_maintenance"
CLIENT_UPDATE_REQUIRED = "client_update_required"
MAS_SIGNALS: tuple[str, ...] = (SERVER_MAINTENANCE, CLIENT_UPDATE_REQUIRED)

# 判定信号的框架通知：节点识别命中就算，不等动作（维护节点多是没有 next 的
# [JumpBack]，等动作只会看它原地点下去）。
SIGNAL_NOTIFICATION = "Node.Recognition.Succeeded"


@dataclass(frozen=True)
class MaaFWSignalSpec:
    """一个信号节点的声明：``fixed`` 是字符串形状；``rules`` 是对象形状（按固定优先级）。"""

    node: str
    fixed: str | None = None
    rules: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...] = field(
        default_factory=tuple
    )


def parse_signal_spec(
    node: str, node_data: Any
) -> tuple[MaaFWSignalSpec | None, list[str]]:
    """从 ``resource.get_node_data`` 的结果里取出信号声明。

    返回 (声明或 None, 告警)。没写 ``auto_mas`` 的节点返回 (None, [])；写法非法
    （未知信号名、规则不是字符串列表）的整个节点忽略并给一条告警，不影响运行。
    正则编译失败的那一条按字面量匹配，同样给告警。
    """

    if not isinstance(node_data, dict):
        return None, []
    attach = node_data.get("attach")
    if not isinstance(attach, dict) or MAS_SIGNAL_ATTACH_KEY not in attach:
        return None, []
    value = attach[MAS_SIGNAL_ATTACH_KEY]
    prefix = f"节点 {node} 的 attach.{MAS_SIGNAL_ATTACH_KEY}"
    if isinstance(value, str):
        if value in MAS_SIGNALS:
            return MaaFWSignalSpec(node=node, fixed=value), []
        return None, [f"{prefix} 写的是未知信号 {value!r}，已忽略该节点"]
    if not isinstance(value, dict) or not value:
        return None, [f"{prefix} 既不是信号名也不是「信号 → 正则列表」，已忽略该节点"]

    warnings: list[str] = []
    rules: list[tuple[str, tuple[re.Pattern[str], ...]]] = []
    for signal, patterns in value.items():
        if signal not in MAS_SIGNALS:
            return None, [f"{prefix} 写了未知信号 {signal!r}，已忽略该节点"]
        if (
            not isinstance(patterns, list)
            or not patterns
            or not all(isinstance(item, str) and item for item in patterns)
        ):
            return None, [
                f"{prefix} 里 {signal} 的值不是非空的字符串列表，已忽略该节点"
            ]
        compiled: list[re.Pattern[str]] = []
        for pattern in patterns:
            try:
                compiled.append(re.compile(pattern))
            except re.error as exc:
                warnings.append(
                    f"{prefix} 里 {signal} 的正则 {pattern!r} 无法编译（{exc}），"
                    "按字面量匹配"
                )
                compiled.append(re.compile(re.escape(pattern)))
        rules.append((signal, tuple(compiled)))
    # 固定优先级（见模块说明），与 attach 里写的顺序无关
    rules.sort(key=lambda rule: MAS_SIGNALS.index(rule[0]))
    return MaaFWSignalSpec(node=node, rules=tuple(rules)), warnings


def recognition_texts(details: Any) -> list[str] | None:
    """``Node.Recognition.Succeeded`` 里 OCR 识别到的文本；不是 OCR / 取不到时返回 None。

    先取 ``reco_details.detail.filtered[].text``（过了 expected 的那些），没有再取
    ``best.text``。
    """

    if not isinstance(details, dict):
        return None
    reco = details.get("reco_details")
    if not isinstance(reco, dict):
        return None
    detail = reco.get("detail")
    if not isinstance(detail, dict):
        return None
    texts: list[str] = []
    filtered = detail.get("filtered")
    if isinstance(filtered, list):
        for item in filtered:
            text = item.get("text") if isinstance(item, dict) else None
            if isinstance(text, str) and text:
                texts.append(text)
    if not texts:
        best = detail.get("best")
        text = best.get("text") if isinstance(best, dict) else None
        if isinstance(text, str) and text:
            texts.append(text)
    return texts or None


def match_signal(
    spec: MaaFWSignalSpec, details: Any
) -> tuple[str | None, list[str] | None]:
    """节点识别命中后判定信号，返回 (信号或 None, 用于判定的识别文本)。

    对象形状按 ``MAS_SIGNALS`` 的固定优先级判（``parse_signal_spec`` 已排好序）。
    """

    if spec.fixed is not None:
        return spec.fixed, None
    texts = recognition_texts(details)
    if not texts:
        return None, None
    for signal, patterns in spec.rules:
        for pattern in patterns:
            if any(pattern.search(text) for text in texts):
                return signal, texts
    return None, texts


def signal_enable_override(nodes: Any) -> dict[str, dict[str, bool]]:
    """强开信号节点的 pipeline 覆盖；要叠在任务自身与全部选项的覆盖**之后**。"""

    return {name: {"enabled": True} for name in sorted(nodes)}


__all__ = [
    "CLIENT_UPDATE_REQUIRED",
    "MAS_SIGNALS",
    "MAS_SIGNAL_ATTACH_KEY",
    "MaaFWSignalSpec",
    "SERVER_MAINTENANCE",
    "SIGNAL_NOTIFICATION",
    "match_signal",
    "parse_signal_spec",
    "recognition_texts",
    "signal_enable_override",
]
