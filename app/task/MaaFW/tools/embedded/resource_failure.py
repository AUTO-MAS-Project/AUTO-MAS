#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""资源包没能加载时给用户的一句话：原因从本次尝试的原生 ERR 行里找。

资源加载是普通 Job，MaaFramework 不回传失败详情，以前用户只看到「加载资源失败: <目录>，
详见本次运行的 .maafw.log」，每次重试都一样。真正的原因在 ``PipelineResMgr`` 的 ERR 行里，
例如节点重名（战双帕弥什旧版本残留的 ``auto_battle.jsonc``，2026-10-26）::

    [时间][ERR][Px..][Tx..][PipelineResMgr.cpp][L180][...::parse_and_override_once] key already exists [key=K]
    [时间][ERR][Px..][Tx..][PipelineResMgr.cpp][L125][...::open_and_parse_file] parse_config failed [path=P] [json={...}]
    [时间][ERR][Px..][Tx..][PipelineResMgr.cpp][L95][...::load_all_json] open_and_parse_file failed [entry_path=P]

- 依据优先取本次运行的 ``.maafw.log``（项目 ``debug/maafw.log`` 本次新写的部分，UTF-8）：worker
  stdout 里的同一行按控制台代码页转过，非 ASCII 的节点名 / 路径可能已经变成 ``?``（2026-10-26
  走查实测）。拿不到原生日志时才用 stdout 收到的行。
