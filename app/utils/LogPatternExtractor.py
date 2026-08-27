#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


"""日志模式提取工具

提供三种日志提取模式，供任务执行流（如推送日志采集）按可配置规则从
日志中过滤并提取关键内容：

1. 字符串切割（split）：按关键字过滤行，再掐头去尾提取中间内容
2. 正则（regex）：匹配正则过滤行，提取表达式用 $() 语法提取并处理内容
3. 多行聚合（multiline）：由起始/结束正则划定多行窗口，再用提取表达式
   从窗口内容中提取字段并拼接，适合跨行关联日志的采集

提取表达式语法（详见 app.utils.expression）::

    $(正则)              正则提取作用域
    "文本"               字面量（支持 \" \\ \n \t 转义）
    +                    同行拼接
    ;                    换行拼接
    $(正则).函数(参数)   函数链处理（cut/get/sub/cutby/subby/replace/trim/upper/lower）

本模块仅提供无副作用的纯函数与数据类，不引入业务策略与 IO，便于跨任务复用。
"""

import json
import re
from dataclasses import dataclass, field
from typing import Optional, Pattern, Union

from app.utils.expression import CompiledExpression, ExpressionError, compile_expression

# ==================== 类型定义 ====================
PATTERN_TYPE_SPLIT = "split"
PATTERN_TYPE_REGEX = "regex"
PATTERN_TYPE_MULTILINE = "multiline"
SUPPORTED_PATTERN_TYPES = (PATTERN_TYPE_SPLIT, PATTERN_TYPE_REGEX, PATTERN_TYPE_MULTILINE)

# 规则日志类型：普通 = 任何推送报告均包含；失败 = 仅在存在未完成用户的报告中包含
LOG_TYPE_NORMAL = "普通"
LOG_TYPE_ERROR = "失败"
SUPPORTED_LOG_TYPES = (LOG_TYPE_NORMAL, LOG_TYPE_ERROR)


def _clean_log_type(value: object) -> str:

    if value == LOG_TYPE_ERROR:
        return LOG_TYPE_ERROR
    return LOG_TYPE_NORMAL

# 多行聚合默认最大跨行数
_MULTILINE_DEFAULT_MAX_LINES = 50


# ==================== 编译入口 ====================
def compile_regex(pattern: str, flags: int = 0) -> Optional[Pattern[str]]:
    """编译 Python 标准正则表达式

    Args:
        pattern: Python 正则字符串
        flags: re 编译标志

    Returns:
        编译后的 re.Pattern；为空或非法时返回 None
    """
    if not pattern:
        return None
    try:
        return re.compile(pattern, flags)
    except re.error:
        return None


# ==================== 匹配器数据类 ====================
@dataclass
class SplitMatcher:
    """字符串切割匹配器

    按子串匹配过滤行，再依次掐头、去尾提取中间内容。
    match 支持以「|」分隔多个关键字，任一命中即视为该行通过过滤。
    head_include/tail_include 为 True 时连同关键字一起去掉，为 False 时保留关键字。
    """

    match: str
    head: Optional[str]
    head_include: bool
    tail: Optional[str]
    tail_include: bool
    # 日志类型（普通/异常）：仅作为推送策略的元数据，不参与匹配逻辑
    log_type: str = LOG_TYPE_NORMAL

    def apply(self, line: str) -> Optional[str]:
        """对单行日志应用切割规则，命中返回提取文本，未命中返回 None"""
        if self.match:
            # 支持「|」分隔的多关键字任一命中（与旧版 PushLog 关键字语义一致）
            keywords = [kw for kw in self.match.split("|") if kw]
            if keywords and not any(kw in line for kw in keywords):
                return None
        result = line
        # 掐头：截掉头部关键字之前（含/不含关键字本身）的内容
        if self.head:
            idx = result.find(self.head)
            if idx >= 0:
                if self.head_include:
                    result = result[idx + len(self.head) :]
                else:
                    result = result[idx:]
        # 去尾：截掉尾部关键字之后（含/不含关键字本身）的内容
        if self.tail:
            idx = result.find(self.tail)
            if idx >= 0:
                if self.tail_include:
                    result = result[:idx]
                else:
                    result = result[: idx + len(self.tail)]
        return result.strip()

    def flush(self) -> Optional[str]:
        """单行模式无残留状态"""
        return None


