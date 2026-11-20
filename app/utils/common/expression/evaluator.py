"""表达式编译器与求值器

将 parser 产出的 AST 编译为可执行对象，对文本执行提取并返回结果。

编译后的 CompiledExpression.extract(text) 流程::

    对每一行（; 分隔）:
      对每个片段（+ 连接）:
        - 字面量：直接拼接
        - 正则片段：finditer 提取 → 函数链处理 → 拼接
      若行内所有正则片段均命中，输出该行
    各行以 \\n 拼接为最终结果
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Optional, Pattern

from .functions import FUNCTIONS, Arg, ExpressionFunction
from .parser import (
    ExpressionError,
    LiteralSegment,
    is_qualified_function_name,
    parse,
)

# ==================== 编译后的片段 ====================


@dataclass
class _CompiledCall:
    name: str
    function: ExpressionFunction
    args: tuple[Arg, ...]
    strict: bool


@dataclass
class _CompiledRegex:
    """编译后的正则片段：预编译正则 + 函数链"""

    pattern: Optional[Pattern[str]]
    functions: list[_CompiledCall] = field(default_factory=list)
    full_text: bool = False  # True 表示 $() 为空，直接返回整段文本


@dataclass
class _CompiledLiteral:
    """编译后的字面量片段"""

    text: str


_CompiledSegment = _CompiledRegex | _CompiledLiteral


# ==================== 编译后的表达式 ====================


class ExpressionEvaluationError(ExpressionError):
    """已编译的函数调用执行失败。"""


@dataclass
class CompiledExpression:
    """编译后的提取表达式

    由 compile_expression() 创建，调用 extract(text) 对文本执行提取。

    Attributes:
        lines: 二维列表，每个子列表是一行的编译后片段
    """

    lines: list[list[_CompiledSegment]] = field(default_factory=list)

    def extract(self, text: str) -> str:
        """对文本执行提取，返回拼接后的结果字符串

        Args:
            text: 待提取的文本（多行模式为窗口内容，正则模式为单行）

        Returns:
            提取并拼接后的字符串；无命中时返回空字符串
        """
        if not self.lines:
            return text

        output_lines: list[str] = []
        for line in self.lines:
            parts: list[str] = []
            all_matched = True
            for seg in line:
                if isinstance(seg, _CompiledLiteral):
                    parts.append(seg.text)
                else:
                    result = self._eval_regex(seg, text)
                    if result is None:
                        all_matched = False
                        break
                    parts.append(result)
            if all_matched:
                output_lines.append("".join(parts))

        return "\n".join(output_lines)

    def _eval_regex(self, seg: _CompiledRegex, text: str) -> Optional[str]:
        """执行单个正则片段的提取 + 函数链处理

        Args:
            seg: 编译后的正则片段
            text: 待提取文本

        Returns:
            提取并处理后的字符串（无捕获组时为空串，继续后续函数链与拼接）；
            正则未命中或编译失败时返回 None，此时整行跳过
        """
        # 空 $() → 直接返回整段文本，再执行函数链
        if seg.full_text:
            return self._apply_functions(seg.functions, text)

        if seg.pattern is None:
            return None

        matches = list(seg.pattern.finditer(text))
        if not matches:
            return None  # 正则未命中 → 该片段不产出，整行跳过

        # 收集提取内容：仅取捕获组中的非空组；无捕获组时返回空串继续处理
        # （如需提取整段匹配，请用捕获组包裹正则，例如 (任务结束) 或 (.*)）
        collected: list[str] = []
        for m in matches:
            for g in m.groups():
                if g:
                    collected.append(g)

        return self._apply_functions(seg.functions, "\n".join(collected))

    def _apply_functions(self, calls: list[_CompiledCall], result: str) -> str:
        for call in calls:
            try:
                transformed = call.function(result, list(call.args))
                if call.strict and not isinstance(transformed, str):
                    raise TypeError("表达式函数必须返回字符串")
            except (ValueError, TypeError) as exc:
                if call.strict:
                    raise ExpressionEvaluationError(
                        f"函数 '{call.name}' 执行失败"
                    ) from exc
                # 旧规则继续跳过参数失败的函数，保留此次变换前的文本。
                continue
            result = transformed
        return result


# ==================== 编译入口 ====================


def compile_expression(
    expr_str: str,
    *,
    extensions: Mapping[str, ExpressionFunction] | None = None,
    strict_functions: bool = False,
) -> CompiledExpression:
    """编译提取表达式字符串

    Args:
        expr_str: 表达式字符串，如 $(\\d+).replace("/","-")+"："+$(.+)
        extensions: 当前会话的扩展函数，键为 namespace:name，调用错误始终向上报告。
        strict_functions: 内置函数调用错误也向上报告；默认沿用旧规则跳过失败变换的行为。

    Returns:
        CompiledExpression 对象

    Raises:
        ExpressionError: 语法错误、函数名称不可用或正则编译失败
    """
    ast_lines = parse(expr_str, allow_qualified=extensions is not None)
    compiled_lines: list[list[_CompiledSegment]] = []

    functions = dict(FUNCTIONS)
    if extensions is not None:
        for name, function in extensions.items():
            if name in functions or not is_qualified_function_name(name):
                raise ExpressionError(
                    f"扩展函数名 '{name}' 必须是未注册的 namespace:name"
                )
            functions[name] = function

    for line in ast_lines:
        compiled_line: list[_CompiledSegment] = []
        for seg in line:
            if isinstance(seg, LiteralSegment):
                compiled_line.append(_CompiledLiteral(text=seg.text))
            else:
                calls: list[_CompiledCall] = []
                for fn in seg.functions:
                    function = functions.get(fn.name)
                    if function is None:
                        available = ", ".join(sorted(functions))
                        raise ExpressionError(
                            f"未知函数 '{fn.name}'，可用函数: {available}"
                        )
                    calls.append(
                        _CompiledCall(
                            name=fn.name,
                            function=function,
                            args=tuple(fn.args),
                            strict=strict_functions or ":" in fn.name,
                        )
                    )
                # 空 $() → full_text 模式，直接返回整段文本
                if not seg.pattern_str.strip():
                    compiled_line.append(
                        _CompiledRegex(pattern=None, functions=calls, full_text=True)
                    )
                else:
                    # 编译正则（启用 DOTALL 以跨行匹配）
                    try:
                        pattern = re.compile(seg.pattern_str, re.DOTALL)
                    except re.error as e:
                        # 正则语法错误直接抛出，由校验/调试接口向用户返回具体信息，
                        # 避免非法表达式被编译为「无匹配」后运行时静默失效
                        raise ExpressionError(
                            f"正则语法错误 '{seg.pattern_str}': {e}"
                        ) from e
                    compiled_line.append(
                        _CompiledRegex(
                            pattern=pattern, functions=calls, full_text=False
                        )
                    )
        compiled_lines.append(compiled_line)

    return CompiledExpression(lines=compiled_lines)
