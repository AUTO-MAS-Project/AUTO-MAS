#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import json
import re
from contextlib import contextmanager
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import sentry_sdk
from sentry_sdk import metrics
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.loguru import LoguruIntegration


SENTRY_DSN = (
    "https://eae490f602916b04f2f51f49f0fb5155@"
    "o4511881138733056.ingest.us.sentry.io/4511902512644096"
)
PRIVATE_REQUEST_FIELDS = {
    "cookies",
    "data",
    "env",
    "headers",
    "query_string",
}
PRIVATE_DATA_MARKERS = {
    "body",
    "cookie",
    "cookies",
    "header",
    "headers",
    "query",
    "query_string",
    "statement",
}

PATH_DATA_MARKERS = {"file", "filename", "path", "uri", "url"}

# Loguru 会把 traceback 与局部变量渲染进日志正文，其中含形如
# ``C:\Users\<用户名>\...`` 的本机绝对路径；结构化字段的清洗覆盖不到正文，
# 需在此按用户目录段单独遮蔽。局部变量以 repr 形式渲染，分隔符会是转义后的
# ``C:\\Users\\<用户名>``，故分隔符按一个或多个匹配。
USER_DIR_PATTERN = re.compile(
    r"((?:[A-Za-z]:)?[\\/]+(?:Users|home)[\\/]+)([^\\/\r\n\"'<>|]+)",
    re.IGNORECASE,
)

_sentry_release: str | None = None
_sentry_dist: str | None = None
_sentry_started = False

NOISY_TRANSACTIONS = {
    "/api/core/health",
    "/api/core/ws_meta",
}


def _strip_url_query(url: str) -> str:
    """移除 URL 中可能包含隐私数据的查询参数和片段。"""

    return url.split("?", 1)[0].split("#", 1)[0]


def _sanitize_path(value: str) -> str:
    """移除路径查询信息，并将本机路径缩减为文件名。"""

    sanitized = _strip_url_query(value)
    is_windows_path = (
        len(sanitized) >= 3 and sanitized[1] == ":" and sanitized[2] in {"\\", "/"}
    )
    if not sanitized.lower().startswith("file://") and not is_windows_path:
        return sanitized

    normalized = sanitized.replace("\\", "/")
    return normalized.rsplit("/", 1)[-1] or "<local-file>"


def _sanitize_data(data: Any) -> None:
    """清理 Breadcrumb 和 Span 中可能包含隐私的数据。"""

    if not isinstance(data, dict):
        return

    for key, value in list(data.items()):
        if not isinstance(key, str):
            continue
        markers = set(key.lower().replace("-", ".").replace("_", ".").split("."))
        if markers & PRIVATE_DATA_MARKERS:
            data.pop(key, None)
        elif markers & PATH_DATA_MARKERS and isinstance(value, str):
            data[key] = _sanitize_path(value)


def _sanitize_stacktrace(stacktrace: Any) -> None:
    """从堆栈帧中移除本机绝对路径。"""

    if not isinstance(stacktrace, dict):
        return

    frames = stacktrace.get("frames")
    if not isinstance(frames, list):
        return

    for frame in frames:
        if isinstance(frame, dict):
            if isinstance(frame.get("filename"), str):
                frame["filename"] = _sanitize_path(frame["filename"])
            frame.pop("abs_path", None)
            frame.pop("vars", None)
            frame.pop("context_line", None)
            frame.pop("pre_context", None)
            frame.pop("post_context", None)
            frame.pop("module_metadata", None)


def _mask_user_dirs(value: str) -> str:
    """遮蔽路径中的用户名段，保留路径结构以便定位问题。"""

    return USER_DIR_PATTERN.sub(r"\1<user>", value)


