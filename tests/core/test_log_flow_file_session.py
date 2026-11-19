"""用真实文件和进程守住实时可见、尾部冲刷及超时释放。"""

import asyncio
import builtins
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import aiofiles
import psutil
import pytest
from auto_mas_core.log_flow import SubmitResult

from app.core.log_flow.contracts import (
    MAX_HOST_PENDING_BYTES,
    MAX_NATIVE_PENDING_RECORDS,
    MAX_NODE_FRAMES,
    WORKER_MESSAGE,
    Failed,
    FileInput,
    FunctionRef,
    LineRule,
    Observed,
    PipelineSpec,
    ProcessorFactorySpec,
    ReportedRecord,
    TextRecord,
    WindowRule,
    WorkerFactorySpec,
)
from app.core.log_flow.declaration import GeneralFlowDeclaration, SimpleFlowDeclaration
from app.core.log_flow.manager import open_for_run
from app.core.log_flow.ownership import FlowOwner
from app.core.log_flow.report import render_node_details
from app.core.log_flow.session import LogFlowSession, SessionOpenError
from app.core.log_flow.simple import (
    open_custom_flow,
    open_simple_flow,
)
from app.core.notify.report import render_aggregate_push_log, render_scatter_push_log
from app.models.log_flow import InvalidObservationCursor
from app.models.task import TaskUserItem
from app.task.MaaEnd.push_log import (
    MAAEND_PUSH_RULES,
    maaend_plain_text,
    maaend_resolve,
)
from app.task.OkNte.push_log import OKNTE_PUSH_RULES, oknte_resolve
from app.utils.common.log.monitor import LogMonitor
from app.utils.common.log.sources import LogSource
from app.utils.common.log_box import LogEntry, LogPipeline


def append(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8") as file:
        file.write(text)


def pipeline(path: Path, *, match: str = "done:") -> PipelineSpec:
    return PipelineSpec(
        file=FileInput(path=str(path)),
        rules=(LineRule(match=match, extract=r"$(done:(\d+))", node_type="success"),),
    )


async def wait_for_first_node(session: LogFlowSession) -> None:
    async with asyncio.timeout(5):
        while not session.snapshot():
            await asyncio.sleep(0.01)


def test_file_rotation_between_path_check_and_open(tmp_path, monkeypatch):
    path = tmp_path / "script.log"
    path.write_bytes(b"history: before this session\n")
    source = LogSource(path, strict_io=True)
    source.open()
    with path.open("ab") as file:
        file.write(b"old tail\n")
    original_open = builtins.open

    def rotate_before_open(file, *args, **kwargs):
        if file == path:
            monkeypatch.setattr(builtins, "open", original_open)
            path.rename(path.with_suffix(".bak"))
            path.write_bytes(b"new head\n")
        return original_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", rotate_before_open)
    assert source.read_new() == ["old tail", "new head"]
    with path.open("ab") as file:
        file.write(b"new tail\n")
    assert source.read_new() == ["new tail"]


def test_script_can_rotate_while_source_holds_read_handle(tmp_path, monkeypatch):
    path = tmp_path / "script.log"
    path.write_bytes(b"old tail\n")
    source = LogSource(path, strict_io=True, start_from_end=False)
    source.open()
    original_fstat = os.fstat

    def rotate_open_file(fd):
        monkeypatch.setattr(os, "fstat", original_fstat)
        path.rename(path.with_suffix(".bak"))
        path.write_bytes(b"new head\n")
        return original_fstat(fd)

    monkeypatch.setattr(os, "fstat", rotate_open_file)
    assert source.read_new() == ["old tail"]
    assert source.read_new() == ["new head"]


@pytest.mark.asyncio
async def test_declared_preprocessor_keeps_maaend_rich_text_report_compatible():
    legacy = LogPipeline()
    legacy.preprocessors.append(maaend_plain_text)
    legacy.postprocessors.append(maaend_resolve)
    for rule in MAAEND_PUSH_RULES:
        legacy.add_rule(*rule)
    module = maaend_plain_text.__module__
    declaration = SimpleFlowDeclaration(
        rules=tuple(
            LineRule(match=match, extract=extract, node_type="普通")
            for match, extract in MAAEND_PUSH_RULES
        ),
        preprocess=FunctionRef(
            name="probe:plain", module=module, attribute="maaend_plain_text"
        ),
        postprocess=FunctionRef(
            name="probe:report", module=module, attribute="maaend_resolve"
        ),
    )
    lines = [
        "<span>[2026-11-19 09:01:02.345] 任务开始: 🎁补给</span>",
        "<span>[2026-11-19 09:01:03.456] 路线 1：样本采集失败</span>",
        "<span>[2026-11-19 09:01:04.567] 任务失败: 🎁补给</span>",
    ]
    run = TaskUserItem()
    async with open_custom_flow(
        declaration, run=run, accept_push=True, mode="汇总"
    ) as flow:
        assert flow.reporter is not None
        for line in lines:
            legacy.feed(line, timestamp=1.0)
            assert flow.reporter.text(line, timestamp=1.0) == SubmitResult.ACCEPTED
    observation = run.node_observation
    assert observation is not None and observation.summary is not None
    summary = observation.summary
    assert summary.complete
    expected = legacy.finish()
    assert len(expected) == 1 and "样本" in expected[0].text
    assert summary.report_entries == tuple(
        (entry.log_type, entry.text, entry.timestamp) for entry in expected
    )
    assert render_node_details(summary, mode="逐条") == render_scatter_push_log(
        expected
    )


@pytest.mark.asyncio
async def test_file_session_streams_and_closes_with_final_complete_lines(tmp_path):
    path = tmp_path / "script.log"
    append(path, "done:99\n")
    session = await LogFlowSession.open(pipeline(path))
    process = psutil.Process(session.pid)
    try:
        append(path, "done:1\n")
        await wait_for_first_node(session)
        assert [node.text for node in session.snapshot()] == ["1"]

        # 轮转旧文件留下未读的完整行，新文件留下半行。
        append(path, "done:2\n")
        path.rename(path.with_suffix(".bak"))
        append(path, "done:3\ndone:4")
        first, second = await asyncio.gather(session.close(), session.close())
        assert first == second
        assert first.reason == "complete"
        assert [(node.sequence, node.text) for node in first.nodes] == [
            (1, "1"),
            (2, "2"),
            (3, "3"),
        ]
        await asyncio.to_thread(process.wait, timeout=1)
    finally:
        await session.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "launcher_denied",
    [
        False,
        pytest.param(
            True,
            marks=pytest.mark.skipif(
                sys.platform != "win32", reason="使用 Windows Job 回收"
            ),
        ),
    ],
)
async def test_stuck_worker_is_reaped_and_keeps_already_observed_nodes(
    tmp_path, monkeypatch, launcher_denied
):
    path = tmp_path / "script.log"
    session = await LogFlowSession.open(pipeline(path))
    process = psutil.Process(session.pid)
    if launcher_denied:

        def deny_launcher_kill():
            raise PermissionError("启动器拒绝终止")

        monkeypatch.setattr(session._process, "kill", deny_launcher_kill)
    try:
        append(path, "done:1\n")
        await wait_for_first_node(session)
        observed = session.snapshot()
        process.suspend()
        append(path, "done:2\n")
        async with asyncio.timeout(3):
            close = asyncio.create_task(session.close(timeout=0.2))
            await asyncio.sleep(0.02)  # 宿主循环仍能执行，不必等待 worker。
            assert not close.done()
            close.cancel()
            with pytest.raises(asyncio.CancelledError):
                await close
            summary = await session.close(timeout=20)
        assert summary.reason == "timeout"
        assert summary.nodes == session.snapshot() == observed
        assert "worker 退出未确认" not in summary.detail
        await asyncio.to_thread(process.wait, timeout=1)
    finally:
        await session.close(timeout=0)