@dataclass
class RegexMatcher:
    """正则匹配器：match 过滤行，extract 表达式提取内容

    match 为空表示不过滤（由编译入口保证非空）；extract 为空表示返回过滤后整行；
    extract 使用 $() 表达式语法，支持函数链和拼接。
    """

    match: Optional[Pattern[str]]
    extract: Optional[CompiledExpression]
    # 日志类型（普通/异常）：仅作为推送策略的元数据，不参与匹配逻辑
    log_type: str = LOG_TYPE_NORMAL

    def apply(self, line: str) -> Optional[str]:
        """对单行日志应用正则规则，命中返回提取文本，未命中返回 None"""
        if self.match is not None and self.match.search(line) is None:
            return None
        if self.extract is None:
            return line.strip()
        result = self.extract.extract(line)
        return result if result else None

    def flush(self) -> Optional[str]:
        """单行模式无残留状态"""
        return None


# ==================== 多行聚合匹配器 ====================
@dataclass
class MultiLineAggregator:
    """多行聚合匹配器

    由起始正则和结束正则划定多行窗口，窗口内所有行拼接后用提取表达式提取字段。
    起始正则为必填项（由 _compile_multiline_matcher 保证非空）；结束正则为空时
    窗口仅在遇到新起始行、达到最大跨行数或日志处理结束时关闭。同一时刻仅允许
    一个窗口处于打开状态；若窗口打开期间遇到新的起始行，则强制关闭当前窗口并
    处理，再以该起始行开启新窗口。日志处理结束时若有打开的窗口，也会强制关闭
    并处理。

    提取表达式使用 $() 语法（详见 app.utils.expression），支持函数链：

    - ``$(正则)`` 正则提取作用域
    - ``"文本"`` 字面量
    - ``+`` 同行拼接，``;`` 换行拼接
    - ``$(正则).函数(参数)`` 函数链处理

    提取表达式留空时返回窗口原文。
    """

    start_re: Optional[Pattern[str]]
    end_re: Optional[Pattern[str]]
    extract_expr: Optional[CompiledExpression] = None
    max_lines: int = _MULTILINE_DEFAULT_MAX_LINES
    # 日志类型（普通/异常）：仅作为推送策略的元数据，不参与匹配逻辑
    log_type: str = LOG_TYPE_NORMAL
    # 运行时状态（不参与序列化）
    _buffer: list[str] = field(default_factory=list, repr=False)
    _window_open: bool = field(default=False, repr=False)

    def apply(self, line: str) -> Optional[str]:
        """逐行喂入日志，窗口关闭时返回提取结果，否则返回 None"""
        is_start = self.start_re is not None and self.start_re.search(line) is not None
        is_end = self.end_re is not None and self.end_re.search(line) is not None

        if not self._window_open:
            # 仅匹配起始正则的行开启窗口（起始正则为必填项，由 _compile_multiline_matcher 保证非空）
            if is_start:
                self._buffer = [line]
                self._window_open = True
                # 起始行同时也是结束行 → 立即关闭
                if is_end:
                    return self._close_and_extract()
            return None

        # 窗口已打开
        # 遇到新的起始行：强制关闭当前窗口（不含本行），再以本行开启新窗口
        if is_start and not is_end:
            result = self._close_and_extract()
            self._buffer = [line]
            self._window_open = True
            return result

        # 正常收集行
        self._buffer.append(line)

        # 遇到结束行 → 关闭窗口
        if is_end:
            return self._close_and_extract()

        # 达到最大行数 → 强制关闭
        if len(self._buffer) >= self.max_lines:
            return self._close_and_extract()

        return None

    def flush(self) -> Optional[str]:
        """日志处理结束时调用，强制关闭并处理残留窗口"""
        if self._window_open:
            return self._close_and_extract()
        return None

    def reset(self) -> None:
        """重置运行时窗口状态。

        匹配器在会话初始化时编译一次并跨多次任务尝试复用；每次尝试开始时
        调用本方法清空残留窗口，避免上一次未闭合的窗口吞并新一次尝试的日志
        产生跨重试的错误聚合结果。
        """
        self._buffer = []
        self._window_open = False

    def _close_and_extract(self) -> Optional[str]:
        """关闭当前窗口，对缓冲内容应用提取表达式，返回提取结果

        提取表达式为空时返回窗口原文；否则使用 CompiledExpression.extract()
        对窗口内容执行提取 + 函数链处理 + 拼接。
        """
        if not self._buffer:
            self._window_open = False
            return None
        content = "\n".join(self._buffer)
        self._buffer = []
        self._window_open = False

        if self.extract_expr is None:
            return content.strip() if content.strip() else None

        result = self.extract_expr.extract(content)
        return result if result else None


