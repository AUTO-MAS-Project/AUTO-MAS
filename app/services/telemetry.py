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
from pathlib import Path
from typing import Any

import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration


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

_sentry_release: str | None = None
_sentry_dist: str | None = None
_sentry_started = False


def _strip_url_query(url: str) -> str:
    """移除 URL 中可能包含隐私数据的查询参数和片段。"""

    return url.split("?", 1)[0].split("#", 1)[0]


def _sanitize_path(value: str) -> str:
    """移除路径查询信息，并将本机路径缩减为文件名。"""

    sanitized = _strip_url_query(value)
    is_windows_path = (
        len(sanitized) >= 3
        and sanitized[1] == ":"
        and sanitized[2] in {"\\", "/"}
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


def sanitize_event(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    """在发送前移除用户、请求内容和本机绝对路径。"""

    del hint
    event.pop("user", None)
    event.pop("extra", None)

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
            git_dir = (source_root / git_dir_value.removeprefix("gitdir:").strip()).resolve()

        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref:"):
            ref_name = head.removeprefix("ref:").strip()
            ref_path = git_dir / ref_name
            if ref_path.is_file():
                revision = ref_path.read_text(encoding="utf-8").strip()
            else:
                revision = ""
                for line in (git_dir / "packed-refs").read_text(
                    encoding="utf-8"
                ).splitlines():
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
            LoggingIntegration(level=None, event_level=None, sentry_logs_level=None)
        ],
        traces_sample_rate=0.1,
        before_send=sanitize_event,
        before_send_transaction=sanitize_event,
    )
    _sentry_started = True


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
        _start_sentry(_sentry_release, _sentry_dist)


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
    "resolve_sentry_dist",
    "sanitize_event",
    "set_telemetry_enabled",
]
