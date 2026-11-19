"""WebUI 多行规则预览沿用运行期的窗口边界。"""

import json

import httpx
import pytest
from fastapi import FastAPI

from app.api import setting
from app.core.log_flow.declaration import GeneralFlowDeclaration
from app.core.log_flow.push import SubmitResult
from app.core.log_flow.simple import open_custom_flow
from app.models.task import TaskUserItem


@pytest.mark.asyncio
async def test_multiline_preview_keeps_blank_lines_in_the_window():
    pattern = {"type": "multiline", "start": "^BEGIN", "end": "^END", "maxLines": 3}
    lines = ["BEGIN", " ", "part", "END", "BEGIN", "unclosed"]
    expected = ["BEGIN\n\npart", "BEGIN\nunclosed"]
    app = FastAPI()
    app.include_router(setting.router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        response = await client.post(
            "/api/setting/debug_pattern",
            json={"pattern": pattern, "logText": "\r\n".join(lines) + "\r\n"},
        )
    assert response.status_code == 200
    preview = response.json()
    assert preview["isMultiline"] and preview["configError"] is None
    extracted = [item["extracted"] for item in preview["results"] if item["hit"]]

    declaration = GeneralFlowDeclaration(patterns=json.dumps([pattern]))
    async with open_custom_flow(
        declaration, run=TaskUserItem(), mode="关闭", accept_push=True
    ) as flow:
        assert flow.reporter is not None
        for line in lines:
            assert flow.reporter.text(line + "\r\n") is SubmitResult.ACCEPTED
    snapshot = flow.snapshot_nodes()
    assert snapshot.close_reason == "complete"
    assert [node.text for node in snapshot.nodes] == expected
    assert extracted == expected
