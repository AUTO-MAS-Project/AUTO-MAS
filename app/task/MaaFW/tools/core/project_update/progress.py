"""项目更新进度事件的类型化视图（纯数据，零宿主耦合）。

核心包（``updater`` / ``transport`` / ``apply``）经 ``progress`` 回调发的是 JSON 友好的
dict（``ProgressCallback``，回调签名不变）：阶段名在 ``stage``，其余字段按阶段各写各的
（下载是 ``downloaded_bytes`` / ``total_bytes``，解压是 ``extractedFiles`` …，包类型有
``package_type`` / ``packageType`` 两种写法）。宿主侧的消费方（编辑页 WS 面板的
``MaaFWUpdateProgressTracker``、运行前 / 运行后任务日志的 ``MaaFWUpdateTaskLogTranslator``、
manager 记最近阶段与字节数）一律先经 :meth:`UpdateProgressEvent.of` 转成这里的模型再读，
字段名与「非法值当未知」的口径只在这里定一次。

这不是 WS 契约：发给前端的仍是 ``WSMaaFWProjectUpdateProgressData``，由 tracker 组装。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

# 核心包写包类型的两种键名，按这个顺序读（后读到、能认出的为准）。
PACKAGE_TYPE_KEYS = ("package_type", "packageType")


def optional_count(value: Any) -> int | None:
    """进度事件里的计数 / 字节数：缺字段、布尔、非整数、负数一律当未知（None）。"""

    if isinstance(value, bool) or value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


@dataclass(frozen=True)
class UpdateProgressEvent:
    """一条核心包进度事件。

    - ``stage``：阶段名（去掉首尾空白；空串表示这条事件没有阶段、消费方一律忽略）。
    - ``status`` / ``message`` / ``version``：原样转成字符串（缺字段为空串）。
    - ``package_types``：事件里出现过的包类型原值，按 :data:`PACKAGE_TYPE_KEYS` 的顺序
      （``full`` / ``delta``，归一成对外名由宿主做）。
    - 计数与字节：经 :func:`optional_count`，未知为 None。
    - ``raw``：原始 dict（只读，留给要看额外字段的调用方）。
    """

    stage: str
    status: str = ""
    message: str = ""
    version: str = ""
    package_types: tuple[Any, ...] = ()
    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    extracted_files: int | None = None
    extract_total_files: int | None = None
    extracted_bytes: int | None = None
    extract_total_bytes: int | None = None
    applied_files: int | None = None
    total_files: int | None = None
    raw: Mapping[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @classmethod
    def from_mapping(cls, event: Mapping[str, Any]) -> UpdateProgressEvent:
        """从核心包的 dict 事件构造；任何字段缺失或非法都不抛。"""

        return cls(
            stage=str(event.get("stage") or "").strip(),
            status=str(event.get("status") or ""),
            message=str(event.get("message") or ""),
            version=str(event.get("version") or ""),
            package_types=tuple(
                event.get(key) for key in PACKAGE_TYPE_KEYS if key in event
            ),
            downloaded_bytes=optional_count(event.get("downloaded_bytes")),
            total_bytes=optional_count(event.get("total_bytes")),
            extracted_files=optional_count(event.get("extractedFiles")),
            extract_total_files=optional_count(event.get("extractTotalFiles")),
            extracted_bytes=optional_count(event.get("extractedBytes")),
            extract_total_bytes=optional_count(event.get("extractTotalBytes")),
            applied_files=optional_count(event.get("appliedFiles")),
            total_files=optional_count(event.get("totalFiles")),
            raw=event,
        )

    @classmethod
    def of(cls, event: UpdateProgressEvent | Mapping[str, Any]) -> UpdateProgressEvent:
        """已是模型就原样返回，否则按 dict 转。消费方的入口都先过这一步。"""

        if isinstance(event, cls):
            return event
        return cls.from_mapping(event)


__all__ = ["PACKAGE_TYPE_KEYS", "UpdateProgressEvent", "optional_count"]