@pytest.mark.asyncio
async def test_invalid_rule_prevents_worker_readiness(tmp_path):
    with pytest.raises(SessionOpenError, match="unterminated subpattern"):
        await LogFlowSession.open(pipeline(tmp_path / "script.log", match="("))


@pytest.mark.asyncio
async def test_repeated_start_cancellation_keeps_worker_registered(
    tmp_path, monkeypatch
):
    pid_path = tmp_path / "worker.pid"
    run = TaskUserItem()
    owner = FlowOwner(lambda: True)
    stopping = asyncio.Event()
    release_stop = asyncio.Event()
    terminate = LogFlowSession._terminate_worker

    async def pause_before_termination(session):
        stopping.set()
        await release_stop.wait()
        return await terminate(session)

    monkeypatch.setattr(LogFlowSession, "_terminate_worker", pause_before_termination)
    spec = PipelineSpec(
        source=WorkerFactorySpec(
            factory=FunctionRef(
                name="probe:start",
                module="tests.support.log_flow_functions",
                attribute="blocking_start_source",
            ),
            options={"pid_path": str(pid_path)},
        )
    )

    async def start():
        async with owner.open(run, spec):
            pytest.fail("worker 启动尚未完成")

    starting = asyncio.create_task(start())
    closing = None
    try:
        async with asyncio.timeout(5):
            while not pid_path.exists() or not (pid := pid_path.read_text()).strip():
                await asyncio.sleep(0.01)
        process = psutil.Process(int(pid))
        starting.cancel()
        await asyncio.wait_for(stopping.wait(), 3)
        starting.cancel()
        closing = asyncio.create_task(owner.close())
        await asyncio.wait({starting, closing}, timeout=0.05)
        assert owner.has_workers and not closing.done()

        release_stop.set()
        with pytest.raises(asyncio.CancelledError):
            await starting
        await asyncio.wait_for(closing, 3)
        await asyncio.to_thread(process.wait, timeout=2)
        assert not owner.has_workers
        assert run.node_observation is not None
        assert run.node_observation.summary is not None
        assert not run.node_observation.summary.complete
    finally:
        release_stop.set()
        starting.cancel()
        await asyncio.gather(starting, return_exceptions=True)
        if closing is not None:
            await asyncio.gather(closing, return_exceptions=True)


@pytest.mark.asyncio
async def test_custom_processor_releases_resources_after_a_processing_error(tmp_path):
    marker = tmp_path / "released.txt"
    session = await LogFlowSession.open(
        PipelineSpec(
            accept_push=True,
            processor=ProcessorFactorySpec(
                factory=FunctionRef(
                    name="probe:prefix",
                    module="tests.support.log_flow_functions",
                    attribute="prefix_processor",
                ),
                options={"prefix": "", "release_marker": str(marker)},
            ),
        )
    )
    try:
        reporter = session.push_reporter()
        assert reporter.text("done:first") == SubmitResult.ACCEPTED
        assert reporter.text("crash") == SubmitResult.ACCEPTED
        summary = await session.close()
        assert summary.reason == "worker_error"
        assert [node.text for node in summary.nodes] == ["first"]
        assert marker.read_text(encoding="utf-8") == "released"
    finally:
        await session.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("component", ["processor", "source", "sink"])
async def test_worker_closes_extensions_with_a_partial_open_failure(
    tmp_path, component
):
    marker = tmp_path / "lifecycle.txt"
    factory = WorkerFactorySpec(
        factory=FunctionRef(
            name="probe:initializer",
            module="tests.support.log_flow_functions",
            attribute="sample_sink" if component == "sink" else "failing_initializer",
        ),
        options={"path": str(marker), "mode": "fail_open"},
    )
    run = TaskUserItem()
    rules = SimpleFlowDeclaration(
        processor=factory if component == "processor" else None
    )
    async with open_custom_flow(
        rules,
        run=run,
        mode="关闭",
        accept_push=True,
        source=factory if component == "source" else None,
        sink=factory if component == "sink" else None,
    ) as flow:
        assert flow.reporter is not None
        submitted = flow.reporter.node("普通", "valid observation")
        assert submitted == (
            SubmitResult.ACCEPTED if component == "sink" else SubmitResult.CLOSED
        )
    observation = run.node_observation
    assert observation is not None and observation.summary is not None
    summary = observation.summary
    if component == "sink":
        assert summary.complete and summary.sink_error == "open: RuntimeError"
        assert [node.text for node in summary.nodes] == ["valid observation"]
        assert marker.read_text(encoding="utf-8").splitlines()[1:] == ["closed"]
    else:
        assert summary.reason == "worker_error" and not summary.nodes
        assert marker.read_text(encoding="utf-8").splitlines() == ["opened", "closed"]


@pytest.mark.asyncio
async def test_unavailable_worker_does_not_prevent_execution_inside_flow():
    run = TaskUserItem()
    reports = []
    declaration = SimpleFlowDeclaration(rules=(LineRule(match="(", node_type="普通"),))
    async with open_custom_flow(
        declaration,
        run=run,
        mode="汇总",
        receive_report=reports.append,
        accept_push=True,
    ) as flow:
        assert flow.read_nodes().close_reason == "worker_error"
        assert flow.reporter is not None
        assert flow.reporter.node("普通", "no worker") == SubmitResult.CLOSED
        await run.set_state(status="完成")

    assert run.info.status == "完成"
    assert reports == [["⚠️ 节点采集不完整"]]


