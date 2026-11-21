"""建运行计划与预览共用的规则表：哪些任务不可选、哪些任务失败即结束本轮或失败不计、
哪些字符串输入项没填时不回落 default。

规则表是调用方（宿主按脚本类型）给的普通数据，核心不认识具体项目；建计划、展开任务快照
（``runner/task_selection``）与预览（``preview.apply_preview_plan_rules``）收同一份。没有
规则的项目传空表，行为与没有这一层时完全相同。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class MaaFWPlanRules:
    """建计划与预览的规则表；各表的键都是任务 ``entry``（``no_default_fallback_inputs`` 除外）。"""

    unselectable: Mapping[str, str] = field(default_factory=dict)
    """不可选任务：entry → 不能选的原因。预览给它们填 ``unselectableReason``；展开任务快照时
    在交给调用方排队列之前剔掉（连同选项），不进计划。"""

    abort_round: Mapping[str, str] = field(default_factory=dict)
    """失败即结束本轮：entry → 失败时报给用户的话，落到计划任务的 ``abortRoundMessage``。"""

    nonfatal: Mapping[str, str] = field(default_factory=dict)
    """失败不计：entry → 失败时接在日志后的说明，落到计划任务的 ``nonFatalMessage``。"""

    no_default_fallback_inputs: frozenset[tuple[str, str]] = frozenset()
    """字符串字段没填时不回落 default 的 input：``(选项名, 字段名)``。建计划时传给覆盖构建，
    预览里把这些字段的 ``default`` 置空。"""


EMPTY_PLAN_RULES = MaaFWPlanRules()
"""没有任何规则（通用项目）。"""


__all__ = ["EMPTY_PLAN_RULES", "MaaFWPlanRules"]
