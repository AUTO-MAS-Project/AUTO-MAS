"""表达式解析器

将提取表达式字符串解析为 AST，供 evaluator 编译执行。

语法规则::

    expression = line (';' line)*            # ; 分隔输出行
    line       = segment ('+' segment)*       # + 连接同行片段
    segment    = regex_segment | literal
    regex_segment = '$(' regex ')' ('.' function)*
    literal    = '"' text '"'                 # 支持 \\" \\\\ \\n \\t 转义
    function   = identifier '(' args ')'
    args       = arg (',' arg)* | ε
    arg        = literal | number

示例::

    $(\\d+/\\d+).replace("/","-")+"："+$(邮件：[^\\n]+)
    $(任务结束);$(邮件：[^\\n]+)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union


# ==================== AST 节点 ====================


@dataclass
class FunctionCall:
    """函数调用：名称 + 参数列表（str 或 int）"""

    name: str
    args: list[Union[str, int]] = field(default_factory=list)


@dataclass
class LiteralSegment:
    """字面量片段"""

    text: str


@dataclass
class RegexSegment:
    """正则片段：原始正则字符串 + 函数链"""

    pattern_str: str
    functions: list[FunctionCall] = field(default_factory=list)


Segment = Union[LiteralSegment, RegexSegment]


# ==================== 异常 ====================


class ExpressionError(Exception):
    """表达式语法或编译错误"""


# ==================== 解析器 ====================


def parse(expr_str: str) -> list[list[Segment]]:
    """将表达式字符串解析为「行 → 片段」二维列表。

    Args:
        expr_str: 表达式字符串

    Returns:
        lines: 每个元素是一行的片段列表

    Raises:
        ExpressionError: 语法错误
    """
    if not expr_str or not expr_str.strip():
        return []

    parser = _Parser(expr_str)
    return parser.parse()


class _Parser:
    """字符级扫描解析器"""

    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.length = len(text)

    def parse(self) -> list[list[Segment]]:
        lines: list[list[Segment]] = []
        current_line: list[Segment] = []

        while self.pos < self.length:
            ch = self.text[self.pos]
            if ch == ";":
                # 换行符：结束当前行
                if current_line:
                    lines.append(current_line)
                    current_line = []
                self.pos += 1
            elif ch == "+":
                # 连接符：跳过，片段已在 current_line 中
                self.pos += 1
            elif ch == '"':
                # 字面量
                seg = self._parse_literal()
                current_line.append(seg)
            elif ch == "$" and self._peek(1) == "(":
                # 正则作用域
                seg = self._parse_regex_segment()
                current_line.append(seg)
            elif ch.isspace():
                self.pos += 1
            else:
                raise ExpressionError(
                    f"位置 {self.pos}：非法字符 '{ch}'，"
                    f'表达式片段必须以 $() 或 "" 开头'
                )

        if current_line:
            lines.append(current_line)

        return lines

    # ---------- 字面量 ----------

    def _parse_literal(self) -> LiteralSegment:
        """解析 "..." 字面量，支持 \\" \\\\ \\n \\t 转义"""
        assert self.text[self.pos] == '"'
        self.pos += 1  # 跳过开头的 "
        chars: list[str] = []
        while self.pos < self.length:
            ch = self.text[self.pos]
            if ch == "\\":
                if self.pos + 1 < self.length:
                    nxt = self.text[self.pos + 1]
                    if nxt == '"':
                        chars.append('"')
                        self.pos += 2
                        continue
                    elif nxt == "\\":
                        chars.append("\\")
                        self.pos += 2
                        continue
                    elif nxt == "n":
                        chars.append("\n")
                        self.pos += 2
                        continue
                    elif nxt == "t":
                        chars.append("\t")
                        self.pos += 2
                        continue
                # 其他 \ 按字面量保留
                chars.append(ch)
                self.pos += 1
            elif ch == '"':
                self.pos += 1  # 跳过结尾的 "
                return LiteralSegment("".join(chars))
            else:
                chars.append(ch)
                self.pos += 1
        raise ExpressionError('字面量缺少闭合的 "')

    # ---------- 正则作用域 ----------

    def _parse_regex_segment(self) -> RegexSegment:
        """解析 $(regex) 及其后续函数链"""
        assert self.text[self.pos] == "$"
        self.pos += 2  # 跳过 $(
        depth = 1
        chars: list[str] = []
        while self.pos < self.length:
            ch = self.text[self.pos]
            if ch == "\\":
                # 转义字符：保留并跳过下一个
                chars.append(ch)
                self.pos += 1
                if self.pos < self.length:
                    chars.append(self.text[self.pos])
                    self.pos += 1
                continue
            elif ch == "(":
                depth += 1
                chars.append(ch)
                self.pos += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    self.pos += 1  # 跳过闭合 )
                    break
                chars.append(ch)
                self.pos += 1
            else:
                chars.append(ch)
                self.pos += 1
        if depth != 0:
            raise ExpressionError("正则作用域 $() 缺少闭合的 )")

        pattern_str = "".join(chars)
        # 允许空 $()：表示获取整行/整段文本，由 evaluator 特殊处理

        # 解析后续函数链
        functions = self._parse_function_chain()
        return RegexSegment(pattern_str=pattern_str, functions=functions)

    # ---------- 函数链 ----------

    def _parse_function_chain(self) -> list[FunctionCall]:
        """解析 .func(args).func2(args2)... 函数链"""
        functions: list[FunctionCall] = []
        while self.pos < self.length and self.text[self.pos] == ".":
            self.pos += 1  # 跳过 .
            name = self._parse_identifier()
            if not name:
                raise ExpressionError(f"位置 {self.pos}：'.' 后需要函数名")
            # 跳过空白
            self._skip_spaces()
            if self.pos >= self.length or self.text[self.pos] != "(":
                raise ExpressionError(f"函数 '{name}' 后需要 ()")
            self.pos += 1  # 跳过 (
            args = self._parse_args()
            if self.pos >= self.length or self.text[self.pos] != ")":
                raise ExpressionError(f"函数 '{name}' 的参数列表缺少闭合的 )")
            self.pos += 1  # 跳过 )
            functions.append(FunctionCall(name=name, args=args))
        return functions

    def _parse_identifier(self) -> str:
        """解析函数名（字母、数字、下划线）"""
        start = self.pos
        while self.pos < self.length:
            ch = self.text[self.pos]
            if ch.isalnum() or ch == "_":
                self.pos += 1
            else:
                break
        return self.text[start : self.pos]

    def _parse_args(self) -> list[Union[str, int]]:
        """解析函数参数列表"""
        args: list[Union[str, int]] = []
        self._skip_spaces()
        if self.pos < self.length and self.text[self.pos] == ")":
            return args  # 无参数
        while True:
            self._skip_spaces()
            if self.pos >= self.length:
                raise ExpressionError("参数列表不完整")
            ch = self.text[self.pos]
            if ch == '"':
                # 字符串参数
                seg = self._parse_literal()
                args.append(seg.text)
            elif ch == "-" or ch.isdigit():
                # 数字参数
                num = self._parse_number()
                args.append(num)
            else:
                raise ExpressionError(
                    f"位置 {self.pos}：参数必须为 \"字符串\" 或数字，得到 '{ch}'"
                )
            self._skip_spaces()
            if self.pos < self.length and self.text[self.pos] == ",":
                self.pos += 1  # 跳过 ,
                continue
            else:
                break
        return args

    def _parse_number(self) -> int:
        """解析整数（含负号）"""
        start = self.pos
        if self.text[self.pos] == "-":
            self.pos += 1
        while self.pos < self.length and self.text[self.pos].isdigit():
            self.pos += 1
        num_str = self.text[start : self.pos]
        if not num_str or num_str == "-":
            raise ExpressionError(f"位置 {start}：无效的数字")
        return int(num_str)

    # ---------- 辅助 ----------

    def _peek(self, offset: int = 0) -> str:
        pos = self.pos + offset
        if pos < self.length:
            return self.text[pos]
        return ""

    def _skip_spaces(self) -> None:
        while self.pos < self.length and self.text[self.pos].isspace():
            self.pos += 1