@pytest.mark.asyncio
@pytest.mark.parametrize("rotation", ["none", "recreated", "between_files"])
async def test_large_file_backlog_drains_in_batches_through_close(tmp_path, rotation):
    path = tmp_path / "script.log"
    append(path, "done:9\nprevious run: ")
    start = await FileInput(path=str(path)).capture_start()
    padding = ("x" * 8192 + "\n") * 140
    suffix = "x" * (2 * 1024 * 1024) if rotation == "between_files" else ""
    append(path, f"done:999{suffix}\ndone:1\n{padding}done:2\n")
    if rotation != "none":
        path.rename(path.with_suffix(".bak"))
    if rotation == "recreated":
        append(path, "done:3\n")

    spec = pipeline(path).model_copy(update={"file": start})
    session = await LogFlowSession.open(spec)
    try:
        summary = await session.close()
        assert summary.complete, summary.detail
        assert [node.text for node in summary.nodes] == (
            ["1", "2", "3"] if rotation == "recreated" else ["1", "2"]
        )
    finally:
        await session.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("accept_push", [False, True])
async def test_file_backlog_reports_an_incomplete_session(tmp_path, accept_push):
    path = tmp_path / "script.log"
    spec = pipeline(path).model_copy(update={"accept_push": accept_push})
    session = await LogFlowSession.open(spec)
    try:
        append(path, "done:1\n")
        await wait_for_first_node(session)
        # 单行也可能超过预算；不能把它一直当作尚未闭合的尾部并声称完整。
        append(path, "x" * (2 * 1024 * 1024))
        expected = ["1"]
        if accept_push:
            reporter = session.push_reporter()
            for text in ("2", "3"):
                assert reporter.node("普通", text) == SubmitResult.ACCEPTED
                expected.append(text)
        summary = await session.close()
        assert summary.reason == "capacity"
        assert [node.text for node in summary.nodes] == expected
        assert render_node_details(summary, mode="汇总") == [
            *expected,
            "⚠️ 节点采集不完整",
        ]
        assert render_node_details(summary, mode="关闭") == []
    finally:
        await session.close()


def test_worker_keeps_over_budget_node_out_of_pipe_if_sink_cleanup_fails(tmp_path):
    path = tmp_path / "session.log"
    path.write_bytes(b"done:1\n" * (MAX_NODE_FRAMES + 1))
    sink_log = tmp_path / "sink.log"
    spec = PipelineSpec(
        file=FileInput(path=str(path), start_from_end=False),
        rules=(LineRule(match="^done:", node_type="普通"),),
        sink=WorkerFactorySpec(
            factory=FunctionRef(
                name="probe:sink",
                module="tests.support.log_flow_functions",
                attribute="sample_sink",
            ),
            options={"path": str(sink_log), "mode": "fail_close"},
        ),
    )
    worker = subprocess.run(
        [sys.executable, "-m", "app.core.log_flow.worker"],
        input=spec.model_dump_json().encode() + b"\n",
        capture_output=True,
        timeout=10,
        check=False,
    )
    messages = [
        WORKER_MESSAGE.validate_json(frame) for frame in worker.stdout.splitlines()
    ]
    nodes = [message.node for message in messages if isinstance(message, Observed)]
    assert [node.sequence for node in nodes] == list(range(1, MAX_NODE_FRAMES + 1))
    assert sink_log.read_text(encoding="utf-8").splitlines()[-1] == "closed"
    assert isinstance(messages[-1], Failed) and messages[-1].reason == "capacity"


@pytest.mark.asyncio
async def test_mixed_session_drains_accepted_records_and_rejects_late_input(tmp_path):
    path = tmp_path / "script.log"
    file_spec = pipeline(path)
    # 两次执行可使用同一账号配置，观察信息仍按真实运行对象隔离。
    run = TaskUserItem(user_id="same")
    another_run = TaskUserItem(user_id="same")
    unrelated = another_run.open_node_observation()
    session = await open_for_run(
        run, PipelineSpec(file=file_spec.file, rules=file_spec.rules, accept_push=True)
    )
    try:
        append(path, "done:1\n")
        await wait_for_first_node(session)
        observation = run.node_observation
        assert observation is not None
        before = observation.read()
        assert [node.text for node in before.nodes] == ["1"]
        assert before.close_reason is None
        with pytest.raises(InvalidObservationCursor):
            unrelated.read(after=before.cursor)
        assert session.submit(TextRecord(text="done:2"))
        assert session.submit(
            ReportedRecord(node_type="warning", text="done:3", timestamp=123.0)
        )

        summary = await session.close()
        assert summary.complete
        assert [(node.source, node.node_type, node.text) for node in summary.nodes] == [
            ("file", "success", "1"),
            ("push", "success", "2"),
            ("push", "warning", "done:3"),
        ]
        assert not session.submit(TextRecord(text="done:4"))
        after = observation.read(after=before.cursor)
        assert after.nodes == summary.nodes[1:]
        assert after.close_reason == "complete"
        assert after.nodes[-1].timestamp == 123.0
        assert run.info.status == "等待"
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_push_returns_backpressure_without_blocking_host():
    session = await LogFlowSession.open(PipelineSpec(accept_push=True))
    process = psutil.Process(session.pid)
    try:
        process.suspend()
        reporter = session.push_reporter()
        submitted = {reporter.node("success", "x" * 8192) for _ in range(512)}
        assert submitted == {SubmitResult.ACCEPTED, SubmitResult.BACKPRESSURE}
        assert not session.snapshot()
        async with asyncio.timeout(3):
            summary = await session.close(timeout=0.2)
        assert summary.reason == "timeout"
        assert not summary.nodes
        await asyncio.to_thread(process.wait, timeout=1)
    finally:
        await session.close(timeout=0)


