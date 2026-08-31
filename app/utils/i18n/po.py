"""gettext PO 文件解析

把 .po 文件解析为 msgid → msgstr 映射，供 PoTranslator 使用。

PO 条目格式（msgid/msgstr 均可跨行拼接，字符串支持 \\n \\t \\" \\\\ 转义）::

    msgid "English"
    msgstr "中文"

文件头（空 msgid）与空 msgstr（表示沿用 msgid，不翻译）会被跳过。
"""

from __future__ import annotations

from pathlib import Path


def _unescape(fragment: str) -> str:
    """解析 PO 字符串片段中的 C 风格转义（\\n \\t \\" \\\\ 等）"""
    out: list[str] = []
    i = 0
    n = len(fragment)
    while i < n:
        ch = fragment[i]
        if ch == "\\" and i + 1 < n:
            nxt = fragment[i + 1]
            if nxt == "n":
                out.append("\n")
            elif nxt == "t":
                out.append("\t")
            elif nxt == '"':
                out.append('"')
            elif nxt == "\\":
                out.append("\\")
            else:
                out.append(ch)
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _parse_string_literal(line: str) -> str:
    """从形如 `  "abc"` 的行中取出字符串字面量内容（含转义原文，未闭合时取整行）"""
    stripped = line.strip()
    if not stripped.startswith('"'):
        return ""
    # 手动扫描到匹配的结束引号，保留转义序列原文交给 _unescape 统一处理
    chars: list[str] = []
    i = 1
    n = len(stripped)
    while i < n:
        ch = stripped[i]
        if ch == "\\" and i + 1 < n:
            chars.append(ch)
            chars.append(stripped[i + 1])
            i += 2
            continue
        if ch == '"':
            break
        chars.append(ch)
        i += 1
    return "".join(chars)


def parse_po(path: Path) -> dict[str, str]:
    """解析 .po 文件，返回 msgid → msgstr 映射

    解析失败的条目静默跳过，保证单个异常条目不影响整体加载。
    """
    result: dict[str, str] = {}
    key: str = ""
    value: str = ""
    phase: str = "id"  # 当前收集阶段：id / str / plural
    is_plural: bool = False  # 当前条目是否为复数形式

    def flush() -> None:
        """登记当前完整条目并复位（仅在新 msgid 处与文件结尾调用）"""
        nonlocal key, value, phase, is_plural
        if key and value:
            result[key] = value
        key = ""
        value = ""
        phase = "id"
        is_plural = False

    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("msgctxt "):
                # 有上下文的条目：忽略上下文，按 msgid 收录
                flush()
                continue
            if line.startswith("msgid_plural"):
                # 复数形式：msgid 已收集，等待 msgstr[0]（仅取单数）
                is_plural = True
                phase = "plural"
                continue
            if line.startswith("msgstr["):
                if line.startswith("msgstr[0]"):
                    phase = "str"
                    value = _unescape(_parse_string_literal(line[len("msgstr[0]") :]))
                continue
            if line.startswith("msgid "):
                # 新条目：登记上一条完整条目
                flush()
                phase = "id"
                key = _unescape(_parse_string_literal(line[len("msgid") :]))
                continue
            if line.startswith("msgstr "):
                phase = "str"
                value = _unescape(_parse_string_literal(line[len("msgstr") :]))
                continue
            # 续行：追加到当前 msgid / msgstr
            fragment = _unescape(_parse_string_literal(line))
            if phase == "id":
                key += fragment
            elif phase in ("str", "plural"):
                value += fragment

    flush()
    return result
