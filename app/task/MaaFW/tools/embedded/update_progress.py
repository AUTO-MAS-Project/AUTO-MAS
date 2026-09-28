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

"""MaaFW 项目手动更新过程 → WS 进度数据的翻译。

核心包（``updater`` / ``transport`` / ``apply``）各自发裸 dict 事件，阶段名与
字段名并不统一；编辑页「更新过程」面板要的是一份稳定的
:class:`WSMaaFWProjectUpdateProgressData`。翻译只在这里做一次，检查与应用
两条路径共用。

- 下载速度按 ``downloaded_bytes`` 的时间差在这里算，核心包不管。
- 下载、解压与覆盖三类高频事件按时间节流（默认 0.5s），但收尾事件必发，前端才能
  走到满格。
- 全量 / 差量：核心包叫 ``full`` / ``delta``，对外统一成 ``full`` /
  ``incremental``。
- 所有文案先过 :func:`sanitize_log_message`，WS 通道同日志一样不得泄露 CDK。

运行前自动更新没有这块面板，进度只能进任务日志，翻译在
:class:`MaaFWUpdateTaskLogTranslator`：日志是**追加**的，每多一行就多一条
永久记录，所以节流按进度跨度（下载 5%、解压 10%、覆盖 25%）而不是时间。
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any

from app.models.schema import WSMaaFWProjectUpdateProgressData
from app.task.MaaFW.tools.core.project_update.timing import format_duration
from app.utils.security import sanitize_log_message

STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"

PACKAGE_KIND_FULL = "full"
PACKAGE_KIND_INCREMENTAL = "incremental"

# 核心包里表示「本次更新已收尾」的 completed 子状态；除 updated 外都算成功结束。
_FINAL_STAGES = frozenset({"completed", "failed"})
_THROTTLED_STAGES = frozenset({"downloading", "extracting", "applying"})

_STAGE_MESSAGES: dict[str, str] = {
    "checking": "正在检查更新",
    "downloading": "正在下载更新包",
    "downloaded": "更新包下载完成",
    "extracting": "正在解压更新包",
    "plan_validated": "更新计划校验通过，正在准备新版本",
    "staged": "已从当前版本复制出新版本骨架，开始套用更新包",
    "applying": "正在套用更新包",
    "post_validating": "正在预检新版本的运行环境",
    "committed": "新版本已登记，正在切换脚本",
    # 不再发出：新版本只在 staging 里建，失败就丢掉，没有回滚。词表项留着兼容。
    "rolled_back": "更新失败，已回滚到更新前状态",
}

# 解压开始时先补发的一条过渡消息用的阶段名（旧前端认识、归到「准备」阶段）。
# v5.6.0 的前端没有 extracting：未知阶段停在上一个阶段（downloading），而 downloading 下
# 会拿这条事件的 percent / downloadedBytes / totalBytes 覆盖显示——下载条从 100% 倒回去、
# 字节变空，message 反而不显示。先发一条 staged 把它切到「准备」阶段：之后的 extracting
# 在旧前端上停在「准备」，状态行显示「准备覆盖 · 正在解压更新包 30%（…）」，不碰下载字段；
# 新前端收到 extracting 立刻切到「解压中」，这条过渡只闪一下。只进 WS，不进日志与任务日志。
_LEGACY_PREPARING_STAGE = "staged"

# 任务日志的节流步长：下载每 5%、解压每 10%、覆盖每 25% 一行。359MB 的包按 5% 是
# 20 行，既看得出在动，也不会把用户自己的运行日志淹掉。
_DOWNLOAD_PERCENT_STEP = 5.0
_DOWNLOAD_UNKNOWN_STEP_BYTES = 32 * 1024 * 1024
_EXTRACT_PERCENT_STEP = 10.0
_APPLY_PERCENT_STEP = 25.0
# 这些阶段核心包自己已经用 send_log 写过人话（比对 / 复制骨架 / 预检的开始与带用时的
# 结束行都在 updater 里），再翻一遍就是重复行。
_TASK_LOG_SKIPPED_STAGES = frozenset(
    {"checking", "completed", "failed", "plan_validated", "staged", "post_validating"}
)


def _megabytes(value: float | int | None) -> str:
    """字节数 → 一位小数的 MB 数字（不带单位，由调用方拼）。"""

    return f"{(value or 0) / (1024 * 1024):.1f}"


def _format_eta(seconds: float) -> str:
    """剩余秒数 → 「1 分 46 秒」这类中文时长。

    一律向下取整：``round`` 会把 59.6 说成「60 秒」、3599.7 说成「60 分」，
    看着像坏了。
    """

    total = int(seconds)
    if total < 60:
        return f"{total} 秒"
    if total < 3600:
        return f"{total // 60} 分 {total % 60} 秒"
    return f"{total // 3600} 小时 {(total % 3600) // 60} 分"


def normalize_package_kind(raw_value: Any) -> str | None:
    """把核心包的 ``full`` / ``delta`` 归一成对外的 ``full`` / ``incremental``。"""

    value = str(raw_value or "").strip().lower()
    if value == "full":
        return PACKAGE_KIND_FULL
    if value in {"delta", "incremental"}:
        return PACKAGE_KIND_INCREMENTAL
    return None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _percent(done: int | None, total: int | None) -> float | None:
    if done is None or not total or total <= 0:
        return None
    return round(min(100.0, done / total * 100.0), 1)


_ExtractCounts = tuple[int | None, int | None, int | None, int | None]


def _extract_counts(event: Mapping[str, Any]) -> _ExtractCounts:
    """解压事件的 (已解压文件, 文件总数, 已解压字节, 展开总字节)。"""

    return (
        _optional_int(event.get("extractedFiles")),
        _optional_int(event.get("extractTotalFiles")),
        _optional_int(event.get("extractedBytes")),
        _optional_int(event.get("extractTotalBytes")),
    )


def _extract_percent(
    files: int | None,
    total_files: int | None,
    done_bytes: int | None,
    total_bytes: int | None,
) -> float | None:
    """解压百分比取字节与文件数两个进度的平均。

    只按字节算，包里的大文件排在前面时会出现「100%（3/33 个文件）」；只按文件数算，
    一个几百 MB 的模型文件又会让进度停在原地。两者都给不出时用能给的那个。
    """

    by_bytes = _percent(done_bytes, total_bytes)
    by_files = _percent(files, total_files)
    if by_bytes is None or by_files is None:
        return by_bytes if by_bytes is not None else by_files
    return round((by_bytes + by_files) / 2, 1)


def _extract_finished(
    files: int | None,
    total_files: int | None,
    done_bytes: int | None,
    total_bytes: int | None,
) -> bool:
    if files is None or total_files is None or files < total_files:
        return False
    return not total_bytes or (done_bytes or 0) >= total_bytes


def _describe_extract(
    files: int | None,
    total_files: int | None,
    done_bytes: int | None,
    total_bytes: int | None,
) -> str:
    """「正在解压更新包 30%（1200/5230 个文件，105.2 / 350.8 MB）」；缺哪项就不写哪项。

    百分比也写进文案：v5.6.0 的前端不认识 extracting，只显示这句 message（见
    :data:`_LEGACY_PREPARING_STAGE`），没有进度条。
    """

    text = _STAGE_MESSAGES["extracting"]
    percent = _extract_percent(files, total_files, done_bytes, total_bytes)
    if percent is not None:
        text = f"{text} {int(percent)}%"
    details: list[str] = []
    if files is not None and total_files is not None:
        details.append(f"{files}/{total_files} 个文件")
    if done_bytes is not None and total_bytes:
        details.append(f"{_megabytes(done_bytes)} / {_megabytes(total_bytes)} MB")
    return f"{text}（{'，'.join(details)}）" if details else text


class MaaFWUpdateProgressTracker:
    """一次手动更新请求的进度状态机；每次请求新建一个。

    Args:
        clock: 单调时钟，测试注入用；默认 ``time.monotonic``。
        throttle_seconds: 下载 / 覆盖事件的最小间隔，收尾事件不受限。
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        throttle_seconds: float = 0.5,
    ) -> None:
        self._clock = clock
        self._throttle = max(0.0, float(throttle_seconds))
        self.package_kind: str | None = None
        # 节流只在同一阶段内部比：阶段一换（checking → downloading、
        # staged → applying）首条必发，否则下载刚开始那条会被上一阶段的时间戳吞掉。
        self._last_stage: str | None = None
        self._last_emit_at: float | None = None
        # 上一次**已发出**的下载采样点，速度按发出点之间的差算，
        # 节流吞掉的采样不参与，否则 0.5s 内的抖动会把速度算得忽高忽低。
        self._last_sample: tuple[float, int] | None = None
        self._extract_announced = False

    # ------------------------------------------------------------------ 组装

    def _data(
        self,
        stage: str,
        *,
        status: str = STATUS_RUNNING,
        message: str = "",
        **fields: Any,
    ) -> WSMaaFWProjectUpdateProgressData:
        return WSMaaFWProjectUpdateProgressData(
            stage=stage,
            status=status,
            message=sanitize_log_message(str(message or "")),
            packageKind=fields.pop("packageKind", self.package_kind),
            **fields,
        )

    def _throttled(self, stage: str, now: float) -> bool:
        if self._last_emit_at is None or self._last_stage != stage:
            return False
        return now - self._last_emit_at < self._throttle

    def _mark_emitted(self, stage: str, now: float) -> None:
        self._last_stage = stage
        self._last_emit_at = now

    # ------------------------------------------------------------------ 入口

    def log(self, line: str) -> WSMaaFWProjectUpdateProgressData:
        """一行更新日志；调用方已打码也无妨，这里再过一遍。"""

        text = sanitize_log_message(str(line))
        return self._data("log", message=text, log=text)

    def checking(self, message: str = "") -> WSMaaFWProjectUpdateProgressData:
        return self._data("checking", message=message or _STAGE_MESSAGES["checking"])

    def finished(
        self,
        *,
        success: bool,
        message: str,
        package_kind: str | None = None,
    ) -> WSMaaFWProjectUpdateProgressData:
        """调用方自己收尾（检查路径没有核心包的 completed 事件）。"""

        if package_kind is not None:
            self.package_kind = normalize_package_kind(package_kind)
        return self._data(
            "completed" if success else "failed",
            status=STATUS_SUCCESS if success else STATUS_FAILED,
            message=message,
        )

    def events(
        self, event: Mapping[str, Any]
    ) -> list[WSMaaFWProjectUpdateProgressData]:
        """同 :meth:`event`，但返回要发的全部 WS 消息（被节流吞掉时为空）。

        一条核心事件目前最多对应两条：解压的第一条前面先补一条旧前端兼容的过渡消息
        （见 :data:`_LEGACY_PREPARING_STAGE`）。WS 发送方用这个入口。
        """

        data = self.event(event)
        if data is None:
            return []
        if data.stage == "extracting" and not self._extract_announced:
            self._extract_announced = True
            return [self._data(_LEGACY_PREPARING_STAGE, message=data.message), data]
        return [data]

    def event(
        self, event: Mapping[str, Any]
    ) -> WSMaaFWProjectUpdateProgressData | None:
        """翻译一条核心包进度事件；被节流吞掉时返回 ``None``。"""

        stage = str(event.get("stage") or "").strip()
        if not stage:
            return None

        for key in ("package_type", "packageType"):
            if key in event:
                kind = normalize_package_kind(event.get(key))
                if kind is not None:
                    self.package_kind = kind

        if stage in _FINAL_STAGES:
            return self._final(stage, event)
        if stage in {"downloading", "downloaded"}:
            return self._download(stage, event)
        if stage == "extracting":
            return self._extracting(event)
        if stage == "applying":
            return self._applying(event)
        return self._plain(stage, event)

    # ------------------------------------------------------------------ 各阶段

    def _final(
        self, stage: str, event: Mapping[str, Any]
    ) -> WSMaaFWProjectUpdateProgressData:
        message = str(event.get("message") or "")
        if stage == "failed":
            return self._data(
                stage, status=STATUS_FAILED, message=message or "更新失败"
            )
        return self._data(
            "completed", status=STATUS_SUCCESS, message=message or "更新已完成"
        )

    def _plain(
        self, stage: str, event: Mapping[str, Any]
    ) -> WSMaaFWProjectUpdateProgressData:
        message = str(event.get("message") or "")
        if stage == "checking":
            # 核心包这一步的 message 是英文流水（"checking for project updates"），
            # 面板上统一用中文阶段文案；发现版本时把版本号带上。
            if str(event.get("status") or "") == "version_discovered":
                version = str(event.get("version") or "").strip()
                message = f"发现新版本 {version}" if version else "发现新版本"
            else:
                message = _STAGE_MESSAGES["checking"]
        self._mark_emitted(stage, self._clock())
        return self._data(stage, message=message or _STAGE_MESSAGES.get(stage, ""))

    def _download(
        self, stage: str, event: Mapping[str, Any]
    ) -> WSMaaFWProjectUpdateProgressData | None:
        downloaded = _optional_int(event.get("downloaded_bytes"))
        total = _optional_int(event.get("total_bytes"))
        now = self._clock()
        finished = stage == "downloaded" or (
            downloaded is not None and total is not None and downloaded >= total
        )
        if not finished and self._throttled("downloading", now):
            return None

        speed: float | None = None
        if downloaded is not None and self._last_sample is not None:
            last_at, last_bytes = self._last_sample
            elapsed = now - last_at
            # 字节数回退说明换了一次尝试（断点续传重连），速度从头算。
            if downloaded >= last_bytes and elapsed > 0:
                speed = round((downloaded - last_bytes) / elapsed, 1)
        if downloaded is not None:
            self._last_sample = (now, downloaded)
        self._mark_emitted("downloading", now)

        percent = 100.0 if finished and total else _percent(downloaded, total)
        return self._data(
            stage,
            message=_STAGE_MESSAGES["downloaded" if finished else "downloading"],
            percent=percent,
            downloadedBytes=downloaded,
            totalBytes=total,
            speedBytesPerSec=speed,
        )

    def _extracting(
        self, event: Mapping[str, Any]
    ) -> WSMaaFWProjectUpdateProgressData | None:
        files, total_files, done_bytes, total_bytes = _extract_counts(event)
        now = self._clock()
        finished = _extract_finished(files, total_files, done_bytes, total_bytes)
        # 首个（0 个文件、0 字节）与最后一个必发；中间按时间节流，与覆盖同一口径。
        started = not files and not done_bytes
        if not started and not finished and self._throttled("extracting", now):
            return None
        self._mark_emitted("extracting", now)
        return self._data(
            "extracting",
            message=_describe_extract(files, total_files, done_bytes, total_bytes),
            percent=_extract_percent(files, total_files, done_bytes, total_bytes),
            extractedFiles=files,
            extractTotalFiles=total_files,
            extractedBytes=done_bytes,
            extractTotalBytes=total_bytes,
        )

    def _applying(
        self, event: Mapping[str, Any]
    ) -> WSMaaFWProjectUpdateProgressData | None:
        applied = _optional_int(event.get("appliedFiles"))
        total = _optional_int(event.get("totalFiles"))
        now = self._clock()
        finished = applied is not None and total is not None and applied >= total
        # 首个 applying（appliedFiles=0）与最后一个必发；中间按时间节流。
        if applied and not finished and self._throttled("applying", now):
            return None
        self._mark_emitted("applying", now)
        message = _STAGE_MESSAGES["applying"]
        if applied is not None and total is not None:
            message = f"{message} {applied}/{total}"
        return self._data(
            "applying",
            message=message,
            percent=_percent(applied, total),
            appliedFiles=applied,
            totalFiles=total,
        )