@pytest.mark.asyncio
async def test_native_burst_reports_dropped_input_as_incomplete():
    session = await LogFlowSession.open(
        PipelineSpec(
            accept_mas=True, rules=(LineRule(match="^step ", node_type="普通"),)
        )
    )
    try:
        receive = session.native_line_receiver()
        # 真实监控器可能在同一个事件循环轮次交接一批已经缓冲的行。
        for index in range(MAX_NATIVE_PENDING_RECORDS + 2):
            receive(f"step {index}")
        summary = await session.close()
        assert summary.reason == "capacity"
        assert [node.text for node in summary.nodes] == [
            f"step {index}" for index in range(MAX_NATIVE_PENDING_RECORDS)
        ]
        assert session.observation.read().close_reason == "capacity"
        assert render_node_details(summary, mode="汇总")[-1] == "⚠️ 节点采集不完整"
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_native_backlog_is_limited_by_bytes_when_lines_are_large():
    session = await LogFlowSession.open(
        PipelineSpec(
            accept_mas=True, rules=(LineRule(match="^observed", node_type="普通"),)
        )
    )
    try:
        receive = session.native_line_receiver()
        receive("observed")
        large_line = "a" * 60_000
        batch_size = MAX_HOST_PENDING_BYTES // len(large_line) + 2
        assert batch_size < MAX_NATIVE_PENDING_RECORDS
        for _ in range(batch_size):
            receive(large_line)
        summary = await session.close()
        assert summary.reason == "capacity"
        assert [node.text for node in summary.nodes] == ["observed"]
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_simple_flow_handles_stdout_burst_from_real_log_monitor():
    async def save_display(_lines, _latest_time):
        pass

    monitor = LogMonitor((0, 0), "", save_display)
    run = TaskUserItem()
    declaration = SimpleFlowDeclaration(
        rules=(LineRule(match="^step ", node_type="普通"),)
    )
    async with open_simple_flow(
        declaration,
        run=run,
        monitor=monitor,
        mode="关闭",
        receive_report=lambda _: None,
    ):
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            'import sys; sys.stdout.buffer.write((b"step " + b"x"*114 + b"\\n") * 1024)',
            stdout=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(monitor.monitor_process(process, "stdout"), 5)
        assert await process.wait() == 0

    observation = run.node_observation
    assert observation is not None
    assert observation.read().close_reason == "complete"
    assert len(observation.snapshot()) == 1024


@pytest.mark.asyncio
@pytest.mark.parametrize("hold_pipe_open", [False, True])
async def test_native_process_flow_drains_pipe_on_stop(monkeypatch, hold_pipe_open):
    from app.utils.common.log import monitor as monitor_module

    async def display(_lines, _latest_time):
        pass

    if hold_pipe_open:
        monkeypatch.setattr(monitor_module, "_STOP_DRAIN_SECONDS", 0.3)
    monitor = LogMonitor((0, 0), "", display)
    run = TaskUserItem()
    reports = []
    declaration = SimpleFlowDeclaration(
        rules=(LineRule(match="^done:", extract=r"$(done:(\w+))", node_type="普通"),)
    )
    async with open_simple_flow(
        declaration,
        run=run,
        monitor=monitor,
        mode="逐条",
        receive_report=reports.append,
    ) as read_nodes:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            'import sys; print("done:tail", flush=True); sys.stdin.read()',
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
        )
        assert process.stdin is not None
        try:
            if not hold_pipe_open:
                process.stdin.close()
                assert await asyncio.wait_for(process.wait(), 5) == 0
            await monitor.start_monitor_process(process)
            if hold_pipe_open:
                async with asyncio.timeout(5):
                    while not read_nodes().nodes:
                        await asyncio.sleep(0.01)
            async with asyncio.timeout(2):
                await monitor.stop()
        finally:
            process.stdin.close()
            await asyncio.wait_for(process.wait(), 5)

    page = read_nodes()
    assert [node.text for node in page.nodes] == ["tail"]
    assert page.close_reason == ("worker_error" if hold_pipe_open else "complete")
    assert reports == [["tail", *(["⚠️ 节点采集不完整"] if hold_pipe_open else [])]]


@pytest.mark.asyncio
async def test_native_stdout_skips_an_entire_oversized_line_and_reports_a_gap():
    async def display(_lines, _latest_time):
        pass

    monitor = LogMonitor((0, 0), "", display)
    run = TaskUserItem()
    reports = []
    declaration = SimpleFlowDeclaration(
        rules=(LineRule(match="^done:", extract=r"$(done:(\w+))", node_type="普通"),)
    )
    async with open_simple_flow(
        declaration,
        run=run,
        monitor=monitor,
        mode="逐条",
        receive_report=reports.append,
    ):
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            'import sys, time; out = sys.stdout.buffer; out.write(b"done:before\\n" + b"x" * 2048); '
            'out.flush(); time.sleep(.3); out.write(b"done:fragment\\ndone:after\\n"); out.flush()',
            stdout=asyncio.subprocess.PIPE,
            limit=128,
        )
        await asyncio.wait_for(monitor.monitor_process(process, "stdout"), 5)
        assert await process.wait() == 0

    assert reports == [["before", "after", "⚠️ 节点采集不完整"]]
    observation = run.node_observation
    assert observation is not None and observation.summary is not None
    assert [node.text for node in observation.snapshot()] == ["before", "after"]
    assert observation.summary.reason == "worker_error"


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_case", ["normal", "rotated", "slow_callback"])
async def test_native_file_flow_drains_last_poll_on_stop(
    tmp_path, monkeypatch, stop_case
):
    from app.utils.common.log import monitor as monitor_module

    path = tmp_path / "script.log"
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    append(path, f"{stamp} done:first\n")
    first_seen = asyncio.Event()
    slow_callback = stop_case == "slow_callback"

    async def display(lines, _latest_time):
        if lines:
            first_seen.set()
        if slow_callback and any("done:tail" in line for line in lines):
            await asyncio.Future()

    if slow_callback:
        monkeypatch.setattr(monitor_module, "_STOP_DRAIN_SECONDS", 0.3)
    monitor = LogMonitor((0, 19), "%Y-%m-%d %H:%M:%S", display)
    run = TaskUserItem()
    reports = []
    declaration = SimpleFlowDeclaration(
        rules=(LineRule(match="done:", extract=r"$(done:(\w+))", node_type="普通"),)
    )
    async with open_simple_flow(
        declaration,
        run=run,
        monitor=monitor,
        mode="逐条",
        receive_report=reports.append,
    ):
        await monitor.start_monitor_file(
            lambda: path, datetime.now() - timedelta(seconds=10)
        )
        try:
            await asyncio.wait_for(first_seen.wait(), 5)
            append(path, f"{stamp} done:tail\n{stamp} done:unfinished")
            if stop_case == "rotated":
                path.rename(path.with_suffix(".bak"))
        finally:
            await asyncio.wait_for(monitor.stop(), 2)

    observation = run.node_observation
    assert observation is not None
    assert [node.text for node in observation.snapshot()] == ["first", "tail"]
    assert observation.read().close_reason == (
        "worker_error" if slow_callback else "complete"
    )
    assert reports == [
        ["first", "tail", *(["⚠️ 节点采集不完整"] if slow_callback else [])]
    ]


