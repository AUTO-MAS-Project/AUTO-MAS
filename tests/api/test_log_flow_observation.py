"""调度树查询账号本次运行的最终日志分析。"""

import asyncio

import httpx
import pytest
from fastapi import FastAPI

from app.api import dispatch
from app.core import task_manager
from app.core.ws import Publisher, protocol
from app.models.config import GeneralConfig
from app.models.task import TaskMode
from app.utils.common.log_flow.analysis import analyze_logs
from app.utils.common.log_flow.declaration import SimpleFlowDeclaration
from app.utils.common.log_flow.observation import NodeAttribute
from tests.support.scheduler import Builtin
from tests.support.scheduler import scheduler as scheduler


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("peer", "status"), [("::ffff:127.0.0.1", 404), ("::ffff:192.0.2.1", 403)]
)
async def test_mapped_ipv6_peer_obeys_dispatch_analysis_loopback_boundary(
    scheduler, monkeypatch, peer, status
):
    manager, _, _, _ = scheduler
    monkeypatch.setattr(dispatch, "TaskManager", manager)
    app = FastAPI()
    app.include_router(dispatch.router)
    missing_id = "00000000-0000-0000-0000-000000000001"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=(peer, 12345)),
        base_url="http://[::ffff:127.0.0.1]",
    ) as client:
        response = await client.post(
            "/api/dispatch/get",
            headers={"Origin": "http://[::ffff:127.0.0.1]"},
            json={
                "taskId": missing_id,
                "logAnalysis": {"scriptRunId": missing_id, "userRunId": missing_id},
            },
        )
    assert response.status_code == status, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("cache_budget", [1024, 16 * 1024 * 1024])
