"""用真实文件和进程守住实时可见、尾部冲刷及超时释放。"""

import asyncio
import json
import os
import sys
from pathlib import Path

import psutil
import pytest
from auto_mas_core.log_flow import SubmitResult

from app.core.log_flow.contracts import (
    MAX_HOST_PENDING_BYTES,
    MAX_NATIVE_PENDING_RECORDS,
    FileInput,
    FunctionRef,
    LineRule,
    PipelineSpec,
    ProcessorFactorySpec,
    ReportedRecord,
    TextRecord,
    WindowRule,
    WorkerFactorySpec,
)
from app.core.log_flow.manager import open_for_run
from app.core.log_flow.report import render_node_details
from app.core.log_flow.session import LogFlowSession, SessionOpenError
from app.core.log_flow.simple import (
    SimpleFlowDeclaration,
    open_custom_flow,
    open_simple_flow,
)
from app.core.notify.report import render_scatter_push_log
from app.models.log_flow import InvalidObservationCursor
from app.models.task import TaskUserItem
from app.task.OkNte.push_log import OKNTE_PUSH_RULES, oknte_resolve
from app.utils.common.log.monitor import LogMonitor
from app.utils.common.log_box import LogPipeline


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
async def test_stuck_worker_is_reaped_and_keeps_already_observed_nodes(tmp_path):
    path = tmp_path / "script.log"
    session = await LogFlowSession.open(pipeline(path))
    process = psutil.Process(session.pid)
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
async def test_file_backlog_reports_an_incomplete_session(tmp_path):
    path = tmp_path / "script.log"
    session = await LogFlowSession.open(pipeline(path))
    try:
        append(path, "done:1\n")
        await wait_for_first_node(session)
        # 单行也可能超过预算；不能把它一直当作尚未闭合的尾部并声称完整。
        append(path, "x" * (2 * 1024 * 1024))
        summary = await session.close()
        assert summary.reason == "capacity"
        assert [node.text for node in summary.nodes] == ["1"]
        assert render_node_details(summary, mode="汇总") == ["1", "⚠️ 节点采集不完整"]
        assert render_node_details(summary, mode="关闭") == []
    finally:
        await session.close()


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
async def test_report_consumes_current_nodes_after_correction_and_withdrawal():
    session = await LogFlowSession.open(PipelineSpec(accept_push=True))
    try:
        reporter = session.push_reporter()
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
        assert reporter.withdraw("discard") == SubmitResult.ACCEPTED
        assert reporter.withdraw("invalid/key") == SubmitResult.INVALID
        summary = await session.close()
        assert summary.complete
        assert render_node_details(summary, mode="逐条") == ["✅ 成功: step"]
        assert render_node_details(summary, mode="汇总") == ["✅ 成功: step"]
        assert summary.nodes[0].status == "success"
        assert len(session.observation.read().nodes) == 4
    finally:
        await session.close(timeout=0)


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
@pytest.mark.parametrize("mode", ["ok", "fail", "block"])
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


@pytest.mark.asyncio
async def test_general_webui_rules_share_legacy_hook_and_match_order():
    session = await LogFlowSession.open(
        PipelineSpec(
            accept_push=True,
            general_hooks=json.dumps(
                [
                    {"type": "drop", "match": "^noise"},
                    {
                        "type": "replace",
                        "match": "token=\\w+",
                        "replace": "token=hidden",
                    },
                ]
            ),
            general_patterns=json.dumps(
                [
                    {
                        "type": "regex",
                        "match": ".+",
                        "extract": '"停用"',
                        "enabled": False,
                    },
                    {
                        "type": "regex",
                        "match": "redacted",
                        "extract": r"$(token=(\w+))",
                    },
                    {"type": "split", "match": "redacted"},
                ]
            ),
        )
    )
    try:
        assert session.submit(TextRecord(text="noise redacted token=discarded"))
        assert session.submit(TextRecord(text="redacted token=secret"))
        summary = await session.close()
        assert summary.complete
        assert [node.text for node in summary.nodes] == ["hidden"]
    finally:
        await session.close(timeout=0)