def _sanitize_text_fields(event: dict[str, Any]) -> None:
    """清洗日志正文与异常描述中的本机用户名。"""

    logentry = event.get("logentry")
    if isinstance(logentry, dict):
        for field in ("message", "formatted"):
            text = logentry.get(field)
            if isinstance(text, str):
                logentry[field] = _mask_user_dirs(text)
        params = logentry.get("params")
        if isinstance(params, list):
            logentry["params"] = [
                _mask_user_dirs(param) if isinstance(param, str) else param
                for param in params
            ]

    message = event.get("message")
    if isinstance(message, str):
        event["message"] = _mask_user_dirs(message)


def sanitize_event(
    event: dict[str, Any], hint: dict[str, Any]
) -> dict[str, Any] | None:
    """在发送前移除用户、请求内容和本机绝对路径。"""

    log_record = hint.get("log_record")
    if log_record is not None and not getattr(log_record, "exc_info", None):
        return None

    event.pop("user", None)
    event.pop("extra", None)

    _sanitize_text_fields(event)

    request = event.get("request")
    if isinstance(request, dict):
        for field in PRIVATE_REQUEST_FIELDS:
            request.pop(field, None)
        if isinstance(request.get("url"), str):
            request["url"] = _sanitize_path(request["url"])

    _sanitize_stacktrace(event.get("stacktrace"))
    for container_name in ("exception", "threads"):
        container = event.get(container_name)
        if not isinstance(container, dict):
            continue
        values = container.get("values")
        if not isinstance(values, list):
            continue
        for value in values:
            if isinstance(value, dict):
                _sanitize_stacktrace(value.get("stacktrace"))
                if isinstance(value.get("value"), str):
                    value["value"] = _mask_user_dirs(value["value"])

    breadcrumbs = event.get("breadcrumbs")
    if isinstance(breadcrumbs, dict) and isinstance(breadcrumbs.get("values"), list):
        for breadcrumb in breadcrumbs["values"]:
            if not isinstance(breadcrumb, dict):
                continue
            data = breadcrumb.get("data")
            if not isinstance(data, dict):
                continue
            for field in PRIVATE_REQUEST_FIELDS:
                data.pop(field, None)
            _sanitize_data(data)

    spans = event.get("spans")
    if isinstance(spans, list):
        for span in spans:
            if isinstance(span, dict):
                _sanitize_data(span.get("data"))

    return event


def is_telemetry_enabled(config_path: Path) -> bool:
    """读取遥测开关；缺失或损坏的旧配置按默认开启处理。"""

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        value = data.get("Function", {}).get("IfEnableTelemetry", True)
        return value if isinstance(value, bool) else True
    except (OSError, json.JSONDecodeError, AttributeError):
        return True


def resolve_sentry_dist(source_root: Path) -> str | None:
    """读取当前源码提交短哈希，缺少 Git 元数据时返回空。"""

    try:
        git_dir = source_root / ".git"
        if git_dir.is_file():
            git_dir_value = git_dir.read_text(encoding="utf-8").strip()
            if not git_dir_value.startswith("gitdir:"):
                return None
            git_dir = (
                source_root / git_dir_value.removeprefix("gitdir:").strip()
            ).resolve()

        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref:"):
            ref_name = head.removeprefix("ref:").strip()
            ref_path = git_dir / ref_name
            if ref_path.is_file():
                revision = ref_path.read_text(encoding="utf-8").strip()
            else:
                revision = ""
                for line in (
                    (git_dir / "packed-refs").read_text(encoding="utf-8").splitlines()
                ):
                    if line.endswith(f" {ref_name}"):
                        revision = line.split(" ", 1)[0]
                        break
        else:
            revision = head
    except (OSError, UnicodeError):
        return None

    if not re.fullmatch(r"[0-9a-fA-F]{7,64}", revision):
        return None
    return revision[:12].lower()


