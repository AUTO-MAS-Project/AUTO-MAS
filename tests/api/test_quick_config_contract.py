"""快速配置开关经过真实请求和响应模型后仍保留，General 不暴露此能力。"""

import asyncio
import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import scripts
from app.models import config, schema


@pytest.mark.parametrize(
    "prefix", ["Maa", "M9A", "Src", "MaaFW", "MaaEnd", "Okww", "OkNte", "BetterGI"]
)
@pytest.mark.parametrize("quick", [False, True])
def test_quick_config_api_roundtrip(monkeypatch, prefix, quick):
    sid, uid = uuid.uuid4(), uuid.uuid4()
    script_config = getattr(config, f"{prefix}Config")()
    user_config = getattr(config, f"{prefix}UserConfig")()
    asyncio.run(user_config.set("Info", "IfQuickConfig", quick))
    monkeypatch.setattr(scripts.Config, "ScriptConfig", {sid: script_config})
    monkeypatch.setattr(
        scripts.Config,
        "get_user",
        AsyncMock(return_value=([], {str(uid): asyncio.run(user_config.toDict())})),
    )
    update = AsyncMock()
    monkeypatch.setattr(scripts.Config, "update_user", update)
    app = FastAPI()
    app.add_api_route("/get", scripts.get_user, methods=["POST"])
    app.add_api_route("/update", scripts.update_user, methods=["POST"])
    ids = {"scriptId": str(sid), "userId": str(uid)}
    with TestClient(app) as client:
        response = client.post("/get", json=ids).json()
        assert response["code"] == 200
        assert response["data"][str(uid)]["Info"]["IfQuickConfig"] is quick
        response = client.post(
            "/update", json={**ids, "data": {"Info": {"IfQuickConfig": quick}}}
        ).json()
        assert response["code"] == 200
    update.assert_awaited_once_with(
        str(sid), str(uid), {"Info": {"IfQuickConfig": quick}}
    )
    assert "IfQuickConfig" not in schema.GeneralUserConfig_Info.model_fields