CompiledMatcher = Union[SplitMatcher, RegexMatcher, MultiLineAggregator]


# ==================== 批量加载 ====================
def _compile_split(config: dict) -> Optional[SplitMatcher]:
    match = config.get("match") or ""
    head = config.get("head") or ""
    tail = config.get("tail") or ""
    # 匹配关键字留空则该规则不生效，避免误开启后匹配所有行造成海量推送
    if not match:
        return None
    return SplitMatcher(
        match=match,
        head=head or None,
        head_include=bool(config.get("headInclude", False)),
        tail=tail or None,
        tail_include=bool(config.get("tailInclude", False)),
        log_type=_clean_log_type(config.get("logType")),
    )


def _compile_regex_matcher(config: dict) -> Optional[RegexMatcher]:
    match_str = config.get("match") or ""
    extract_str = config.get("extract") or ""
    # 匹配正则留空则该规则不生效，避免误开启后匹配所有行造成海量推送
    if not match_str:
        return None
    match_re = compile_regex(match_str)
    # 提取表达式使用 $() 语法（支持函数链），为空时返回整行
    extract_expr = compile_expression(extract_str) if extract_str else None
    # 匹配正则编译失败则跳过该条，避免运行时静默失效
    if match_re is None:
        return None
    return RegexMatcher(
        match=match_re,
        extract=extract_expr,
        log_type=_clean_log_type(config.get("logType")),
    )


def _compile_multiline_matcher(config: dict) -> Optional[MultiLineAggregator]:
    start_str = config.get("start") or ""
    end_str = config.get("end") or ""
    extract_str = config.get("extract") or ""
    # 起始正则留空则该规则不生效，避免误开启后任意行均可开启窗口造成海量推送
    if not start_str:
        return None
    start_re = compile_regex(start_str)
    end_re = compile_regex(end_str) if end_str else None
    # 提取表达式使用 $() 语法（支持函数链），为空时返回窗口原文
    extract_expr = compile_expression(extract_str) if extract_str else None
    # 提供了正则但编译失败则跳过
    if start_re is None:
        return None
    if end_str and end_re is None:
        return None
    max_lines = config.get("maxLines", _MULTILINE_DEFAULT_MAX_LINES)
    try:
        max_lines = int(max_lines)
        if max_lines < 2:
            max_lines = 2
    except (TypeError, ValueError):
        max_lines = _MULTILINE_DEFAULT_MAX_LINES
    return MultiLineAggregator(
        start_re=start_re,
        end_re=end_re,
        extract_expr=extract_expr,
        max_lines=max_lines,
        log_type=_clean_log_type(config.get("logType")),
    )