async def test_final_results_follow_account_run_in_dispatch_tree(
    scheduler, monkeypatch, cache_budget
):
    manager, _, _, script_id = scheduler
    monkeypatch.setattr(dispatch, "TaskManager", manager)
    monkeypatch.setattr(task_manager, "_RECENT_ANALYSIS_BYTES", cache_budget)
    app = FastAPI()
    app.include_router(dispatch.router)
    first_recorded = asyncio.Event()
    finish = asyncio.Event()

    class AnalyzingScript(Builtin):
        async def main_task(self):
            for user in self.script_info.users.values():
                async with analyze_logs(
                    SimpleFlowDeclaration(), accept_push=True
                ) as analysis:
                    assert analysis.reporter is not None
                    result = analysis.reporter.node(
                        "step",
                        user.info.name + "x" * 600,
                        attributes=(NodeAttribute(key="token", value="hidden"),),
                    )
                    assert result == "accepted"
                assert analysis.result is not None
                previous = Publisher.send.await_count
                await user.record_log_analysis(analysis.result)
                assert all(
                    call.kwargs.get("type") != protocol.TASK_INFO_UPDATED
                    for call in Publisher.send.await_args_list[previous:]
                )
                if user.info.name == "first":
                    first_recorded.set()
                    await finish.wait()
            await super().main_task()

    monkeypatch.setattr(manager, "manager_factories", {GeneralConfig: AnalyzingScript})
    task_id = await manager.start(
        TaskMode.AUTO_PROXY,
        {0: {"uid": "-", "children": {0: {"uid": str(script_id)}}}},
    )
    run = manager.task_handler[task_id]
    script = next(run.task_info.scripts.values())
    first, second = script.users.values()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:

        async def read_users(*, targeted=True, headers=None):
            query = {"taskId": str(task_id)} if targeted else {}
            response = await client.post(
                "/api/dispatch/get", json=query, headers=headers
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["code"] == 200
            return payload["data"][str(task_id)]["scripts"]["data"][str(script.uid)][
                "users"
            ]["data"]

        async def read_analysis(user):
            return await client.post(
                "/api/dispatch/get",
                json={
                    "taskId": str(task_id),
                    "logAnalysis": {
                        "scriptRunId": str(script.uid),
                        "userRunId": str(user.uid),
                    },
                },
            )

        try:
            await asyncio.wait_for(first_recorded.wait(), 5)
            users = await read_users()
            assert all("log_analysis" not in row for row in users.values())
            response = await read_analysis(first)
            assert response.status_code == 200
            analysis = response.json()["data"][str(task_id)]["scripts"]["data"][
                str(script.uid)
            ]["users"]["data"][str(first.uid)]["log_analysis"]
            assert analysis["close_reason"] == "complete"
            assert analysis["nodes"][0]["attributes"] == []
            assert analysis["nodes"][0]["text"] == first.info.name + "x" * 600
            assert "log_analysis" not in users[str(second.uid)]
            assert all(
                "log_analysis" not in row
                for row in (await read_users(targeted=False)).values()
            )
            remote = await read_users(headers={"Origin": "https://example.com"})
            assert all("log_analysis" not in row for row in remote.values())
            snapshot = manager.get_runtime_snapshot().model_dump(mode="json")
            assert "log_analysis" not in str(snapshot["tasks"][0]["task"])
        finally:
            finish.set()

        await asyncio.wait_for(run.accomplish.wait(), 5)
        users = await read_users()
        assert all("log_analysis" not in row for row in users.values())
        response = await read_analysis(second)
        assert response.status_code == 200
        assert (
            response.json()["data"][str(task_id)]["scripts"]["data"][str(script.uid)][
                "users"
            ]["data"][str(second.uid)]["log_analysis"]["nodes"][0]["text"]
            == second.info.name + "x" * 600
        )
        assert (await read_analysis(first)).status_code == (
            200 if cache_budget > 1024 else 404
        )
        assert (await client.get(f"/api/dispatch/task/{task_id}")).json()[
            "status"
        ] == "success"
        old = await client.get(
            f"/api/dispatch/task/{task_id}/runs/{script.uid}/log-nodes"
        )
        assert old.status_code == 404


@pytest.mark.asyncio
async def test_explicit_account_query_reads_published_live_tree(scheduler, monkeypatch):
    from app.task.log_flow.run import LogFlow
    from app.utils.common.log.flow_monitor import LogFlowMonitor

    manager, _, _, script_id = scheduler
    monkeypatch.setattr(dispatch, "TaskManager", manager)
    app = FastAPI()
    app.include_router(dispatch.router)
    amend = asyncio.Event()
    finish = asyncio.Event()

    async def display(_lines, _timestamp):
        pass

    class AnalyzingScript(Builtin):
        async def main_task(self):
            first, _ = self.script_info.users.values()

            async def run_source(_monitor):
                reporter = flow.reporter
                assert reporter is not None
                assert reporter.node("step", "working", node_id="step") == "accepted"
                assert reporter.node("step", "old", node_id="obsolete") == "accepted"
                assert reporter.node("step", "unchanged") == "accepted"
                await amend.wait()
                assert (
                    reporter.node(
                        "step",
                        "done",
                        node_id="step",
                        status="success",
                        attributes=(NodeAttribute(key="token", value="hidden"),),
                    )
                    == "accepted"
                )
                assert reporter.withdraw("obsolete") == "accepted"
                await finish.wait()

            flow = LogFlow(
                LogFlowMonitor((0, 0), "", display, source_runner=run_source),
                first,
                SimpleFlowDeclaration(),
                accept_push=True,
            )
            await flow.run()
            await super().main_task()

    monkeypatch.setattr(manager, "manager_factories", {GeneralConfig: AnalyzingScript})
    task_id = await manager.start(
        TaskMode.AUTO_PROXY,
        {0: {"uid": "-", "children": {0: {"uid": str(script_id)}}}},
    )
    run = manager.task_handler[task_id]
    script = next(run.task_info.scripts.values())
    first, second = script.users.values()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:

        async def query(*, user=None, headers=None):
            body = {"taskId": str(task_id)}
            if user is not None:
                body["logAnalysis"] = {
                    "scriptRunId": str(script.uid),
                    "userRunId": str(user.uid),
                }
            return await client.post("/api/dispatch/get", json=body, headers=headers)

        async def users(*, user=None):
            response = await query(user=user)
            assert response.status_code == 200, response.text
            if user is not None:
                assert response.headers["cache-control"] == "no-store"
            return response.json()["data"][str(task_id)]["scripts"]["data"][
                str(script.uid)
            ]["users"]["data"]

        try:
            async with asyncio.timeout(5):
                while len(first.log_analysis.nodes) < 3:
                    await asyncio.sleep(0.01)
            assert [node.text for node in first.log_analysis.nodes] == [
                "working",
                "old",
                "unchanged",
            ]
            assert all("log_analysis" not in row for row in (await users()).values())
            rows = await users(user=first)
            initial = rows[str(first.uid)]["log_analysis"]
            assert [node["text"] for node in initial["nodes"]] == [
                "working",
                "old",
                "unchanged",
            ]
            assert initial["close_reason"] is None
            assert "log_analysis" not in rows[str(second.uid)]
            assert (
                await query(user=first, headers={"Origin": "null"})
            ).status_code == 403
            assert (
                await query(user=first, headers={"Origin": "https://example.com"})
            ).status_code == 403
            other = await users(user=second)
            assert "log_analysis" not in other[str(first.uid)]
            assert not other[str(second.uid)]["log_analysis"]["nodes"]
            amend.set()
            async with asyncio.timeout(5):
                while [node.text for node in first.log_analysis.nodes] != [
                    "done",
                    "unchanged",
                ]:
                    await asyncio.sleep(0.01)
            changed, unchanged = (await users(user=first))[str(first.uid)][
                "log_analysis"
            ]["nodes"]
            assert changed["text"] == "done"
            assert changed["node_id"] == initial["nodes"][0]["node_id"]
            assert changed["revision"] > initial["nodes"][0]["revision"]
            assert changed["attributes"] == []
            assert unchanged == initial["nodes"][2]
            assert "log_analysis" not in str(
                manager.get_runtime_snapshot().model_dump(mode="json")
            )
        finally:
            amend.set()
            finish.set()

        await asyncio.wait_for(run.accomplish.wait(), 5)
        final = (await users(user=first))[str(first.uid)]["log_analysis"]
        assert final["nodes"] == [changed, unchanged]
        assert final["close_reason"] == "complete"
        assert all("log_analysis" not in row for row in (await users()).values())
