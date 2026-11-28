"""通用配置表单不再出现已弃用的托管「执行会话」字段。"""

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api import scripts_router
from app.config import ConfigCollection
from app.core import Config
from app.models.config import GeneralConfig

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def scripts(monkeypatch, isolated_app_paths):
    collection = ConfigCollection.build(
        [GeneralConfig],
        keep_unknown_types=True,
        file=Config.config_path / "scripts.yaml",
    )
    monkeypatch.setattr(Config, "ScriptConfig", collection)
    await collection.activate()
    app = FastAPI()
    app.include_router(scripts_router)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test/api/"
    ) as client:
        yield collection, client


async def test_detail_hints_omit_deprecated_execution_session(scripts):
    collection, client = scripts
    uid = collection.add(
        GeneralConfig, payload={"Run": {"ExecutionSession": "desktop"}}
    )
    await collection.commit()

    response = await client.post("scripts/get", json={"scriptId": str(uid)})
    response.raise_for_status()
    body = response.json()

    run_fields = [hint["field"] for hint in body["ui"]["hints"].get("Run", [])]
    assert run_fields, "Run 组的其他字段仍应出现在表单里"
    assert "ExecutionSession" not in run_fields
    # 旧值保留给降级使用，只是不再渲染。
    assert body["data"][str(uid)]["Run"]["ExecutionSession"] == "desktop"
