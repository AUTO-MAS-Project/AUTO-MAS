"""运行这一块的按值打码：把密码原文在日志里可能出现的写法换成占位。

密码字段这件事分三处（迁移方案 §3.7）：哪些选项是密码、从快照里收集值归解析
（``blocks/maafw_interface/interface/password_values``）；加解密（DPAPI）在宿主（``option_secrets``）；
按值打码归运行（本模块）。``plan_run`` 复制原生日志、转发 worker 输出，``pretask_run`` 的输出，
``project_logs`` 的项目日志，``resource_failure`` 摘录失败原因都用这里的函数；要打码的值由调用方
（账号流程）经下面的 ``run_secret_values`` / ``project_log_secret_variants`` 算好、经 ``secret_log_variants``
换成写法后传进来。本模块不读配置、
不碰加解密。

两组要打码的值也在这里凑齐（``run_secret_values`` / ``project_log_secret_variants``）：调用方从配置里取出
快照原值（``option_secrets.user_task_snapshot`` / ``script_task_snapshots``）、带上 DPAPI 的 opener 交进来，
这里交给解析一侧的收集函数。每个要打码的调用点（运行前设置、跑计划、资源包失败的摘录）都现算一次，
不缓存：重试时计划会变。
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from app.task.MaaFW.blocks.maafw_interface.interface.models import (
    MaaFWInterface,
    password_input_names,
)
from app.task.MaaFW.blocks.maafw_interface.interface.password_values import (
    MaaFWSecretOpener,
    collect_run_password_values,
    collect_snapshots_password_values,
)
from app.utils import get_logger

if TYPE_CHECKING:  # pragma: no cover - 只给类型检查用
    from app.task.MaaFW.blocks.maafw_interface.runner.models import MaaFWRunPlan

# 与任务类同名：搬过来的那一行 debug 日志在 app.log 里仍按原来的名字检索
logger = get_logger("MaaFW 插件自动代理")

#: 日志里替换密码原文用的占位。
REDACTED_SECRET_TEXT = "<已隐藏>"
#: 短于这个长度的密码不做全文替换：一两个字符的值会把日志里所有同样的字符都换掉，
#: 日志就没法看了；这么短的密码本身也谈不上保密。
MIN_REDACTED_SECRET_LENGTH = 4
#: 项目有 password 输入框、或本次有要打码的值（账号快照里留着项目已撤掉标记的密文）时，每次运行的
#: ``.worker.log`` 第一行以它开头（``log_redaction_notice``）。
#: 问题包导出（frontend/electron/services/maafwIssueReportService.ts）凭这一行认定这次的
#: ``.worker.log`` / ``.maafw.log`` 是写的时候就打过码的，没有这一行的旧副本不往包里放。两边一起改。
LOG_REDACTION_MARKER = "[MAS 日志打码]"


def secret_log_variants(values: list[str]) -> list[str]:
    """一个密码在日志里可能出现的写法：原文，以及 JSON 转义后的两种（中文原样 / \\u 转义）。

    MaaFramework 原生日志把 ``pipeline_override`` 按 JSON 记下来（``MaaTaskerPostTask``
    的 ``[pipeline_override={...}]``），带引号、反斜杠或中文的密码在那里是转义后的样子。
    过短的值不收（见 ``MIN_REDACTED_SECRET_LENGTH``）；长的在前，免得先替换掉子串。
    """

    variants: set[str] = set()
    for value in values:
        if len(value) < MIN_REDACTED_SECRET_LENGTH:
            continue
        variants.add(value)
        variants.add(json.dumps(value, ensure_ascii=False)[1:-1])
        variants.add(json.dumps(value, ensure_ascii=True)[1:-1])
    return sorted(variants, key=len, reverse=True)


#: 按字节打码时每个写法再试的编码：项目日志不一定是 UTF-8（GBK 控制台输出重定向进文件、
#: Windows 下 UTF-16LE 的日志），``.maafw.log`` 与 ``.project.log`` 共用。
_SECRET_BYTE_ENCODINGS = ("utf-8", "gbk", "utf-16-le")


def secret_byte_pairs(variants: list[str]) -> list[tuple[bytes, bytes]]:
    """``secret_log_variants`` 的每个写法在 UTF-8 / GBK / UTF-16LE 下的字节，配同一编码的占位；
    编不了的（GBK 里没有的字）跳过，重复的只留一份，长的在前。"""

    pairs: dict[bytes, bytes] = {}
    for variant in variants:
        for encoding in _SECRET_BYTE_ENCODINGS:
            try:
                raw = variant.encode(encoding)
                placeholder = REDACTED_SECRET_TEXT.encode(encoding)
            except UnicodeEncodeError:
                continue
            if raw:
                pairs.setdefault(raw, placeholder)
    return sorted(pairs.items(), key=lambda item: len(item[0]), reverse=True)


def redact_secret_bytes(data: bytes, pairs: list[tuple[bytes, bytes]]) -> bytes:
    """按 ``secret_byte_pairs`` 把字节里的密码换成占位。"""

    for raw, placeholder in pairs:
        if raw in data:
            data = data.replace(raw, placeholder)
    return data


def redact_secret_text(text: str, variants: list[str]) -> str:
    """把 ``text`` 里出现的密码（``secret_log_variants`` 给出的写法）换成占位。"""

    for variant in variants:
        if variant in text:
            text = text.replace(variant, REDACTED_SECRET_TEXT)
    return text


def log_redaction_notice(interface: MaaFWInterface, values: list[str]) -> str | None:
    """项目声明了 password 输入框、或本次有要打码的值时写进 ``.worker.log`` 开头的打码说明，
    都没有就是 None。

    ``values`` 是本次运行要打码的密码值（``password_values.collect_run_password_values``）：
    项目把 password 标记全撤掉之后，账号快照里留着的密文解开照样会进日志，那时也要打码、也要
    写这一行。
    """

    if not password_input_names(interface) and not values:
        return None
    short = sum(1 for value in values if len(value) < MIN_REDACTED_SECRET_LENGTH)
    notice = (
        f"{LOG_REDACTION_MARKER} 本次的 .worker.log 与 .maafw.log 已把 "
        f"{len(values) - short} 个密码值换成「{REDACTED_SECRET_TEXT}」"
    )
    if short:
        notice += f"；另有 {short} 个短于 {MIN_REDACTED_SECRET_LENGTH} 个字符，未打码"
    return notice


def run_secret_values(
    plan: MaaFWRunPlan | None,
    interface: MaaFWInterface | None,
    user_snapshot_raw: Any | None,
    opener: MaaFWSecretOpener,
) -> list[str]:
    """本次运行要打码的密码值：计划里 password 字段的值 + 该账号快照里全部密文解开的值
    （项目撤掉了 password 标记的字段建计划时照样解开，见 option_secrets）。

    ``user_snapshot_raw`` 是账号 ``Task.TaskSnapshot`` 的原值；计划或 interface 还没有时没有可打码的值。
    """

    if plan is None or interface is None:
        return []
    return collect_run_password_values(plan, interface, user_snapshot_raw, opener)


def project_log_secret_variants(
    run_variants: list[str],
    script_snapshots_raw: Iterable[Any],
    interface: MaaFWInterface | None,
    opener: MaaFWSecretOpener,
) -> list[str]:
    """项目日志要打码的写法：项目日志不一定是本次运行的用户写的（上一个账号留下的片段也可能落在
    本次新增里），所以按脚本全部用户的密码（``script_snapshots_raw``）打码，再并上本次运行的
    ``run_variants``。收集出错时退回本次运行的那组。"""

    try:
        values = collect_snapshots_password_values(
            script_snapshots_raw, interface, opener
        )
    except Exception as exc:  # noqa: BLE001 - 取不到时退回本次运行计划里的
        logger.debug(f"收集脚本全部用户的密码失败，只按本次运行的打码: {exc}")
        return run_variants
    return sorted(
        set(run_variants) | set(secret_log_variants(values)),
        key=len,
        reverse=True,
    )


__all__ = [
    "LOG_REDACTION_MARKER",
    "MIN_REDACTED_SECRET_LENGTH",
    "REDACTED_SECRET_TEXT",
    "log_redaction_notice",
    "project_log_secret_variants",
    "run_secret_values",
    "redact_secret_bytes",
    "redact_secret_text",
    "secret_byte_pairs",
    "secret_log_variants",
]