- ``[json=...]`` 是整份 pipeline 文件，可能很长、也可能跨多行（带缩进的文件原样打出）：只认以
  ``[日期 时间][ERR]`` 开头的行，``[json=`` 起整段丢掉，续行一律不看，绝不进用户消息。
- 认得出的情况（节点重名、JSON 写错、节点不是对象……）给一句人话；都认不出时退回清理过的
  第一条相关 ERR 行，这时才保留「详见本次运行的 .maafw.log」。
- 消息里的路径按项目根给相对路径，再过用户目录脱敏（``log_redact``）与密码打码
  （``option_secrets``）。

纯逻辑，宿主侧用（不进 worker 导入闭包）。
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from app.task.MaaFW.tools.core.log_redact import mask_home_path

from .option_secrets import redact_secret_text

# 一次尝试最多留这么多条 ERR 行、每条最多这么多字符（``[json=`` 之前的部分通常不到 300）。
MAX_NATIVE_ERROR_LINES = 400
MAX_NATIVE_ERROR_CHARS = 2000
# 原生日志副本按行扫，最多读这么多字节（只取 ERR 行，副本本身已按本次运行截过）。
MAX_NATIVE_LOG_SCAN_BYTES = 64 * 1024 * 1024
# 找「同一资源包里另一个定义 K 的文件」：只在 pipeline 目录里按文本找，有上限。
OTHER_DEFINITION_MAX_FILES = 5000
OTHER_DEFINITION_MAX_BYTES = 64 * 1024 * 1024
OTHER_DEFINITION_MAX_SECONDS = 3.0
# 退回原始 ERR 行时，那一行最多给用户看这么多字符。
FALLBACK_DETAIL_MAX_CHARS = 160
NATIVE_LOG_HINT = "详见本次运行的 .maafw.log"

_ERR_HEADER_RE = re.compile(r"\[\d{4}-\d{2}-\d{2}[ T][^\]]*\]\[ERR\]")
# ``[ERR]`` 之后的固定几段：[Px..][Tx..][文件][L行号][函数]
_ERR_FIELDS_RE = re.compile(
    r"^\[ERR\](?:\[Px\d+\])?(?:\[Tx\d+\])?\[(?P<file>[^\]]*)\]\[L\d+\]"
    r"\[(?P<func>[^\]]*)\]\s*(?P<message>.*)$"
)
# 整份文件 / 节点内容的字段：从这里起到行尾一律丢掉。
_BULKY_FIELD_RE = re.compile(r"\s*\[(?:json|value|input)=", re.IGNORECASE)
_PIPELINE_SUFFIXES = (".json", ".jsonc")


@dataclass(frozen=True)
class NativeError:
    """一条原生 ERR 行（``[json=`` 起已丢）。``fields`` 是 ``[name=value]`` 形式的变量。"""

    source: str
    function: str
    message: str
    text: str
    fields: dict[str, str] = field(default_factory=dict)


def native_error_excerpt(line: str) -> str | None:
    """这一行是原生 ERR 行就返回去掉 ``[json=...]`` 等大字段、截过长度的那段（从
    ``[日期][ERR]`` 起），否则 None（普通日志、``[json=`` 的续行）。"""

    match = _ERR_HEADER_RE.search(str(line or ""))
    if match is None:
        return None
    text = line[match.start() :]
    bulky = _BULKY_FIELD_RE.search(text)
    if bulky is not None:
        text = text[: bulky.start()]
    return text.rstrip()[:MAX_NATIVE_ERROR_CHARS]


def read_native_error_lines(path: Path) -> list[str]:
    """从本次运行的原生日志副本里按行取 ERR 行（续行不要），读不了返回空表。"""

    lines: list[str] = []
    try:
        with Path(path).open("rb") as handle:
            read = 0
            for raw in handle:
                read += len(raw)
                if read > MAX_NATIVE_LOG_SCAN_BYTES:
                    break
                if b"][ERR][" not in raw:
                    continue
                excerpt = native_error_excerpt(
                    raw.decode("utf-8", errors="replace").rstrip("\r\n")
                )
                if excerpt is not None:
                    lines.append(excerpt)
                    del lines[:-MAX_NATIVE_ERROR_LINES]
    except OSError:
        return []
    return lines


def _parse_fields(message: str) -> dict[str, str]:
    """``key already exists [key=K]`` → ``{"key": "K"}``。值里允许出现 ``]``，以「``]`` 后面紧跟
    空白 + ``[`` 或行尾」为界（节点名里带方括号的项目不少）。"""

    fields: dict[str, str] = {}
    for match in re.finditer(
        r"\[(?P<name>[A-Za-z_]+)=(?P<value>.*?)\](?=\s*\[|\s*$)", message
    ):
        fields.setdefault(match["name"], match["value"])
    return fields


def parse_native_error(line: str) -> NativeError | None:
    excerpt = native_error_excerpt(line)
    if excerpt is None:
        return None
    header = _ERR_HEADER_RE.match(excerpt)
    rest = excerpt[header.end() - len("[ERR]") :] if header else excerpt
    match = _ERR_FIELDS_RE.match(rest)
    if match is None:
        return NativeError(source="", function="", message=rest, text=excerpt)
    message = match["message"].strip()
    return NativeError(
        source=match["file"],
        function=match["func"],
        message=message,
        text=excerpt,
        fields=_parse_fields(message),
    )


def _norm(path: str) -> str:
    return str(path or "").replace("\\", "/").rstrip("/")


def _relative(path: str, root: Path) -> str:
    """原生日志里的绝对路径（正斜杠）→ 项目根相对路径；不在项目根下的原样（脱敏后）给。"""

    text = _norm(path)
    base = _norm(str(root))
    if base and text.casefold().startswith(f"{base.casefold()}/"):
        return text[len(base) + 1 :]
    return text


def _within(path: str, directory: str) -> bool:
    text, base = _norm(path).casefold(), _norm(directory).casefold()
    return bool(base) and (text == base or text.startswith(f"{base}/"))


# 认得出的根因：消息开头 → 给用户的说法（{key} / {file} 由调用方填）。
_ROOT_CAUSES = (
    "key already exists",
    "json::open failed",
    "json is not object",
    "value is not object",
    "parse_task failed",
    "key is empty",
)
# 跟在根因后面、带出文件路径的那几行。
_PATH_CARRIERS = (
    ("parse_config failed", "path"),
    ("open_and_parse_file failed", "entry_path"),
)


def _file_of(errors: Sequence[NativeError], index: int) -> str:
    """根因那一行自己带的路径，或紧跟着的 parse_config / open_and_parse_file 行带的。"""

    own = errors[index].fields.get("path", "")
    if own:
        return own
    for later in errors[index + 1 : index + 4]:
        for prefix, name in _PATH_CARRIERS:
            if later.message.startswith(prefix) and later.fields.get(name):
                return later.fields[name]
    return ""


def _find_other_definition(
    bundle: str, key: str, exclude: str, project_root: Path
) -> str:
    """同一资源包的 pipeline 目录里另一个定义了节点 ``key`` 的文件（项目根相对路径），找不到
    返回空串。按文本找 ``"key":``，有文件数、字节数与时间上限；MaaFramework 跳过的
    ``.`` 开头路径段也跳过。"""

    pipeline = Path(bundle) / "pipeline"
    if not key or not pipeline.is_dir():
        return ""
    pattern = re.compile(r'"' + re.escape(key) + r'"\s*:')
    started = time.monotonic()
    files = read = 0
    excluded = _norm(exclude).casefold()
    for current, dir_names, file_names in os.walk(pipeline):
        dir_names[:] = sorted(name for name in dir_names if not name.startswith("."))
        for name in sorted(file_names):
            if name.startswith(".") or not name.casefold().endswith(_PIPELINE_SUFFIXES):
                continue
            path = Path(current) / name
            if _norm(str(path)).casefold() == excluded:
                continue
            files += 1
            if (
                files > OTHER_DEFINITION_MAX_FILES
                or read > OTHER_DEFINITION_MAX_BYTES
                or time.monotonic() - started > OTHER_DEFINITION_MAX_SECONDS
            ):
                return ""
            try:
                data = path.read_bytes()
            except OSError:
                continue
            read += len(data)
            if pattern.search(data.decode("utf-8-sig", errors="replace")):
                return _relative(str(path), project_root)
    return ""


def _clean(text: str, secrets: Iterable[str]) -> str:
    return mask_home_path(redact_secret_text(text, list(secrets)))


def describe_resource_failure(
    kind: str,
    bundle_path: str,
    errors: Sequence[str],
    *,
    project_root: Path,
    secrets: Iterable[str] = (),
) -> str:
    """给用户的失败消息（含「MaaFW 运行失败：」前缀，与其它运行失败同一开头）。

    ``kind`` / ``bundle_path`` 来自结果的 ``resourceFailure``；``errors`` 是本次尝试的原生 ERR
    行（:func:`native_error_excerpt` 处理过的，或原样的行，这里会再处理一遍）。
    """

    secrets = list(secrets)
    bundle_rel = _relative(bundle_path, project_root) or str(bundle_path)
    if kind == "missing":
        return _clean(
            f"MaaFW 运行失败：资源目录不存在：{bundle_rel}（项目副本里没有这个资源包）",
            secrets,
        )
    parsed = [error for line in errors if (error := parse_native_error(line))]
    lead = f"MaaFW 运行失败：资源包 {bundle_rel} 加载失败："
    roots = [
        (index, _file_of(parsed, index))
        for index, error in enumerate(parsed)
        if error.message.startswith(_ROOT_CAUSES)
    ]
    # 同一次运行里别的资源包也可能报过错：取落在这个资源包里的最后一个根因，没有再取最后一个。
    inside = [root for root in roots if _within(root[1], bundle_path)]
    chosen = (inside or roots or [None])[-1]
    if chosen is not None:
        error = parsed[chosen[0]]
        file_rel = _relative(chosen[1], project_root) if chosen[1] else ""
        key = error.fields.get("key", "")
        message = error.message
        if message.startswith("key already exists"):
            other = (
                _find_other_definition(bundle_path, key, chosen[1], project_root)
                if chosen[1]
                else ""
            )
            files = "、".join(item for item in (file_rel, other) if item)
            reason = (
                f"节点「{key}」重复定义（{files}），同一资源包里的节点不能重名"
                if other
                else f"节点「{key}」在 {file_rel or '某个 pipeline 文件'} 里重复定义"
                "（同一资源包里别的文件已经定义过它），同一资源包里的节点不能重名"
            )
            reason += "；多半是项目目录里留着旧版本的文件"
        elif message.startswith("json::open failed"):
            reason = (
                f"{file_rel or 'pipeline 文件'} 不是有效的 JSON（格式写错了或读不了）"
            )
        elif message.startswith("json is not object"):
            reason = f"{file_rel or 'pipeline 文件'} 的内容不是 JSON 对象"
        elif message.startswith("value is not object"):
            reason = (
                f"{file_rel or 'pipeline 文件'} 里节点「{key}」的内容不是 JSON 对象"
            )
        elif message.startswith("parse_task failed"):
            reason = (
                f"{file_rel or 'pipeline 文件'} 里节点「{key}」的字段写法有误，"
                "MaaFramework 解析不了"
            )
        else:
            reason = f"{file_rel or 'pipeline 文件'} 里有名字为空的节点"
        return _clean(lead + reason, secrets)

    # 认不出：取第一条相关的 ERR 行（资源管理那几个模块的优先），去掉前缀与大字段。
    relevant = [
        error
        for error in parsed
        if "Res" in error.source
        or "ResourceNS" in error.function
        or _within(error.fields.get("path", ""), bundle_path)
    ] or parsed
    if not relevant:
        return _clean(f"{lead[:-1]}，{NATIVE_LOG_HINT}", secrets)
    detail = relevant[0].message
    for name, value in relevant[0].fields.items():
        if name.endswith("path"):
            detail = detail.replace(value, _relative(value, project_root))
    detail = " ".join(detail.split())
    if len(detail) > FALLBACK_DETAIL_MAX_CHARS:
        detail = detail[: FALLBACK_DETAIL_MAX_CHARS - 1] + "…"
    return _clean(f"{lead}{detail}，{NATIVE_LOG_HINT}", secrets)


__all__ = [
    "MAX_NATIVE_ERROR_LINES",
    "NATIVE_LOG_HINT",
    "NativeError",
    "describe_resource_failure",
    "native_error_excerpt",
    "parse_native_error",
    "read_native_error_lines",
]
