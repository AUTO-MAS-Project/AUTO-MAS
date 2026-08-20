"""可编程规则构建器 Rule

``col.rule(regex, type).get(1).trim().end()`` 以编程方式构建提取规则。
函数链最终编译为表达式字符串，交给表达式引擎编译——函数名校验与引擎一致，
同时接受内置 FUNCTIONS 与注入 REGISTRY 的自定义算子（Process）。
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Union

from app.utils.LogPatternExtractor import LOG_TYPE_NORMAL

if TYPE_CHECKING:
    from .collect import LogCollect

# 函数链参数：字符串或整数
_RuleArg = Union[str, int]


class Rule:
    """可编程规则构建器

    由 ``col.rule(regex, type)`` 创建；函数链方法逐个追加算子，end() 完成
    构建并注册进 LogCollect。
    """

    def __init__(
        self,
        collect: "LogCollect",
        match_regex: str,
        log_type: str = LOG_TYPE_NORMAL,
    ):
        self._collect = collect
        self._match_regex = match_regex
        self._log_type = log_type
        self._scope = ""  # $() 内的提取正则作用域；空 = 取整行
        self._calls: list[tuple[str, list[_RuleArg]]] = []

    # ---------- 提取作用域 ----------

    def regex(self, pattern: str) -> "Rule":
        """设置提取正则作用域（表达式 $() 内的正则）；不调用时取整行文本"""
        self._scope = pattern
        return self

    # ---------- 函数链 ----------

    def func(self, name: str, *args: _RuleArg) -> "Rule":
        """追加任意函数（含注入 REGISTRY 的自定义 Process 算子）"""
        self._calls.append((name, list(args)))
        return self

    def cut(self, num: int) -> "Rule":
        return self.func("cut", num)

    def get(self, num: int) -> "Rule":
        return self.func("get", num)

    def sub(self, start: int, end: int) -> "Rule":
        return self.func("sub", start, end)

    def cutby(self, *args: _RuleArg) -> "Rule":
        return self.func("cutby", *args)

    def subby(self, *args: _RuleArg) -> "Rule":
        return self.func("subby", *args)

    def replace(self, old: str, new: str) -> "Rule":
        return self.func("replace", old, new)

    def trim(self) -> "Rule":
        return self.func("trim")

    def upper(self) -> "Rule":
        return self.func("upper")

    def lower(self) -> "Rule":
        return self.func("lower")

    # ---------- 完成构建 ----------

    def _build_expr(self) -> str:
        """把提取作用域 + 函数链拼为表达式字符串"""
        parts = [f"$({self._scope})"]
        for name, args in self._calls:
            arg_text = ", ".join(
                json.dumps(arg, ensure_ascii=False)
                if isinstance(arg, str)
                else str(arg)
                for arg in args
            )
            parts.append(f".{name}({arg_text})")
        return "".join(parts)

    def end(self) -> "LogCollect":
        """完成构建：编译提取表达式并注册进 LogCollect"""
        expr = self._build_expr()
        self._collect.add_rule(self._match_regex, expr, self._log_type)
        return self._collect
