"""调度发起的采集会话可在断线和任务结束后补读。"""

import asyncio
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api import dispatch
from app.core.log_flow.contracts import PipelineSpec, ReportedRecord
from app.core.log_flow.manager import open_for_run
from app.models.config import GeneralConfig
from app.models.task import TaskMode
from tests.support.scheduler import Builtin
from tests.support.scheduler import scheduler as scheduler


@pytest.mark.asyncio
async def test_observe_run_before_and_after_scheduler_completion(
    scheduler, monkeypatch
):
    manager, _, _, script_id = scheduler
    monkeypatch.setattr(dispatch, "TaskManager", manager)
    first_emitted = asyncio.Event()
    finish = asyncio.Event()
    app = FastAPI()
    app.include_router(dispatch.router)

    class ObservedScript(Builtin):
        async def main_task(self):
            user = next(self.script_info.users.values())
            session = await open_for_run(user, PipelineSpec(accept_push=True))
            try:
                reporter = session.push_reporter()
                assert (
                    reporter.node(
                        "error", "token=private", node_id="retry", status="failed"
                    )
                    == "accepted"
                )
                async with asyncio.timeout(3):
                    while not session.snapshot():
                        await asyncio.sleep(0.01)
                first_emitted.set()
                await finish.wait()
                assert (
                    reporter.node("success", "step two", node_id="retry") == "accepted"
                )
                assert session.submit(
                    ReportedRecord(node_type="success", text="step three")
                )
                assert reporter.withdraw("retry") == "accepted"
            finally:
                await session.close()
            await super().main_task()

    monkeypatch.setattr(manager, "manager_factories", {GeneralConfig: ObservedScript})
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://localhost"
    ) as client:
        task_id = await manager.start(
            TaskMode.AUTO_PROXY,
            {0: {"uid": "-", "children": {0: {"uid": str(script_id)}}}},
        )
        run = manager.task_handler[task_id]
        script = next(run.task_info.scripts.values())
        first_user, second_user = script.users.values()
        path = f"/api/dispatch/task/{task_id}/runs/{script.uid}/log-nodes"
        params = {"userRunId": str(first_user.uid), "limit": 1}
        try:
            await asyncio.wait_for(first_emitted.wait(), 5)
            assert (
                await client.get(
                    path, params=params, headers={"Origin": "https://example.com"}
                )
            ).status_code == 403
            assert (
                await client.get(path, params={"userRunId": str(second_user.uid)})
            ).status_code == 404
            response = await client.get(path, params=params)
            assert response.status_code == 200
            assert response.headers["Cache-Control"] == "no-store"
            page = response.json()
            assert [(node["sequence"], node["text"]) for node in page["nodes"]] == [
                (1, "token=***")
            ]
            assert page["closeReason"] is None
            assert page["nodes"][0]["revision"] == 1
            assert page["nodes"][0]["status"] == "failed"
            cursor = page["cursor"]
            assert (
                await client.get(path, params={**params, "after": 1})
            ).status_code == 409
            assert (
                await client.get(path, params={**params, "sessionId": str(uuid4())})
            ).status_code == 409
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app, client=("192.0.2.9", 1234)),
                base_url="http://localhost",
            ) as remote:
                assert (await remote.get(path, params=params)).status_code == 403
        finally:
            finish.set()
        await asyncio.wait_for(run.accomplish.wait(), 5)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://localhost"
    ) as reconnected:
        response = await reconnected.get(
            path,
            params={
                **params,
                "sessionId": cursor["sessionId"],
                "after": cursor["sequence"],
            },
        )
        assert response.status_code == 200
        page = response.json()
        assert [(node["sequence"], node["text"]) for node in page["nodes"]] == [
            (2, "step two")
        ]
        assert page["nodes"][0]["node_id"] == "push/retry"
        assert page["nodes"][0]["revision"] == 2
        assert page["nodes"][0]["status"] == "info"
        assert page["closeReason"] == "complete" and page["hasMore"] is True
        last = (
            await reconnected.get(
                path,
                params={
                    **params,
                    "sessionId": cursor["sessionId"],
                    "after": page["cursor"]["sequence"],
                    "limit": 2,
                },
            )
        ).json()
        assert [node["sequence"] for node in last["nodes"]] == [3, 4]
        assert last["nodes"][1]["node_id"] == "push/retry"
        assert last["nodes"][1]["revision"] == 3 and last["nodes"][1]["withdrawn"]
        assert [node.text for node in first_user.node_observation.snapshot()] == [
            "step three"
        ]
        assert last["hasMore"] is False
        assert (await reconnected.get(f"/api/dispatch/task/{task_id}")).json()[
            "status"
        ] == "success"
