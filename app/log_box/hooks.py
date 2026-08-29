"""日志处理 Hook 层：日志进入采集与判定之前的预处理/丢弃

钩子是日志采集管线的统一入口层，按配置的规则顺序逐行作用于日志：

- ``drop``：匹配正则命中即丢弃该行，用于过滤上游脚本的噪声行（心跳、进度刷屏）；
- ``replace``：按匹配正则改写该行后继续交给后续规则，用于脱敏与格式归一化。

挂接点由宿主决定，两种宿主共用同一份编译结果（均为
``Callable[[str], Optional[str]]``）：MAS 进程宿主把 ``make_line_hook()`` 的返回值
传给 ``LogMonitor(line_hook=...)``；log_box 采集会话可直接把它作为
``LogCollect.open(processor)`` 的前置处理器。专项只喂规则参数，不在各专项内
重复实现过滤逻辑。

执行顺序（与成功/失败判定的关系）::

    日志行 → 钩子（丢弃/改写）→ 任务日志 + 推送日志采集 + 成功/失败标志判定

即钩子先于一切下游环节，丢弃的行不进入任务日志、推送报告与标志判定；改写后的
文本才是标志判定的依据（便于先归一化再匹配）。唯一的例外是日志时间戳活跃度
跟踪（``LogMonitor.update_latest_timestamp``）仍读原始行，保证过滤噪声行不会让
运行中的脚本被误判为超时。

被丢弃的行同样不会用于成功/失败标志匹配，配置丢弃规则时不要丢掉标志所在的行。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable, Optional, Pattern

from app.utils.LogPatternExtractor import compile_regex

# 钩子类型：drop = 丢弃命中行；replace = 按正则改写命中内容
HOOK_TYPE_DROP = "drop"
HOOK_TYPE_REPLACE = "replace"
SUPPORTED_HOOK_TYPES = (HOOK_TYPE_DROP, HOOK_TYPE_REPLACE)

# 行钩子：逐行 map（返回新文本）/ filter（返回 None 丢弃该行）
LineHook = Callable[[str], Optional[str]]


@dataclass
class LogHook:
    """单条日志钩子规则

    match 为 Python 正则；drop 规则命中即丢弃，replace 规则用 replace 文本做
    ``re.sub`` 改写（支持 ``\\1`` 反向引用）。日志行保留原有行尾换行符，规则
    按行首/行尾锚点书写时按 Python 正则语义生效。
    """

    type: str
    match: Pattern[str]
    replace: str = ""

    def apply(self, line: str) -> Optional[str]:
        """对单行日志应用本条规则

        Args:
            line: 单行日志原文（含行尾换行符）

        Returns:
            处理后的行；drop 规则命中时返回 None 表示丢弃该行
        """
        if self.type == HOOK_TYPE_DROP:
            return None if self.match.search(line) is not None else line
        return self.match.sub(self.replace, line)


def compile_hook(config: dict) -> Optional[LogHook]:
    """按类型编译单条钩子配置

    Args:
        config: 形如 ``{"type":"drop|replace","match":...,"replace":...}`` 的配置字典

    Returns:
        编译后的钩子；类型未知、匹配正则为空/非法、替换文本引用了不存在的
        捕获组，或 enabled 为 false 时返回 None
    """
    # 单条规则停用开关：显式为 false 时跳过编译，保留配置但不生效
    if config.get("enabled", True) is False:
        return None
    hook_type = (config.get("type") or "").lower()
    if hook_type not in SUPPORTED_HOOK_TYPES:
        return None
    # 匹配正则留空则该规则不生效，避免误开启后匹配所有行造成全量丢弃
    match_re = compile_regex((config.get("match") or "").strip())
    if match_re is None:
        return None
    if hook_type == HOOK_TYPE_DROP:
        return LogHook(type=HOOK_TYPE_DROP, match=match_re)
    replace = config.get("replace") or ""
    try:
        # 提前暴露「引用不存在的捕获组」等替换模板错误，避免逐行改写时抛异常
        match_re.sub(replace, "")
    except re.error:
        return None
    return LogHook(type=HOOK_TYPE_REPLACE, match=match_re, replace=replace)


def load_hooks(hooks_json: str) -> list[LogHook]:
    """从 JSON 字符串加载并编译钩子规则列表

    解析或编译失败的条目会被静默跳过，保证其余规则仍可生效。

    Args:
        hooks_json: 钩子规则列表的 JSON 字符串

    Returns:
        编译后的钩子列表
    """
    if not hooks_json:
        return []
    try:
        items = json.loads(hooks_json)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(items, list):
        return []

    compiled: list[LogHook] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        hook = compile_hook(item)
        if hook is not None:
            compiled.append(hook)
    return compiled


def apply_hooks(line: str, hooks: list[LogHook]) -> Optional[str]:
    """按顺序对单行日志应用钩子规则

    drop 规则命中即结束并丢弃该行；replace 规则改写后继续交给后续规则，
    因此多条 replace 规则可以叠加（如先归一化格式再脱敏）。

    Args:
        line: 单行日志原文
        hooks: 编译后的钩子列表

    Returns:
        处理后的行；被丢弃时返回 None
    """
    for hook in hooks:
        result = hook.apply(line)
        if result is None:
            return None
        line = result
    return line


def make_line_hook(hooks_json: str) -> Optional[LineHook]:
    """把钩子规则配置编译为行钩子函数

    Args:
        hooks_json: 钩子规则列表的 JSON 字符串

    Returns:
        逐行处理函数；无可用规则时返回 None，调用方据此保持与未启用钩子
        完全一致的行为
    """
    hooks = load_hooks(hooks_json)
    if not hooks:
        return None
    return lambda line: apply_hooks(line, hooks)


def validate_hook(config: dict) -> Optional[str]:
    """校验单条钩子配置，返回面向用户的错误信息或 None（通过）

    与 compile_hook 配合使用：compile_hook 返回 None 时无法区分原因，
    本函数给出可展示的具体错误。
    """
    hook_type = (config.get("type") or "").lower()
    if hook_type not in SUPPORTED_HOOK_TYPES:
        return f"未知钩子类型: {hook_type}"

    match_str = (config.get("match") or "").strip()
    if not match_str:
        return "匹配正则为空，该规则不生效"
    match_re = compile_regex(match_str)
    if match_re is None:
        return f"匹配正则语法错误: {match_str}"

    if hook_type == HOOK_TYPE_REPLACE:
        try:
            match_re.sub(config.get("replace") or "", "")
        except re.error as e:
            return f"替换文本语法错误: {e}"
    return None
