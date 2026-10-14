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
- ``-r`` / ``--requirement`` 引用的另一份清单：照 pip 的规则递归读入（路径相对引用它的那份
  清单所在目录，子清单同一套解析）。只读项目目录以内的本地文件；越出项目目录、网络地址、文件
  不在都报错（``RequirementsFileError``）——静默跳过的话依赖少装了，准备照样报「已就绪」，
  agent 起来才导入失败。同一份文件只读一次（循环引用、菱形引用都不重复）。
- ``-c`` / ``--constraint`` 与 ``-e`` / ``--editable``：逐条交给安装器的做法表达不了它们（约束
  不是要装的包，可编辑安装要带路径参数），目前不支持，报错而不是忽略——忽略了照样会报「已就绪」。
- 其余整行选项（``-i`` / ``--index-url`` / ``--extra-index-url`` / ``-f`` ……）：交给安装器当
  requirement 只会报错；索引由运行池的候选轮换决定，所以忽略并交给调用方记日志。

规则照抄 pip 的 ``req_file``：先接续行，再去注释（行首或空白之后的 ``#`` 到行尾），再按空格
把 requirement 与它后面的选项分开（第一个以 ``-`` 开头的词起都算选项）。
"""

from __future__ import annotations

import locale
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

_COMMENT_RE = re.compile(r"(^|\s+)#.*$")
_URL_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")
#: 逐条交给安装器表达不了、目前不支持的依赖指令：遇到就报错，不能忽略后照样报「已就绪」。
_UNSUPPORTED_DEPENDENCY_OPTIONS = frozenset({"-c", "--constraint", "-e", "--editable"})


class RequirementsFileError(RuntimeError):
    """清单读不出来（编码认不出）、引用的子清单读不了、或用了不支持的依赖指令。
    文案面向用户，带文件路径。"""


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


def _include_target(options: str) -> str | None:
    """``-r x`` / ``-rx`` / ``--requirement x`` / ``--requirement=x`` → ``x``；不是引用返回 None。"""

    tokens = options.split()
    if not tokens:
        return None
    first = tokens[0]
    if first in ("-r", "--requirement"):
        return tokens[1] if len(tokens) > 1 else ""
    if first.startswith("--requirement="):
        return first.split("=", 1)[1]
    if first.startswith("-r") and not first.startswith("--"):
        return first[2:]
    return None


def _option_name(options: str) -> str:
    token = options.split(None, 1)[0] if options else ""
    if token.startswith("--"):
        return token.split("=", 1)[0]
    # 短选项可能把值粘在后面（``-cconstraints.txt``），只取前两个字符
    return token[:2]


def _parse_lines(text: str, where: str):
    """逐条给出 ``("req", requirement)`` / ``("include", 目标)`` / ``("option", 选项名)``；
    遇到不支持的依赖指令直接报错（``where`` 是报错里写的清单名）。"""

    if text.startswith("﻿"):
        text = text[1:]
    for raw_line in _join_lines(text.splitlines()):
        line = _COMMENT_RE.sub("", raw_line).strip()
        if not line:
            continue
        requirement, options = _break_args_options(line)
        requirement = requirement.strip()
        if requirement:
            yield "req", requirement
            continue
        target = _include_target(options)
        if target is not None:
            yield "include", target
            continue
        name = _option_name(options)
        if name in _UNSUPPORTED_DEPENDENCY_OPTIONS:
            raise RequirementsFileError(
                f"{where} 里的 {name} 目前不支持（AUTO-MAS 逐条安装依赖，表达不了约束文件与"
                "可编辑安装），请把它改写成普通的依赖行"
            )
        if name:
            yield "option", name


def parse_requirements_text(text: str) -> RequirementsFile:
    """只解析一段文本：``-r`` 引用无处可解析，报错（读文件请用 :func:`read_requirements_file`）。"""

    result = RequirementsFile()
    for kind, value in _parse_lines(text, "requirements 清单"):
        if kind == "req":
            result.requirements.append(value)
        elif kind == "include":
            raise RequirementsFileError(
                f"requirements 清单引用了 {value}，只解析文本时无法展开"
            )
        else:
            result.ignored_options.append(value)
    return result


def scan_top_level_requirements(path: Path) -> list[str]:
    """只读这一份清单顶层的依赖行，跳过所有选项与 ``-r`` / ``-c`` / ``-e`` 指令，不展开、不报指令错。

    给只需从清单里认出某个包声明（如 maafw 版本）的调用方兜底：:func:`read_requirements_file`
    因为不支持的指令或读不了的 ``-r`` 报错时，顶层写着的声明仍认得出来。真要安装请用
    :func:`read_requirements_file`。文件读不到或解码失败返回空列表。
    """

    try:
        text = _decode(path.read_bytes(), path)
    except (OSError, RequirementsFileError):
        return []
    if text.startswith("﻿"):
        text = text[1:]
    found: list[str] = []
    for raw_line in _join_lines(text.splitlines()):
        line = _COMMENT_RE.sub("", raw_line).strip()
        if not line:
            continue
        requirement, _options = _break_args_options(line)
        requirement = requirement.strip()
        if requirement:
            found.append(requirement)
    return found


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
            f"项目 {path.name} 的编码无法识别（不是 UTF-8，也不是系统编码 "
            f"{fallback}），请转成 UTF-8: {path}"
        ) from exc


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def read_requirements_file(
    path: str | Path, *, root: str | Path | None = None
) -> RequirementsFile | None:
    """读清单并展开 ``-r`` 引用。顶层文件不在返回 None（与「在但是空的」区分开：调用方对
    两者的处理不同）；引用的子清单读不了、越界或用了不支持的指令都抛 ``RequirementsFileError``。

    ``root`` 是引用不许越出的目录，缺省为顶层清单所在目录（项目根）。
    """

    top = Path(path)
    try:
        data = top.read_bytes()
    except FileNotFoundError:
        return None
    root_dir = Path(root if root is not None else top.parent).resolve()
    result = RequirementsFile()
    seen: set[str] = set()

    def where(file: Path) -> str:
        try:
            return file.relative_to(root_dir).as_posix()
        except ValueError:
            return file.name

    def visit(file: Path, content: bytes) -> None:
        seen.add(os.path.normcase(str(file)))
        for kind, value in _parse_lines(_decode(content, file), where(file)):
            if kind == "req":
                result.requirements.append(value)
                continue
            if kind == "option":
                result.ignored_options.append(value)
                continue
            if not value or _URL_SCHEME_RE.match(value):
                # 网络地址可能带凭据，报错里不写原文
                shown = "网络地址" if value else "（缺少文件名）"
                raise RequirementsFileError(
                    f"{where(file)} 里的 -r {shown} 读不了：只支持项目目录内的本地清单"
                )
            target = Path(value)
            if not target.is_absolute():
                target = file.parent / target
            target = target.resolve()
            if not _is_within(target, root_dir):
                raise RequirementsFileError(
                    f"{where(file)} 里的 -r {value} 在项目目录之外，不读"
                )
            if os.path.normcase(str(target)) in seen:
                continue  # 循环 / 重复引用：同一份文件只读一次
            try:
                nested = target.read_bytes()
            except OSError as exc:
                raise RequirementsFileError(
                    f"{where(file)} 里的 -r {value} 读不了：{exc.strerror or exc}"
                ) from exc
            visit(target, nested)

    visit(top.resolve(), data)
    return result


__all__ = [
    "RequirementsFile",
    "RequirementsFileError",
    "parse_requirements_text",
    "read_requirements_file",
]
