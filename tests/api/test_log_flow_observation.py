"""调度树查询账号本次运行的最终日志分析。"""

import asyncio

import httpx
import pytest
from fastapi import FastAPI

from app.api import dispatch
from app.core import task_manager
from app.models.config import GeneralConfig
from app.models.task import TaskMode
from app.utils.common.log_flow.analysis import analyze_logs
from app.utils.common.log_flow.declaration import SimpleFlowDeclaration
from app.utils.common.log_flow.observation import NodeAttribute
from tests.support.scheduler import Builtin
from tests.support.scheduler import scheduler as scheduler


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
                await user.record_log_analysis(analysis.result)
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

        try:
            await asyncio.wait_for(first_recorded.wait(), 5)
            users = await read_users()
            analysis = users[str(first.uid)]["log_analysis"]
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
        final = users[str(second.uid)]["log_analysis"]
        assert final["nodes"][0]["text"] == second.info.name + "x" * 600
        assert ("log_analysis" in users[str(first.uid)]) is (cache_budget > 1024)
        assert (await client.get(f"/api/dispatch/task/{task_id}")).json()[
            "status"
        ] == "success"
        old = await client.get(
            f"/api/dispatch/task/{task_id}/runs/{script.uid}/log-nodes"
        )
        assert old.status_code == 404


@pytest.mark.asyncio
async def test_account_log_analysis_supports_snapshot_and_cursor_reconnect(
    scheduler, monkeypatch
):
    from contextlib import AsyncExitStack

    manager, _, _, script_id = scheduler
    monkeypatch.setattr(dispatch, "TaskManager", manager)
    app = FastAPI()
    app.include_router(dispatch.router)
    started = asyncio.Event()
    amend = asyncio.Event()
    close = asyncio.Event()

    class AnalyzingScript(Builtin):
        async def main_task(self):
            first, second = self.script_info.users.values()
            async with AsyncExitStack() as stack:
                left = await stack.enter_async_context(
                    analyze_logs(SimpleFlowDeclaration(), accept_push=True)
                )
                right = await stack.enter_async_context(
                    analyze_logs(SimpleFlowDeclaration(), accept_push=True)
                )
                first.bind_log_analysis(left)
                with pytest.raises(ValueError):
                    second.bind_log_analysis(left)
                second.bind_log_analysis(right)
                assert left.reporter is not None and right.reporter is not None
                assert (
                    left.reporter.node("step", "working", node_id="step") == "accepted"
                )
                assert (
                    left.reporter.node("step", "old", node_id="obsolete") == "accepted"
                )
                assert right.reporter.node("step", "other account") == "accepted"
                started.set()
                await amend.wait()
                assert (
                    left.reporter.node("step", "done", node_id="step", status="success")
                    == "accepted"
                )
                assert left.reporter.withdraw("obsolete") == "accepted"
                await close.wait()
            for account, analysis in ((first, left), (second, right)):
                assert analysis.result is not None
                await account.record_log_analysis(analysis.result)
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

        async def query(user, *, cursor=None, headers=None, limit=50):
            return await client.post(
                "/api/dispatch/get",
                json={
                    "taskId": str(task_id),
                    "logAnalysis": {
                        "scriptRunId": str(script.uid),
                        "userRunId": str(user.uid),
                        "cursor": cursor,
                        "limit": limit,
                    },
                },
                headers=headers,
            )

        async def page(user, *, cursor=None, limit=50):
            response = await query(user, cursor=cursor, limit=limit)
            assert response.status_code == 200, response.text
            assert response.headers["cache-control"] == "no-store"
            envelope = response.json()
            assert not envelope["data"]
            return envelope["logAnalysis"]

        try:
            await asyncio.wait_for(started.wait(), 5)
            assert (
                await query(first, headers={"Origin": "https://example.com"})
            ).status_code == 403
            assert (await query(first, limit=101)).status_code == 422
            async with asyncio.timeout(5):
                while len((snapshot := await page(first))["nodes"]) < 2:
                    await asyncio.sleep(0.01)
                while not (other := await page(second))["nodes"]:
                    await asyncio.sleep(0.01)
            assert [node["text"] for node in snapshot["nodes"]] == ["working", "old"]
            assert snapshot["closeReason"] is None
            assert [node["text"] for node in other["nodes"]] == ["other account"]
            assert (await query(second, cursor=snapshot["cursor"])).status_code == 409
            amend.set()
            async with asyncio.timeout(5):
                while not (
                    change := await page(first, cursor=snapshot["cursor"], limit=1)
                )["nodes"]:
                    await asyncio.sleep(0.01)
                while not (
                    withdrawal := await page(first, cursor=change["cursor"], limit=1)
                )["nodes"]:
                    await asyncio.sleep(0.01)
            [changed] = change["nodes"]
            [removed] = withdrawal["nodes"]
            assert changed["text"] == "done" and changed["status"] == "success"
            assert changed["node_id"] == snapshot["nodes"][0]["node_id"]
            assert changed["revision"] > snapshot["nodes"][0]["revision"]
            assert removed["withdrawn"]
            assert removed["node_id"] == snapshot["nodes"][1]["node_id"]
            assert (await page(first, cursor=snapshot["cursor"], limit=1)) == {
                **change,
                "hasMore": True,
            }
            assert (await page(first))["nodes"] == [changed]
        finally:
            amend.set()
            close.set()

        await asyncio.wait_for(run.accomplish.wait(), 5)
        complete = await page(first, cursor=withdrawal["cursor"])
        assert complete["nodes"] == []
        assert complete["closeReason"] == "complete"
        assert complete["cursor"] == withdrawal["cursor"]
        assert (await page(first))["nodes"] == [changed]

        # 变更历史已淘汰时，用最终节点重建视图。
        monkeypatch.setattr(task_manager, "_RECENT_ANALYSIS_HISTORY_BYTES", 0)
        assert (await query(first, cursor=withdrawal["cursor"])).status_code == 409
        final = await page(first)
        assert final["nodes"] == [changed]
        assert final["cursor"] is None and final["closeReason"] == "complete"