@pytest.mark.asyncio
async def test_native_file_flow_keeps_incomplete_lines_until_they_are_written(tmp_path):
    path = tmp_path / "script.log"
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    append(path, f"{stamp} done:first\n{stamp} done:par")
    saw_final = asyncio.Event()
    appended = False

    async def display(lines, _latest_time):
        nonlocal appended
        if lines and not appended:
            append(path, f"tial\n{stamp} done:final\n{stamp} done:unfinished")
            appended = True
        if any("done:final" in line for line in lines):
            saw_final.set()

    monitor = LogMonitor((0, 19), "%Y-%m-%d %H:%M:%S", display)
    run = TaskUserItem()
    declaration = SimpleFlowDeclaration(
        rules=(LineRule(match="done:", extract=r"$(done:(\w+))", node_type="普通"),)
    )
    async with open_simple_flow(
        declaration,
        run=run,
        monitor=monitor,
        mode="关闭",
        receive_report=lambda _: None,
    ):
        await monitor.start_monitor_file(
            lambda: path, datetime.now() - timedelta(seconds=10)
        )
        try:
            await asyncio.wait_for(saw_final.wait(), 5)
        finally:
            await monitor.stop()

    observation = run.node_observation
    assert observation is not None
    assert [node.text for node in observation.snapshot()] == [
        "first",
        "partial",
        "final",
    ]


@pytest.mark.asyncio
async def test_native_file_monitor_does_not_replay_append_when_ctime_changes(
    tmp_path, monkeypatch
):
    path = tmp_path / "script.log"
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    append(path, f"{stamp} done:first\n")
    original_stat = Path.stat
    ctime_delta = 0
    saw_append = asyncio.Event()

    def stat_with_changed_ctime(target, *args, **kwargs):
        stat = original_stat(target, *args, **kwargs)
        if target != path:
            return stat
        fields = ["st_ino", "st_dev", "st_size", "st_mode", "st_mtime"]
        if sys.platform == "win32":
            fields.append("st_birthtime_ns")
        return SimpleNamespace(
            **{field: getattr(stat, field) for field in fields},
            st_ctime_ns=stat.st_ctime_ns + ctime_delta,
        )

    async def display(lines, _latest_time):
        nonlocal ctime_delta
        if lines and not ctime_delta:
            append(path, f"{stamp} done:second\n")
            ctime_delta = 1
        if lines and "done:second" in lines[-1]:
            saw_append.set()

    monkeypatch.setattr(Path, "stat", stat_with_changed_ctime)
    monitor = LogMonitor((0, 19), "%Y-%m-%d %H:%M:%S", display)
    run = TaskUserItem()
    flow = SimpleFlowDeclaration(
        rules=(LineRule(match="done:", extract=r"$(done:(\w+))", node_type="普通"),)
    )
    async with open_simple_flow(
        flow, run=run, monitor=monitor, mode="关闭", receive_report=lambda _: None
    ):
        await monitor.start_monitor_file(
            lambda: path, datetime.now() - timedelta(seconds=10)
        )
        try:
            await asyncio.wait_for(saw_append.wait(), 5)
        finally:
            await monitor.stop()
    assert run.node_observation is not None
    assert [node.text for node in run.node_observation.snapshot()] == [
        "first",
        "second",
    ]


@pytest.mark.asyncio
async def test_script_can_rotate_while_native_file_monitor_reads(tmp_path):
    path = tmp_path / "script.log"
    rotated = path.with_suffix(".bak")
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    append(path, f"{stamp} done:first\n")
    read = asyncio.Event()

    def roll_after_first_line(line):
        if "done:first" in line and not rotated.exists():
            path.rename(rotated)
        return line

    async def display(lines, _latest_time):
        if lines:
            read.set()

    monitor = LogMonitor(
        (0, 19), "%Y-%m-%d %H:%M:%S", display, line_hook=roll_after_first_line
    )
    await monitor.start_monitor_file(
        lambda: path, datetime.now() - timedelta(seconds=10)
    )
    try:
        await asyncio.wait_for(read.wait(), 5)
        assert rotated.is_file()
    finally:
        await monitor.stop()


@pytest.mark.asyncio
async def test_native_file_monitor_keeps_offset_when_open_races_rotation(
    tmp_path, monkeypatch
):
    path = tmp_path / "script.log"
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    append(path, f"{stamp} first\n")
    raw = []
    appended = False
    rotated = False
    read_replacement = asyncio.Event()
    original_open = aiofiles.open

    def rotate_before_open(file, *args, **kwargs):
        nonlocal rotated
        if file == path and appended and not rotated:
            rotated = True
            path.rename(path.with_suffix(".bak"))
            append(path, f"{stamp} new00\n{stamp} new01\n")
        return original_open(file, *args, **kwargs)

    async def display(lines, _latest_time):
        nonlocal appended
        if not appended and lines:
            append(path, f"{stamp} last0\n")
            appended = True
        if any("new00" in line for line in lines):
            read_replacement.set()

    monkeypatch.setattr(aiofiles, "open", rotate_before_open)
    monitor = LogMonitor((0, 19), "%Y-%m-%d %H:%M:%S", display, on_raw_line=raw.append)
    await monitor.start_monitor_file(
        lambda: path, datetime.now() - timedelta(seconds=10)
    )
    try:
        await asyncio.wait_for(read_replacement.wait(), 7)
    finally:
        await monitor.stop()
    assert [line.strip().split()[-1] for line in raw] == [
        "first",
        "last0",
        "new00",
        "new01",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "rotation", ["none", "while_away", "during_drain", "before_drain"]
)
async def test_native_file_monitor_resumes_date_path_by_identity(
    tmp_path, monkeypatch, rotation
):
    first = tmp_path / "day-one.log"
    second = tmp_path / "day-two.log"
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    append(first, f"{stamp} first\n")
    append(second, f"{stamp} other\n")
    current = first
    switched_back = False
    finished = asyncio.Event()
    raw = []
    backup = first.with_suffix(".bak")
    original_open = aiofiles.open

    def write_replacement():
        append(first, f"{stamp} new00\n{stamp} new01\n")

    def rotate_during_open(file, *args, **kwargs):
        if (
            rotation == "during_drain"
            and file == first
            and current == second
            and not backup.exists()
        ):
            first.rename(backup)
            write_replacement()
        return original_open(file, *args, **kwargs)

    async def display(lines, _latest_time):
        nonlocal current, switched_back
        if not lines:
            return
        tail = lines[-1].split()[-1]
        if tail == "first" and not switched_back:
            if rotation in ("during_drain", "before_drain"):
                append(first, f"{stamp} last0\n")
            if rotation == "before_drain":
                first.rename(backup)
            current = second
        elif tail == "other" and not switched_back:
            if rotation in ("none", "while_away"):
                append(first, f"{stamp} last0\n")
            if rotation == "while_away":
                first.rename(backup)
            if rotation in ("while_away", "before_drain"):
                write_replacement()
            current = first
            switched_back = True
        elif tail == ("last0" if rotation == "none" else "new01"):
            finished.set()

    monkeypatch.setattr(aiofiles, "open", rotate_during_open)
    monitor = LogMonitor((0, 19), "%Y-%m-%d %H:%M:%S", display, on_raw_line=raw.append)
    await monitor.start_monitor_file(
        lambda: current, datetime.now() - timedelta(seconds=10)
    )
    try:
        await asyncio.wait_for(finished.wait(), 7)
    finally:
        await monitor.stop()
    expected = (
        ["first", "last0", "other"]
        if rotation in ("during_drain", "before_drain")
        else ["first", "other", "last0"]
    )
    if rotation != "none":
        expected.extend(("new00", "new01"))
    assert [line.split()[-1] for line in raw] == expected