def compile_pattern(config: dict) -> Optional[CompiledMatcher]:
    """按类型编译单条模式配置为匹配器

    Args:
        config: 形如 {"type":"split|regex|multiline", ...} 的配置字典

    Returns:
        编译后的匹配器；类型未知、字段不全或 enabled 为 false 时返回 None

    Note:
        enabled 字段用于单独停用某条规则而保留其配置，与匹配字段为空时的跳过语义
        一致：load_patterns 会静默跳过，validate_pattern/debug_pattern 不受影响
        以便用户在停用状态下仍可调试。
    """
    # 单条规则停用开关：显式为 false 时跳过编译，保留配置但不生效
    if config.get("enabled", True) is False:
        return None
    ptype = (config.get("type") or "").lower()
    if ptype == PATTERN_TYPE_SPLIT:
        return _compile_split(config)
    if ptype == PATTERN_TYPE_REGEX:
        return _compile_regex_matcher(config)
    if ptype == PATTERN_TYPE_MULTILINE:
        return _compile_multiline_matcher(config)
    return None


def load_patterns(patterns_json: str) -> list[CompiledMatcher]:
    """从 JSON 字符串加载并编译模式列表

    支持三种模式混合配置；解析或编译失败的条目会被静默跳过，
    保证其余规则仍可生效。

    Args:
        patterns_json: 模式列表的 JSON 字符串

    Returns:
        编译后的匹配器列表
    """
    if not patterns_json:
        return []
    try:
        items = json.loads(patterns_json)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(items, list):
        return []

    compiled: list[CompiledMatcher] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        # 单条规则解析/编译失败时静默跳过，保证其余规则仍可生效
        try:
            matcher = compile_pattern(item)
        except Exception:
            # 表达式语法错误、正则编译失败等不影响其它规则
            matcher = None
        if matcher is not None:
            compiled.append(matcher)
    return compiled


# ==================== 匹配 ====================
def apply_patterns(
    line: str, matchers: Optional[list[CompiledMatcher]] = None
) -> Optional[tuple[str, str]]:
    """对单行日志依次应用匹配器，返回首个命中规则的 (日志类型, 提取文本)

    Args:
        line: 单行日志原文
        matchers: 经 load_patterns / compile_pattern 编译后的匹配器列表

    Returns:
        首个命中规则的 (log_type, extracted) 元组；全部未命中返回 None

    Note:
        入口处统一 strip() 去除行尾空白字符（如 \\r \\n），与 debug_pattern 保持一致，
        避免正则 (.+) 等配合 re.DOTALL 捕获到行尾换行符导致推送内容多出空行。
    """
    if not matchers:
        return None
    line = line.strip()
    for matcher in matchers:
        result = matcher.apply(line)
        if result is not None:
            return (matcher.log_type, result)
    return None


def flush_patterns(
    matchers: Optional[list[CompiledMatcher]] = None
) -> list[tuple[str, str]]:
    """对所有匹配器调用 flush，收集所有非 None 的 (日志类型, 残留结果)

    用于日志处理结束时强制关闭多行聚合等有状态匹配器的残留窗口。

    需要一次性收集并返回所有 matcher 的残留结果：若配置了多条未设置结束
    正则的 multiline 规则，仅返回首个残留会导致后续 matcher 仍保持打开，
    任务结束时的推送结果丢失。调用端应逐条追加到推送缓冲。

    Args:
        matchers: 编译后的匹配器列表

    Returns:
        (log_type, flushed) 的列表；全部无残留返回空列表
    """
    if not matchers:
        return []
    flushed_all: list[tuple[str, str]] = []
    for matcher in matchers:
        result = matcher.flush()
        if result is not None:
            flushed_all.append((matcher.log_type, result))
    return flushed_all


