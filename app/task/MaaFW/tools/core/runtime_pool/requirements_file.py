"""按 pip 的规则读项目的 ``requirements.txt``，得到能逐个交给 ``pip install`` / ``uv pip
install`` 的 requirement 列表（只用标准库）。

agent 隔离 venv 是把清单逐条当成独立参数交给安装器的（中间还要把 maafw 钉成原生库的版本），
没有 ``-r`` 那一层解析。原样逐行照抄时，pip ``-r`` 本来认得的几种写法都会变成
``Invalid requirement`` 或选项解析错，这份 venv 每次都装不上：

- 带 BOM 的 UTF-8（记事本另存的）：首行变成 ``\\ufeffnumpy``，首行是注释时也躲不过 ``#`` 过滤；
  不是 UTF-8 的（中文系统上另存成 ANSI）按系统编码再读一次，还读不出就报清楚是哪个文件；
- 行内注释（pip-compile 的 ``numpy==1.24.3  # via ...``）；
- 续行（``\\`` 结尾，pip-compile ``--generate-hashes`` 的 ``--hash`` 就是这样续的）与每条
  requirement 后面的选项（``--hash=...``）；
- 整行选项（``-i`` / ``--index-url`` / ``--extra-index-url`` / ``-r`` / ``-c`` / ``-e`` ……）：
  这些交给安装器当 requirement 只会报错；索引由运行池的候选轮换决定，所以忽略并交给调用方记日志。
  ``-r`` 引用的另一份清单目前不展开（日志里记得到选项名）。

规则照抄 pip 的 ``req_file``：先接续行，再去注释（行首或空白之后的 ``#`` 到行尾），再按空格
把 requirement 与它后面的选项分开（第一个以 ``-`` 开头的词起都算选项）。
"""

from __future__ import annotations

import locale
import re
from dataclasses import dataclass, field
from pathlib import Path

_COMMENT_RE = re.compile(r"(^|\s+)#.*$")


class RequirementsFileError(RuntimeError):
    """清单读不出来（编码认不出）。文案面向用户，带文件路径。"""


@dataclass(frozen=True)
class RequirementsFile:
    """``requirements``：按出现顺序的 requirement；``ignored_options``：被忽略的整行选项
    的选项名（只记名字不记取值——``-i`` 后面的地址可能带 ``user:pw@``）。"""

    requirements: list[str] = field(default_factory=list)
    ignored_options: list[str] = field(default_factory=list)


def _join_lines(lines: list[str]) -> list[str]:
    joined: list[str] = []
    pending: list[str] = []
    for line in lines:
        if not line.endswith("\\") or _COMMENT_RE.match(line):
            if _COMMENT_RE.match(line):
                # 注释行不参与续行；前面补空格，保证后面去注释时一定匹配
                line = " " + line
            if pending:
                pending.append(line)
                joined.append("".join(pending))
                pending = []
            else:
                joined.append(line)
        else:
            pending.append(line.strip("\\"))
    if pending:
        joined.append("".join(pending))
    return joined


def _break_args_options(line: str) -> tuple[str, str]:
    tokens = line.split(" ")
    args: list[str] = []
    for index, token in enumerate(tokens):
        if token.startswith("-"):
            return " ".join(args), " ".join(tokens[index:])
        args.append(token)
    return " ".join(args), ""


def parse_requirements_text(text: str) -> RequirementsFile:
    result = RequirementsFile()
    if text.startswith("﻿"):
        text = text[1:]
    for raw_line in _join_lines(text.splitlines()):
        line = _COMMENT_RE.sub("", raw_line).strip()
        if not line:
            continue
        requirement, options = _break_args_options(line)
        requirement = requirement.strip()
        if requirement:
            result.requirements.append(requirement)
            continue
        option_name = options.split(None, 1)[0].split("=", 1)[0] if options else ""
        if option_name:
            result.ignored_options.append(option_name)
    return result


def _decode(data: bytes, path: Path) -> str:
    """先按 UTF-8（带不带 BOM 都行）；不是 UTF-8 再按系统编码；都不行报带路径的错。"""

    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    fallback = locale.getpreferredencoding(False) or "utf-8"
    try:
        return data.decode(fallback)
    except (UnicodeDecodeError, LookupError) as exc:
        raise RequirementsFileError(
            f"项目 requirements.txt 的编码无法识别（不是 UTF-8，也不是系统编码 "
            f"{fallback}），请转成 UTF-8: {path}"
        ) from exc


def read_requirements_file(path: str | Path) -> RequirementsFile | None:
    """文件不在返回 None（与「在但是空的」区分开：调用方对两者的处理不同）。"""

    file = Path(path)
    try:
        data = file.read_bytes()
    except FileNotFoundError:
        return None
    return parse_requirements_text(_decode(data, file))


__all__ = [
    "RequirementsFile",
    "RequirementsFileError",
    "parse_requirements_text",
    "read_requirements_file",
]