class MaaFWUpdateTaskLogTranslator:
    """核心包进度事件 → 运行前自动更新要追加进任务日志的中文行。

    返回 ``None`` 表示这条事件不值得单独占一行。与 WS 面板的区别：

    - 节流按**进度跨度**：下载每跨 5%（``total`` 未知时每 32MB）、解压每跨 10%、
      覆盖每跨 25% 一行，收尾必发（解压的首尾两行由核心包写，这里不出）。按时间节流
      会让 359MB 的下载刷出几百行。
    - ``checking`` / ``completed`` / ``failed`` / ``plan_validated`` / ``staged`` /
      ``post_validating`` 一律跳过：核心包自己已经用 ``send_log`` 写过人话（后三个带
      用时），再翻一遍就是重复行；取消时宿主另有自己的文案。

    速度沿用 :class:`MaaFWUpdateProgressTracker` 算好的 ``speedBytesPerSec``，
    而且**只把决定要发的事件喂给它**——这样速度是两条相邻日志行之间的平均，
    不是两个 64KB chunk 之间的抖动。因此内部那个 tracker 不再按时间节流。
    """

    def __init__(
        self,
        *,
        tracker: MaaFWUpdateProgressTracker | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._tracker = tracker or MaaFWUpdateProgressTracker(throttle_seconds=0.0)
        self._clock = clock
        self._download_key: int | None = None
        self._download_done = False
        self._extract_started_at: float | None = None
        self._extract_bucket: int | None = None
        self._apply_bucket: int | None = None
        self._apply_done = False

    def event(self, event: Mapping[str, Any]) -> str | None:
        stage = str(event.get("stage") or "").strip()
        if not stage or stage in _TASK_LOG_SKIPPED_STAGES:
            return None
        if stage in {"downloading", "downloaded"}:
            return self._download(stage, event)
        if stage == "extracting":
            return self._extracting(event)
        if stage == "applying":
            return self._applying(event)
        message = _STAGE_MESSAGES.get(stage)
        return sanitize_log_message(message) if message else None

    # ------------------------------------------------------------------ 下载

    def _download(self, stage: str, event: Mapping[str, Any]) -> str | None:
        downloaded = _optional_int(event.get("downloaded_bytes"))
        total = _optional_int(event.get("total_bytes"))
        finished = stage == "downloaded" or (
            downloaded is not None
            and total is not None
            and total > 0
            and downloaded >= total
        )
        if finished:
            if self._download_done:
                return None
            self._download_done = True
            self._tracker.event(event)
            text = _STAGE_MESSAGES["downloaded"]
            return sanitize_log_message(
                f"{text}（{_megabytes(total or downloaded)} MB）"
                if (total or downloaded)
                else text
            )
        if downloaded is None or self._download_done:
            return None
        if total and total > 0:
            key = int(downloaded / total * 100.0 // _DOWNLOAD_PERCENT_STEP)
        else:
            # 总大小未知（服务端没给 Content-Length）时只能按绝对量报。
            key = downloaded // _DOWNLOAD_UNKNOWN_STEP_BYTES
        if self._download_key is not None and key == self._download_key:
            return None
        self._download_key = key
        data = self._tracker.event(event)
        if data is None:  # pragma: no cover - 内部 tracker 不节流
            return None
        head = _STAGE_MESSAGES["downloading"]
        if data.percent is not None:
            head = f"{head} {data.percent:.1f}%"
        details: list[str] = []
        if total:
            details.append(f"{_megabytes(downloaded)} / {_megabytes(total)} MB")
        else:
            details.append(f"已下载 {_megabytes(downloaded)} MB")
        if data.speedBytesPerSec:
            details.append(f"{_megabytes(data.speedBytesPerSec)} MB/s")
            # 0% 那行还没有速度，自然也没有 ETA；总大小未知时同理。359MB 的包
            # 「还要多久」比「现在多少 MB/s」更是用户真正想问的那个问题。
            if total and total > downloaded:
                details.append(
                    "预计剩余 "
                    + _format_eta((total - downloaded) / data.speedBytesPerSec)
                )
        return sanitize_log_message(f"{head}（{'，'.join(details)}）")

    # ------------------------------------------------------------------ 解压

    def _extracting(self, event: Mapping[str, Any]) -> str | None:
        """每跨 10% 一行，带文件数、MB 与已用时。

        开始（「正在解压更新包：N 个文件，解压后约 X MB」）与结束（「解压完成：…，用时 …」）
        两行由 updater 用 ``send_log`` 写，这里只出中间的，不重复。
        """

        files, total_files, done_bytes, total_bytes = _extract_counts(event)
        now = self._clock()
        if self._extract_started_at is None:
            self._extract_started_at = now
        percent = _extract_percent(files, total_files, done_bytes, total_bytes)
        if percent is None or _extract_finished(
            files, total_files, done_bytes, total_bytes
        ):
            return None
        bucket = int(percent // _EXTRACT_PERCENT_STEP)
        if self._extract_bucket is None:
            # 第一条（多半是 0%）只定起点，不单独占一行。
            self._extract_bucket = bucket
            if bucket == 0:
                return None
        elif bucket <= self._extract_bucket:
            return None
        self._extract_bucket = bucket
        details: list[str] = []
        if files is not None and total_files is not None:
            details.append(f"{files}/{total_files} 个文件")
        if done_bytes is not None and total_bytes:
            details.append(f"{_megabytes(done_bytes)} / {_megabytes(total_bytes)} MB")
        details.append(f"已用 {format_duration(now - self._extract_started_at)}")
        return sanitize_log_message(
            f"{_STAGE_MESSAGES['extracting']} {percent:.0f}%（{'，'.join(details)}）"
        )

    # ------------------------------------------------------------------ 覆盖

    def _applying(self, event: Mapping[str, Any]) -> str | None:
        applied = _optional_int(event.get("appliedFiles"))
        total = _optional_int(event.get("totalFiles"))
        if applied is None or not total or total <= 0:
            if self._apply_bucket is not None:
                return None
            self._apply_bucket = -1
            return sanitize_log_message(_STAGE_MESSAGES["applying"])
        finished = applied >= total
        if finished:
            if self._apply_done:
                return None
            self._apply_done = True
        else:
            bucket = int(applied / total * 100.0 // _APPLY_PERCENT_STEP)
            if self._apply_bucket is not None and bucket == self._apply_bucket:
                return None
            self._apply_bucket = bucket
        return sanitize_log_message(f"{_STAGE_MESSAGES['applying']} {applied}/{total}")


__all__ = [
    "MaaFWUpdateProgressTracker",
    "MaaFWUpdateTaskLogTranslator",
    "PACKAGE_KIND_FULL",
    "PACKAGE_KIND_INCREMENTAL",
    "STATUS_FAILED",
    "STATUS_RUNNING",
    "STATUS_SUCCESS",
    "normalize_package_kind",
]
