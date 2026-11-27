"""独立 LogFlow 工具通过真实 Windows/Linux 子进程采集日志。"""

import asyncio

import pytest

from app.utils.common.log_flow.analysis import analyze_logs
from app.utils.common.log_flow.contracts import LineRule
from app.utils.common.log_flow.declaration import SimpleFlowDeclaration
from app.utils.common.log_flow.push import SubmitResult


@pytest.mark.asyncio
async def test_analysis_flushes_accepted_lines_when_the_caller_is_cancelled():
    declaration = SimpleFlowDeclaration(
        rules=(LineRule(match=r"^ready:", node_type="step", status="success"),),
    )
    started = asyncio.Event()
    finished = asyncio.Event()

    async def run() -> None:
        try:
            async with analyze_logs(declaration, accept_push=True) as analysis:
                assert analysis.reporter is not None
                started.set()
                try:
                    await finished.wait()
                finally:
                    assert (
                        analysis.reporter.text("ready: last line")
                        == SubmitResult.ACCEPTED
                    )
        finally:
            assert analysis.result is not None and analysis.result.complete
            assert [node.text for node in analysis.result.nodes] == ["ready: last line"]
            for mode in ("逐条", "汇总"):
                assert "ready: last line" in "\n".join(analysis.report_lines(mode=mode))

    task = asyncio.create_task(run())
    async with asyncio.timeout(5):
        await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