def _start_sentry(release: str, dist: str | None = None) -> None:
    """使用固定的脱敏策略启动 Sentry。"""

    global _sentry_started

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        release=f"auto-mas@{release}",
        dist=dist,
        environment="production",
        send_default_pii=False,
        include_local_variables=False,
        include_source_context=False,
        max_request_body_size="never",
        server_name="AUTO-MAS",
        integrations=[
            LoggingIntegration(level=None, event_level=None, sentry_logs_level=None),
            LoguruIntegration(level=None, event_level=30, sentry_logs_level=None),
        ],
        traces_sampler=sample_trace,
        before_send=sanitize_event,
        before_send_transaction=sanitize_event,
    )
    _sentry_started = True


def sample_trace(sampling_context: dict[str, Any]) -> float:
    """优先保留任务链路，跳过高频探活，并限制普通请求的配额占用。"""

    transaction_context = sampling_context.get("transaction_context")
    if not isinstance(transaction_context, dict):
        return 0.02

    name = transaction_context.get("name")
    op = transaction_context.get("op")
    if name in NOISY_TRANSACTIONS:
        return 0.0
    if op == "auto_mas.task.run":
        return 0.25

    parent_sampled = sampling_context.get("parent_sampled")
    if isinstance(parent_sampled, bool):
        return 1.0 if parent_sampled else 0.0
    return 0.02


def set_telemetry_enabled(enabled: bool) -> None:
    """立即启用或停用后端遥测；开发环境下恒为空操作。"""

    global _sentry_started

    if not enabled:
        if _sentry_started:
            sentry_sdk.get_client().close(timeout=0)
            sentry_sdk.init(dsn=None)
            _sentry_started = False
        return

    if not _sentry_started and _sentry_release is not None:
        if _sentry_dist is None:
            _start_sentry(_sentry_release)
        else:
            _start_sentry(_sentry_release, _sentry_dist)


def record_count(
    name: str,
    value: float = 1,
    *,
    attributes: Mapping[str, str | int | float | bool] | None = None,
) -> None:
    """记录低基数计数指标；遥测关闭或 SDK 异常时保持空操作。"""

    if not _sentry_started:
        return

    try:
        metrics.count(name, value, attributes=dict(attributes or {}))
    except Exception:
        pass


def record_distribution(
    name: str,
    value: float,
    *,
    unit: str | None = None,
    attributes: Mapping[str, str | int | float | bool] | None = None,
) -> None:
    """记录低基数分布指标；遥测失败不能影响业务流程。"""

    if not _sentry_started:
        return

    try:
        metrics.distribution(
            name,
            value,
            unit=unit,
            attributes=dict(attributes or {}),
        )
    except Exception:
        pass


@contextmanager
def observe_span(
    *,
    name: str,
    op: str,
    attributes: Mapping[str, str | int | float | bool] | None = None,
    force_transaction: bool = False,
) -> Iterator[None]:
    """在遥测开启时创建 Span，关闭时保持相同调用语义。"""

    if not _sentry_started:
        yield
        return

    start_observation = (
        sentry_sdk.start_span
        if not force_transaction and sentry_sdk.get_current_span() is not None
        else sentry_sdk.start_transaction
    )
    with start_observation(name=name, op=op) as span:
        for key, value in (attributes or {}).items():
            span.set_data(key, value)
        yield


def init_sentry(
    release: str,
    development: bool,
    enabled: bool = True,
    dist: str | None = None,
) -> None:
    """按运行环境和用户配置初始化后端 Sentry。

    Args:
        release: 当前主程序版本号。
        development: 是否为开发环境，开发环境不上报任何数据。
        enabled: 用户配置的匿名遥测开关。
        dist: 当前源码提交或构建标识。
    """

    global _sentry_dist, _sentry_release

    # 开发环境不记录版本号，后续遥测开关变更同样不会启动 Sentry
    if development:
        return

    _sentry_release = release
    _sentry_dist = dist
    set_telemetry_enabled(enabled)


__all__ = [
    "init_sentry",
    "is_telemetry_enabled",
    "observe_span",
    "record_count",
    "record_distribution",
    "resolve_sentry_dist",
    "sample_trace",
    "sanitize_event",
    "set_telemetry_enabled",
]
