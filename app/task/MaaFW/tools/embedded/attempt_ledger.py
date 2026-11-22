"""一个账号这次运行的尝试记账：每次尝试的结构化运行记录、给通知与历史用的尝试结果。

运行这一块（方案 §3.7「结构化运行记录并进运行」），三个专项的账号流程都用它：一个账号一份
``MaaFWAttemptLedger``，跨尝试保留。只收普通数据（运行计划、worker 推来的事件原值、尝试的
结局与文案、``plan_run`` 交回的附件），不读脚本 / 账号配置，不碰调用方对象。

- 记账的键是调用方这次尝试的日志记录（``id(cur_user_log)``），与 history 一条记录对上。
- 结构化记录是旁路：记录这一侧出了错只记 warning（logger 沿用「MaaFW 插件自动代理」），
  返回 None，不影响运行与收尾（``call``）。
- ``HistoryWrite`` / ``HistoryAttachmentInput`` / ``HistorySnapshotStatistic`` 是宿主的 schema，
  由流程自己拼；这里只交回状态、记录原值与附件原样。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from app.task.MaaFW.blocks.maafw_interface.runner.models import MaaFWRunPlan
from app.task.MaaFW.tools.core.runner.run_events import (
    CATEGORY_HOST_ERROR,
    CATEGORY_USER_STOPPED,
    MaaFWTaskEndEvent,
    MaaFWTaskStartEvent,
)
from app.utils import get_logger

from .plan_run import MaaFWPlanRunAttachment
from .run_messages import (
    MISSING_TASK_USER_RESULT,
    retry_skipped_tasks,
    task_display_name,
)
from .run_record import MaaFWRunRecorder, MaaFWTaskRecord, format_incident_lines
from .run_report import (
    CATEGORY_REASONS,
    MaaFWAttemptReport,
    failure_summary,
    failure_summary_tasks,
    format_timeline,
    human_reason,
)

# 与任务类同一个名字：后端日志里这段流程的行照旧记在「MaaFW 插件自动代理」下
logger = get_logger("MaaFW 插件自动代理")


class MaaFWAttemptLedger:
    """一个账号这次运行的各次尝试：结构化记录、尝试结果、历史状态与附件。"""

    def __init__(self) -> None:
        #: 结构化运行记录（每次尝试一份）：worker 推的阶段 / 任务起止 + 宿主自己的阶段，
        #: 进 history 的 data 与推送里单列的原地打转 / 单任务超时。
        self.recorder = MaaFWRunRecorder()
        # 每次尝试的结构化结果：worker 回报的人话摘要、失败任务名（推送的时间线与结果行用，
        # 见 run_report）、完成清单（运行记录不可用时的退路）与失败截图。
        self._reports: list[dict[str, Any]] = []
        self._statuses: dict[int, str] = {}
        self._attachments: dict[int, list[MaaFWPlanRunAttachment]] = {}

    def call(self, action: Callable[[], Any]) -> Any:
        """运行记录是旁路：记录这一侧出了错只记后端日志、返回 None，不影响运行与收尾。"""

        try:
            return action()
        except Exception as exc:  # noqa: BLE001 - 旁路不能拖垮运行
            logger.opt(exception=True).warning(
                f"MaaFW 运行记录出错（不影响运行）: {exc}"
            )
            return None

    def begin(
        self,
        key: int,
        *,
        attempt: int,
        title: str | None,
        plan: MaaFWRunPlan | None,
    ) -> None:
        """这次尝试的结构化记录：与本次尝试的日志（history 记录）同一个键。"""

        def begin() -> None:
            self.recorder.begin_attempt(
                key,
                attempt=attempt,
                title=title or f"第 {attempt} 次尝试",
                planned=(
                    [(task.name, task_display_name(task)) for task in plan.tasks]
                    if plan is not None
                    else []
                ),
                retry_skipped=(
                    len(retry_skipped_tasks(plan)) if plan is not None else 0
                ),
            )

        self.call(begin)

    @contextmanager
    def stage(self, stage: str, *, enabled: bool = True) -> Iterator[None]:
        """宿主自己的一个阶段（运行前设置、拉起客户端）。"""

        with self.recorder.stage(stage, enabled=enabled):
            yield

    def mark_stage(self, stage: str, ok: bool | None) -> None:
        self.recorder.mark_stage(stage, ok)

    def apply_record_event(
        self, data: Any
    ) -> MaaFWTaskStartEvent | MaaFWTaskEndEvent | None:
        """worker 推来的阶段、任务起止事件归入本次尝试；返回解析出的任务事件（进度点用）。"""

        return self.call(lambda: self.recorder.apply(data))

    def current_has_success(self) -> bool:
        """当前这次尝试里有没有已经成功的任务（流程据此报告预下载资格）。"""

        record = self.recorder.current
        return record is not None and any(
            task.outcome == "succeeded" for task in record.tasks
        )

    def record(
        self,
        key: int,
        *,
        status_key: int | None,
        attempt: int,
        title: str | None,
        completed: list[str],
        failure: str | None,
        maintenance: bool,
        screenshots: list[tuple[str, Path]] | None = None,
        category: str | None = None,
        signal: str | None = None,
        user_message: str | None = None,
        failed_task: str | None = None,
    ) -> None:
        """记下本次尝试的结果，供统计通知的「任务详情」与失败截图用。

        ``status_key`` 为 None 时不记 history 状态（调用方这次尝试的日志还没有开始时刻）。
        ``maintenance`` 是这次尝试命中的信号是不是停服维护。``category`` / ``signal`` 进结构化
        运行记录；没给类别的失败由记录按任务结局补（任务都没开始是初始化失败，否则取第一个
        计入失败的任务的类别）。``user_message`` / ``failed_task`` 是 worker 回报的人话摘要与
        失败任务名，推送里的失败原因只从它们和失败类别来（``failure`` 是日志里那句，可能带
        节点链等排障细节）。
        """

        if status_key is not None:
            self._statuses[status_key] = (
                "success" if failure is None else "skipped" if maintenance else "error"
            )
        self.call(
            lambda: self.recorder.finish_attempt(
                outcome=(
                    "success"
                    if failure is None
                    else "skipped"
                    if maintenance
                    else "failed"
                ),
                category=category,
                signal=signal,
            )
        )
        self._reports.append(
            {
                "attempt": attempt,
                "title": title or f"第 {attempt} 次尝试",
                "time": datetime.now().strftime("%H:%M:%S"),
                "completed": list(completed),
                "failure": failure,
                "screenshots": list(screenshots or []),
                # 对上这次尝试的运行记录（键同 begin）
                "record_key": key,
                "user_message": user_message,
                "failed_task": failed_task,
            }
        )

    def mark_error(self, key: int) -> None:
        """崩溃收尾（``on_crash``）：这次尝试的 history 状态记成 error。"""

        self._statuses[key] = "error"

    def finish_open(self, *, stopped: bool) -> None:
        """存历史前收掉最后一次尝试：用户停止 / 崩溃时它没走到 ``record``。"""

        self.call(
            lambda: self.recorder.finish_attempt(
                outcome="stopped" if stopped else "failed",
                category=CATEGORY_USER_STOPPED if stopped else CATEGORY_HOST_ERROR,
            )
        )

    def add_attachments(
        self, key: int, items: Iterable[MaaFWPlanRunAttachment]
    ) -> None:
        """``plan_run`` 交回的附件（日志、失败截图）挂到这次尝试上。"""

        self._attachments.setdefault(key, []).extend(items)

    def history_status(self, key: int, *, stopped: bool, maintenance: bool) -> str:
        """这条 history 记录的状态：记过的照记；没记过的按停止 / 维护跳过 / 出错。"""

        status = self._statuses.get(key)
        if status is None:
            status = "cancelled" if stopped else "skipped" if maintenance else "error"
        return status

    def history_value(self, key: int) -> dict[str, Any] | None:
        """某次尝试的结构化运行记录原值（进 history 的 snapshot 统计）；没有记录返回 None。"""

        return self.recorder.history_value(key)

    def attachments(self, key: int) -> tuple[MaaFWPlanRunAttachment, ...]:
        return tuple(self._attachments.get(key, ()))

    def failure_screenshots(self, *, run_complete: bool) -> list[tuple[str, Path]]:
        """本账号要随通知发出去的失败截图（标签, 路径），按时间顺序。

        最终成功的运行不带图：任务详情那边成功时也不提前面尝试的失败，
        早先尝试的失败画面对已经跑通的一轮没有意义。张数上限由消费方裁。
        """

        if run_complete:
            return []
        shots: list[tuple[str, Path]] = []
        for report in self._reports:
            for label, path in report.get("screenshots", ()):
                shots.append((f"{report['title']} · {label}", path))
        return shots

    def incident_notice(
        self,
        *,
        run_complete: bool,
        signal_message: str | None,
        check_passed: bool,
    ) -> str:
        """本次运行里被原地打转检测或单任务时限停下的任务：进用户与脚本两份报告。

        只在最后没成功时列出；后面的重试成功了就不写，免得一份「全部完成」的报告里
        还挂着前面尝试的问题。结果行（``report_result``，代理结果里账号那一行也是它）
        已经点名的最后一次尝试的任务不列，再单列一遍就是同一件事说两次；结果行没点名的
        （比如不计入失败的任务原地打转，失败的是另一个任务）照常列出。"""

        if run_complete:
            return ""

        def notice() -> str:
            named: list[MaaFWTaskRecord] = []
            attempts = self.recorder.attempts()
            # 与 report_result 同一分支：信号或运行前检查没过时结果行不是 failure_summary
            if attempts and signal_message is None and check_passed:
                named = failure_summary_tasks(attempts[-1])
            return format_incident_lines(self.recorder.incidents(exclude=named))

        return self.call(notice) or ""

    def task_details(
        self,
        *,
        run_complete: bool,
        signal_message: str | None,
        check_passed: bool,
        missing: str,
    ) -> str:
        """账号级统计报告的任务详情：最后一次尝试的逐任务时间线（见 ``run_report``）。

        最后没成功时另起一段列结果行没点名的原地打转 / 单任务超时（每类一行），队列里有
        失效任务时末尾再附一行（``missing``，调用方给）。整次运行一个任务都没开始时没有
        时间线，原因在运行结果那行。
        """

        details = self.call(self._task_timeline)
        if details is None:
            details = self._completed_tasks_fallback(run_complete=run_complete)
        incidents = self.incident_notice(
            run_complete=run_complete,
            signal_message=signal_message,
            check_passed=check_passed,
        )
        return "\n\n".join(part for part in (details, incidents, missing) if part)

    def _attempt_outcomes(self) -> list[MaaFWAttemptReport]:
        """各次尝试的运行记录，配上 worker 回报的人话摘要与失败任务名。"""

        reports = {report.get("record_key"): report for report in self._reports}
        outcomes = []
        for key, record in self.recorder.attempt_items():
            report = reports.get(key) or {}
            outcomes.append(
                MaaFWAttemptReport(
                    record=record,
                    user_message=report.get("user_message"),
                    failed_task=report.get("failed_task"),
                )
            )
        return outcomes

    def _task_timeline(self) -> str | None:
        """逐任务时间线；没有运行记录返回 None（由调用方退回完成清单）。"""

        outcomes = self._attempt_outcomes()
        if not outcomes:
            return None
        return format_timeline(outcomes)

    def _completed_tasks_fallback(self, *, run_complete: bool) -> str:
        """运行记录出错、没有可用记录时的退路：只列完成了哪些任务，不带失败原文。"""

        reports = self._reports
        if not reports:
            return ""
        if run_complete:
            merged: list[str] = []
            for report in reports:
                for label in report["completed"]:
                    if label not in merged:
                        merged.append(label)
        else:
            merged = list(reports[-1]["completed"])
        return "已完成: " + ("、".join(merged) if merged else "无")

    def report_result(
        self,
        *,
        short: bool,
        run_complete: bool,
        missing_task_names: list[str],
        signal_message: str | None,
        check_passed: bool,
        check_status: str,
        crash_message: str | None,
    ) -> str:
        """本账号这次的结果，账号级统计报告与托管级「代理结果」同一口径。

        成功只说完成；失败说失败在哪些任务、为什么（只用人话，见 ``run_report``）；
        信号与运行前检查跳过沿用原来那句话（``check_status``：调用方日志的状态，没有日志时
        是检查结果）。``short``：托管级每个账号一行用的简短说法。
        """

        if run_complete:
            if missing_task_names:
                return MISSING_TASK_USER_RESULT
            return "全部完成" if short else "代理任务全部完成"
        if signal_message is not None:
            return signal_message
        if not check_passed:
            return check_status
        summary = self.call(lambda: failure_summary(self._attempt_outcomes()))
        if summary:
            return summary
        if crash_message is not None:
            # 还没进第一次尝试就崩了：没有运行记录，按崩溃原因说一句
            reason = (
                human_reason(crash_message) or CATEGORY_REASONS[CATEGORY_HOST_ERROR]
            )
            return f"MaaFW 运行失败：{reason}"
        return "代理任务未完成"


__all__ = ["MaaFWAttemptLedger"]