# ==================== 调试 ====================
def validate_pattern(config: dict) -> Optional[str]:
    """校验单条模式配置，返回错误信息或 None（通过）

    与 compile_pattern 配合使用：compile_pattern 返回 None 时无法区分原因，
    本函数提供面向用户的详细错误信息（正则语法错误、表达式语法错误、未知函数等）。
    """
    ptype = (config.get("type") or "").lower()

    if ptype == PATTERN_TYPE_SPLIT:
        if not (config.get("match") or "").strip():
            return "匹配关键字为空，该规则不生效"
        return None

    if ptype == PATTERN_TYPE_REGEX:
        match_str = (config.get("match") or "").strip()
        extract_str = (config.get("extract") or "").strip()
        if not match_str:
            return "匹配正则为空，该规则不生效"
        if compile_regex(match_str) is None:
            return f"匹配正则语法错误: {match_str}"
        if extract_str:
            try:
                compile_expression(extract_str)
            except ExpressionError as e:
                return f"提取表达式语法错误: {e}"
        return None

    if ptype == PATTERN_TYPE_MULTILINE:
        start_str = (config.get("start") or "").strip()
        end_str = (config.get("end") or "").strip()
        extract_str = (config.get("extract") or "").strip()
        if not start_str:
            return "起始正则为空，该规则不生效"
        if compile_regex(start_str) is None:
            return f"起始正则语法错误: {start_str}"
        if end_str and compile_regex(end_str) is None:
            return f"结束正则语法错误: {end_str}"
        if extract_str:
            try:
                compile_expression(extract_str)
            except ExpressionError as e:
                return f"提取表达式语法错误: {e}"
        return None

    return f"未知模式类型: {ptype}"


def debug_pattern(
    config: dict, log_text: str
) -> tuple[Optional[str], bool, list[dict]]:
    """调试单条模式配置，返回逐行/逐窗口的匹配结果

    与 apply_patterns 不同，本函数返回所有行的结果（含未命中行），
    供前端调试弹窗展示每行的命中/未命中状态。

    Args:
        config: 形如 {"type":"split|regex|multiline", ...} 的配置字典
        log_text: 多行日志文本

    Returns:
        (error, is_multiline, results)
        - error: 配置级错误信息（正则/表达式语法错误等），None 表示通过
        - is_multiline: 是否为多行聚合模式
        - results: 每行/每窗口的结果列表，每项形如
          {"idx": int, "hit": bool, "extracted": str, "line": str}
          - split/regex 模式：idx 为行号，line 为该行原文
          - multiline 模式：idx 为窗口序号，line 为空串
    """
    # 配置级校验
    error = validate_pattern(config)
    ptype = (config.get("type") or "").lower()
    is_multiline = ptype == PATTERN_TYPE_MULTILINE
    if error:
        return (error, is_multiline, [])

    # 编译匹配器（validate_pattern 通过后 compile_pattern 不会返回 None；
    # 调试不应受 enabled 开关影响，停用的有效规则也应可调试）
    try:
        matcher = compile_pattern({**config, "enabled": True})
    except Exception as e:
        return (f"规则编译失败: {e}", is_multiline, [])
    if matcher is None:
        return ("规则配置无效", is_multiline, [])

    # 统一预处理：strip 每行，过滤空行（与 apply_patterns 入口 strip 行为一致，
    # 避免行尾 \r 等被正则 (.+) 配合 re.DOTALL 捕获导致调试与生产结果不一致）
    lines = [l.strip() for l in log_text.split("\n") if l.strip()]
    if not lines:
        return (None, is_multiline, [])

    if is_multiline:
        # 多行聚合：逐行喂入，窗口关闭时产出结果
        results: list[dict] = []
        window_idx = 0
        for line in lines:
            result = matcher.apply(line)
            if result is not None:
                results.append(
                    {"idx": window_idx, "hit": True, "extracted": result, "line": ""}
                )
                window_idx += 1
        flushed = matcher.flush()
        if flushed is not None:
            results.append(
                {"idx": window_idx, "hit": True, "extracted": flushed, "line": ""}
            )
        if not results:
            results.append(
                {"idx": 0, "hit": False, "extracted": "", "line": "", "error": "未匹配到任何窗口"}
            )
        return (None, is_multiline, results)

    # split/regex：逐行匹配
    results = []
    for i, line in enumerate(lines):
        result = matcher.apply(line)
        if result is not None:
            results.append({"idx": i, "hit": True, "extracted": result, "line": line})
        else:
            results.append({"idx": i, "hit": False, "extracted": "", "line": line})
    return (None, is_multiline, results)