@pytest.mark.asyncio
async def test_webui_notifications_keep_general_log_time_prefix():
    async def discard_display(_lines, _latest_time):
        pass

    monitor = LogMonitor((0, 8), "%H:%M:%S", discard_display)
    run = TaskUserItem()
    declaration = GeneralFlowDeclaration(
        patterns=json.dumps(
            [
                {
                    "type": "regex",
                    "match": "done:",
                    "extract": r'"✅ 成功: " + $(done:(\w+))',
                }
            ]
        )
    )
    lines = ["09:15:37 done:timed", "no clock done:untimed"]
    async with open_custom_flow(declaration, run=run, monitor=monitor, mode="汇总"):
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "import sys; sys.stdout.buffer.write(bytes.fromhex(sys.argv[1]))",
            ("\n".join(lines) + "\n").encode().hex(),
            stdout=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(monitor.monitor_process(process, "stdout"), 5)
        assert await process.wait() == 0

    observation = run.node_observation
    assert observation is not None and observation.summary is not None
    summary = observation.summary
    assert summary.complete
    expected = [
        LogEntry("普通", "09:15 - ✅ 成功: timed"),
        LogEntry("普通", "✅ 成功: untimed"),
    ]
    assert [node.text for node in summary.nodes] == [entry.text for entry in expected]
    assert render_node_details(summary, mode="逐条") == render_scatter_push_log(
        expected
    )
    assert render_node_details(summary, mode="汇总") == render_aggregate_push_log(
        expected
    )


@pytest.mark.asyncio
async def test_report_consumes_current_nodes_after_correction_and_withdrawal():
    run = TaskUserItem()
    async with open_custom_flow(
        SimpleFlowDeclaration(), run=run, accept_push=True, mode="汇总"
    ) as flow:
        reporter = flow.reporter
        assert reporter is not None
        assert (
            reporter.node("失败", "❌ 失败: step", node_id="step")
            == SubmitResult.ACCEPTED
        )
        assert (
            reporter.node("普通", "✅ 成功: step", node_id="step")
            == SubmitResult.ACCEPTED
        )
        assert (
            reporter.node("普通", "discard", node_id="discard") == SubmitResult.ACCEPTED
        )
        async with asyncio.timeout(5):
            while (snapshot := flow.snapshot_nodes()).cursor.sequence < 3:
                await asyncio.sleep(0.01)
        assert snapshot.close_reason is None
        assert [node.text for node in snapshot.nodes] == ["✅ 成功: step", "discard"]
        assert reporter.withdraw("discard") == SubmitResult.ACCEPTED
        assert reporter.withdraw("invalid/key") == SubmitResult.INVALID

    latest = flow.snapshot_nodes()
    delta = flow.read_nodes(after=snapshot.cursor)
    assert latest.close_reason == delta.close_reason == "complete"
    assert latest.cursor == delta.cursor
    assert len(delta.nodes) == 1 and delta.nodes[0].withdrawn
    assert delta.nodes[0].node_id == "push/discard"
    assert len(latest.nodes) == 1 and latest.nodes[0].status == "success"
    observation = run.node_observation
    assert observation is not None and observation.summary is not None
    summary = observation.summary
    assert summary.nodes == latest.nodes
    assert render_node_details(summary, mode="逐条") == ["✅ 成功: step"]
    assert render_node_details(summary, mode="汇总") == ["✅ 成功: step"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("order", "postprocess", "expected"),
    [
        ("first_seen", None, ["A2", "B"]),
        ("last_updated", None, ["B", "A2"]),
        (
            "last_updated",
            FunctionRef(name="probe:copy", module="builtins", attribute="list"),
            ["B", "A2"],
        ),
    ],
)
async def test_report_order_is_independent_of_observation(order, postprocess, expected):
    run = TaskUserItem()
    declaration = SimpleFlowDeclaration(report_order=order, postprocess=postprocess)
    async with open_custom_flow(
        declaration, run=run, accept_push=True, mode="汇总"
    ) as flow:
        assert flow.reporter is not None
        for key, text in [("a", "A1"), ("b", "B"), ("a", "A2")]:
            assert (
                flow.reporter.node("普通", text, node_id=key) is SubmitResult.ACCEPTED
            )

    assert [node.text for node in flow.snapshot_nodes().nodes] == ["A2", "B"]
    assert [node.text for node in flow.read_nodes().nodes] == ["A1", "B", "A2"]
    observation = run.node_observation
    assert observation is not None and observation.summary is not None
    assert render_node_details(observation.summary, mode="汇总") == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("逐条", [["✅ 成功: 7", "✅ 成功: 8"]]),
        ("汇总", [["✅ 成功: 7, 8"]]),
        ("关闭", []),
    ],
)
async def test_default_flow_shares_live_nodes_and_delivers_selected_report(
    mode, expected
):
    declaration = SimpleFlowDeclaration(
        rules=(LineRule(match="^✅ 成功:", node_type="普通"),),
        windows=(
            WindowRule(
                start="^BEGIN", end="^END", extract='"✅ 成功: 8"', node_type="普通"
            ),
        ),
        postprocess=(
            FunctionRef(
                name="sample:report",
                module="tests.support.log_flow_functions",
                attribute="disabled_report",
            )
            if mode == "关闭"
            else None
        ),
    )
    run = TaskUserItem(user_id="test")
    display: list[str] = []
    reports: list[list[str]] = []

    async def save_display(lines, latest_time):
        display[:] = lines

    monitor = LogMonitor(
        (0, 0),
        "",
        save_display,
        line_hook=lambda line: "显示已改写" if line else None,
    )
    async with open_simple_flow(
        declaration, run=run, monitor=monitor, mode=mode, receive_report=reports.append
    ) as read_nodes:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "import sys; sys.stdout.buffer.write('✅ 成功: 7\\nBEGIN\\n'.encode('utf-8'))",
            stdout=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(monitor.monitor_process(process, "stdout"), 5)
        assert await process.wait() == 0
        assert display and all(line == "显示已改写" for line in display)
        async with asyncio.timeout(5):
            while not (page := read_nodes()).nodes:
                await asyncio.sleep(0.01)
        observation = run.node_observation
        assert observation is not None
        assert page == observation.read()
        assert [(node.source, node.text) for node in page.nodes] == [
            ("mas", "✅ 成功: 7")
        ]
        assert page.close_reason is None
        assert reports == []
    assert reports == expected
    assert monitor.on_raw_line is None
    closed = read_nodes(after=page.cursor)
    assert closed.close_reason == "complete"
    assert [node.text for node in closed.nodes] == ["✅ 成功: 8"]


