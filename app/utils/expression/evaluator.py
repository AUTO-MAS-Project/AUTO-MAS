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
from dataclasses import dataclass, field
from typing import Optional, Pattern

from .functions import FUNCTIONS, apply_function
from .parser import (
    ExpressionError,
    FunctionCall,
    LiteralSegment,
    RegexSegment,
    Segment,
    parse,
)


# ==================== 编译后的片段 ====================

@dataclass
class _CompiledRegex:
    """编译后的正则片段：预编译正则 + 函数链"""

    pattern: Optional[Pattern[str]]
    functions: list[FunctionCall] = field(default_factory=list)
    full_text: bool = False  # True 表示 $() 为空，直接返回整段文本


@dataclass
class _CompiledLiteral:
    """编译后的字面量片段"""

    text: str


_CompiledSegment = _CompiledRegex | _CompiledLiteral


# ==================== 编译后的表达式 ====================

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
            result = text
            for func in seg.functions:
                try:
                    result = apply_function(func.name, func.args, result)
                except (ValueError, TypeError):
                    continue
            return result

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

        result = "\n".join(collected)  # 无捕获组或组全空时为空串

        # 依次执行函数链
        for func in seg.functions:
            try:
                result = apply_function(func.name, func.args, result)
            except (ValueError, TypeError) as e:
                # 函数执行失败时跳过，保留原文本
                continue

        return result


# ==================== 编译入口 ====================

def compile_expression(expr_str: str) -> CompiledExpression:
    """编译提取表达式字符串

    Args:
        expr_str: 表达式字符串，如 $(\\d+).replace("/","-")+"："+$(.+)

    Returns:
        CompiledExpression 对象

    Raises:
        ExpressionError: 语法错误或正则编译失败
    """
    ast_lines = parse(expr_str)
    compiled_lines: list[list[_CompiledSegment]] = []

    # 校验函数名：未知函数名在编译期即报错，避免运行时静默失效
    available = ", ".join(sorted(FUNCTIONS.keys()))
    for line in ast_lines:
        for seg in line:
            if isinstance(seg, RegexSegment):
                for fn in seg.functions:
                    if fn.name not in FUNCTIONS:
                        raise ExpressionError(
                            f"未知函数 '{fn.name}'，可用函数: {available}"
                        )

    for line in ast_lines:
        compiled_line: list[_CompiledSegment] = []
        for seg in line:
            if isinstance(seg, LiteralSegment):
                compiled_line.append(_CompiledLiteral(text=seg.text))
            else:
                # 空 $() → full_text 模式，直接返回整段文本
                if not seg.pattern_str.strip():
                    compiled_line.append(
                        _CompiledRegex(
                            pattern=None, functions=seg.functions, full_text=True
                        )
                    )
                else:
                    # 编译正则（启用 DOTALL 以跨行匹配）
                    try:
                        pattern = re.compile(seg.pattern_str, re.DOTALL)
                    except re.error as e:
                        # 单条正则编译失败时 pattern 置 None，求值时视为未命中
                        pattern = None
                    compiled_line.append(
                        _CompiledRegex(
                            pattern=pattern, functions=seg.functions, full_text=False
                        )
                    )
        compiled_lines.append(compiled_line)

    return CompiledExpression(lines=compiled_lines)