@pytest.mark.asyncio
async def test_simple_flow_can_replace_only_the_text_processor():
    declaration = SimpleFlowDeclaration(
        processor=ProcessorFactorySpec(
            factory=FunctionRef(
                name="example:prefix",
                module="tests.support.log_flow_functions",
                attribute="prefix_processor",
            ),
            options={"prefix": "✅ 成功: "},
        )
    )
    run = TaskUserItem(user_id="test")
    reports: list[list[str]] = []

    async def display(_lines, _latest_time):
        pass

    monitor = LogMonitor((0, 0), "", display)
    async with open_simple_flow(
        declaration,
        run=run,
        monitor=monitor,
        mode="汇总",
        receive_report=reports.append,
    ) as read_nodes:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "print('done:7'); print('done:8')",
            stdout=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(monitor.monitor_process(process, "stdout"), 5)
        assert await process.wait() == 0
        async with asyncio.timeout(5):
            while len((page := read_nodes()).nodes) < 2:
                await asyncio.sleep(0.01)
        assert run.node_observation is not None
        assert page == run.node_observation.read()
        assert [(node.source, node.text) for node in page.nodes] == [
            ("mas", "✅ 成功: 7"),
            ("mas", "✅ 成功: 8"),
        ]
        assert reports == []
    assert [node.text for node in read_nodes(after=page.cursor).nodes] == ["合计: 2"]
    assert reports == [["✅ 成功: 7, 8", "合计: 2"]]


@pytest.mark.asyncio
async def test_custom_flow_keeps_all_sources_bound_to_one_run(tmp_path):
    path = tmp_path / "script.log"
    path.write_text("done:old\n", encoding="utf-8")
    run = TaskUserItem(user_id="same")
    other = TaskUserItem(user_id="same")

    async def display(_lines, _latest_time):
        pass

    monitor = LogMonitor((0, 0), "", display)
    reports = []
    async with open_custom_flow(
        SimpleFlowDeclaration(rules=(LineRule(match="^done:", node_type="普通"),)),
        run=run,
        mode="逐条",
        receive_report=reports.append,
        file=FileInput(path=str(path)),
        monitor=monitor,
        accept_push=True,
    ) as flow:
        reporter = flow.reporter
        assert reporter is not None
        assert reporter.node("", "invalid") == SubmitResult.INVALID
        assert reporter.text("汉" * 25000) == SubmitResult.TOO_LARGE
        assert reporter.node("普通", "from push") == SubmitResult.ACCEPTED
        append(path, "done:file\n")
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-c", "print('done:mas')", stdout=asyncio.subprocess.PIPE
        )
        await asyncio.wait_for(monitor.monitor_process(process, "stdout"), 5)
        assert await process.wait() == 0
    async with open_custom_flow(
        SimpleFlowDeclaration(),
        run=other,
        mode="关闭",
        receive_report=reports.append,
        accept_push=True,
    ) as next_flow:
        assert reporter.node("普通", "late") == SubmitResult.CLOSED
        assert next_flow.reporter is not None
        assert next_flow.reporter.node("普通", "next run") == SubmitResult.ACCEPTED
    assert [n.text for n in next_flow.read_nodes().nodes] == ["next run"]
    page = flow.read_nodes()
    assert page.close_reason == "complete"
    assert {(n.source, n.text) for n in page.nodes} == {
        ("file", "done:file"),
        ("mas", "done:mas"),
        ("push", "from push"),
    }
    assert run.node_observation is not None and run.node_observation.read() == page
    assert len(reports) == 1 and len(reports[0]) == 3


@pytest.mark.asyncio
async def test_push_rejects_timestamp_that_cannot_be_rendered():
    reports: list[list[str]] = []
    async with open_custom_flow(
        SimpleFlowDeclaration(),
        run=TaskUserItem(),
        mode="逐条",
        receive_report=reports.append,
        accept_push=True,
    ) as flow:
        reporter = flow.reporter
        assert reporter is not None
        milliseconds = 1_764_000_000_000
        assert reporter.node("普通", "invalid time", timestamp=milliseconds) == (
            SubmitResult.INVALID
        )
        assert reporter.text("invalid time", timestamp=milliseconds) == (
            SubmitResult.INVALID
        )
        timestamp = datetime(2026, 11, 19, 10, 4).timestamp()
        assert reporter.node("普通", "valid time", timestamp=timestamp) == (
            SubmitResult.ACCEPTED
        )

    assert flow.read_nodes().close_reason == "complete"
    assert reports == [["10:04 - valid time"]]


@pytest.mark.asyncio
async def test_custom_flow_delivers_report_when_execution_raises():
    run = TaskUserItem()
    reports: list[list[str]] = []
    execution_error = RuntimeError("script failed")
    with pytest.raises(RuntimeError) as failure:
        async with open_custom_flow(
            SimpleFlowDeclaration(),
            run=run,
            mode="逐条",
            receive_report=reports.append,
            accept_push=True,
        ) as flow:
            assert flow.reporter is not None
            assert (
                flow.reporter.node("普通", "node before failure")
                == SubmitResult.ACCEPTED
            )
            raise execution_error

    assert failure.value is execution_error
    assert flow.read_nodes().close_reason == "complete"
    assert reports == [["node before failure"]]


@pytest.mark.asyncio
async def test_repeated_execution_cancellation_delivers_frozen_report(tmp_path):
    run = TaskUserItem()
    owner = FlowOwner(lambda: True)
    sink_log = tmp_path / "sink.txt"
    module = "tests.support.log_flow_functions"
    reports: list[list[str]] = []
    submitted = asyncio.Event()

    async def execute():
        async with open_custom_flow(
            SimpleFlowDeclaration(
                postprocess=FunctionRef(
                    name="sample:report", module=module, attribute="sample_report"
                )
            ),
            run=run,
            mode="汇总",
            receive_report=reports.append,
            accept_push=True,
            sink=WorkerFactorySpec(
                factory=FunctionRef(
                    name="sample:sink", module=module, attribute="sample_sink"
                ),
                options={"path": str(sink_log), "mode": "block_close"},
            ),
            owner=owner,
        ) as flow:
            assert flow.reporter is not None
            assert flow.reporter.node("普通", "collected") == SubmitResult.ACCEPTED
            submitted.set()
            await asyncio.Future()

    execution = asyncio.create_task(execute())
    try:
        async with asyncio.timeout(8):
            await submitted.wait()
            execution.cancel()
            while "closing\n" not in sink_log.read_text(encoding="utf-8"):
                await asyncio.sleep(0.01)
            execution.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.shield(execution)

        assert execution.cancelled()
        assert reports == [["sample report", "⚠️ 节点采集不完整"]]
        assert run.node_observation is not None
        assert run.node_observation.read().close_reason == "timeout"
        assert not owner.has_workers
    finally:
        if not execution.done():
            execution.cancel()
        await owner.close()
        await asyncio.gather(execution, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["ok", "fail", "block", "block_close"])
async def test_worker_extensions_keep_observation_independent_of_sink(tmp_path, mode):
    path = tmp_path / "sink.txt"
    module = "tests.support.log_flow_functions"
    session = await LogFlowSession.open(
        PipelineSpec(
            source=WorkerFactorySpec(
                factory=FunctionRef(
                    name="sample:source", module=module, attribute="sample_source"
                )
            ),
            sink=WorkerFactorySpec(
                factory=FunctionRef(
                    name="sample:sink", module=module, attribute="sample_sink"
                ),
                options={"path": str(path), "mode": mode},
            ),
            rules=(LineRule(match="^done:", node_type="普通"),),
            postprocess=FunctionRef(
                name="sample:report", module=module, attribute="sample_report"
            ),
        )
    )
    try:
        await wait_for_first_node(session)
        assert [(n.source, n.text) for n in session.snapshot()] == [
            ("custom", "done:sample")
        ]
        summary = await session.close(timeout=0.2 if mode == "block" else 2)
        lines = path.read_text(encoding="utf-8").splitlines()
        assert lines[0] == f"pid:{session.pid}" and session.pid != os.getpid()
        if mode == "block":
            assert summary.reason == "timeout"
            assert [n.text for n in summary.nodes] == ["done:sample"]
            assert summary.requires_final_report
            assert render_node_details(summary, mode="汇总") == [
                "done:sample",
                "⚠️ 节点采集不完整",
            ]
            assert render_node_details(summary, mode="关闭") == []
        elif mode == "block_close":
            assert summary.reason == "timeout"
            assert [n.text for n in summary.nodes] == ["done:sample", "source tail"]
            assert render_node_details(summary, mode="汇总") == [
                "sample report",
                "⚠️ 节点采集不完整",
            ]
            assert "closed" not in lines
        else:
            assert summary.complete
            assert [n.text for n in summary.nodes] == ["done:sample", "source tail"]
            assert render_node_details(summary, mode="汇总") == ["sample report"]
            assert lines[1:] == (
                ["custom:done:sample", "custom:source tail", "closed"]
                if mode == "ok"
                else ["closed"]
            )
            assert summary.sink_error == (
                "write: RuntimeError" if mode == "fail" else ""
            )
    finally:
        await session.close(timeout=0)


@pytest.mark.asyncio
async def test_close_flushes_each_sources_unfinished_window(tmp_path):
    path = tmp_path / "script.log"
    session = await LogFlowSession.open(
        PipelineSpec(
            file=FileInput(path=str(path)),
            accept_push=True,
            windows=(
                WindowRule(
                    start="begin", extract=r"$(item:(\d+))", node_type="success"
                ),
            ),
        )
    )
    try:
        append(path, "begin\nitem:1\n")
        assert session.submit(TextRecord(text="begin"))
        assert session.submit(TextRecord(text="item:2"))
        summary = await session.close()
        assert summary.complete
        assert {(node.source, node.text) for node in summary.nodes} == {
            ("file", "1"),
            ("push", "2"),
        }
    finally:
        await session.close(timeout=0)


@pytest.mark.asyncio
async def test_custom_expression_function_executes_in_worker():
    session = await LogFlowSession.open(
        PipelineSpec(
            accept_push=True,
            functions=(
                FunctionRef(
                    name="sample:pid",
                    module="tests.support.log_flow_functions",
                    attribute="report_worker_pid",
                ),
            ),
            rules=(
                LineRule(match="^test$", extract="$().sample:pid()", node_type="info"),
            ),
        )
    )
    try:
        assert session.submit(TextRecord(text="test"))
        summary = await session.close()
        assert summary.complete
        assert [node.text for node in summary.nodes] == [str(session.pid)]
        assert session.pid != os.getpid()
    finally:
        await session.close(timeout=0)


@pytest.mark.asyncio
async def test_oknte_shadow_report_matches_legacy_aggregation():
    lines = [
        "任务失败: 日常领取",
        "无法找到活跃度奖励领取框",
        "任务完成: 周本",
        "info_set skipped ['清扫']",
        "当前体力 120",
        "共计消耗体力: 60",
    ]
    legacy = LogPipeline()
    for rule in OKNTE_PUSH_RULES:
        legacy.add_rule(*rule)
    legacy.postprocessors.append(oknte_resolve)
    timestamps = [1_750_000_000.0 + index * 60 for index in range(len(lines))]
    for line, timestamp in zip(lines, timestamps, strict=True):
        legacy.feed(line, timestamp=timestamp)

    session = await LogFlowSession.open(
        PipelineSpec(
            accept_push=True,
            rules=tuple(
                LineRule(match=rule[0], extract=rule[1], node_type="普通")
                for rule in OKNTE_PUSH_RULES
            ),
            postprocess=FunctionRef(
                name="oknte:report",
                module=oknte_resolve.__module__,
                attribute=oknte_resolve.__name__,
            ),
        )
    )
    try:
        for line, timestamp in zip(lines, timestamps, strict=True):
            assert session.submit(TextRecord(text=line, timestamp=timestamp))
        summary = await session.close()
        assert summary.complete
        old_entries = legacy.finish()
        assert summary.report_entries == tuple(
            (entry.log_type, entry.text, entry.timestamp) for entry in old_entries
        )
        assert render_node_details(summary, mode="逐条") == render_scatter_push_log(
            old_entries
        )
        assert render_node_details(summary, mode="汇总") == [
            "✅ 成功: 周本",
            "⏭ 跳过: 日常领取（当日已领取）, 清扫",
            "⚡ 剩余体力: 60",
        ]
    finally:
        await session.close(timeout=0)
