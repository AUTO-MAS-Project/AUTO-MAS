"""日历装配迁移后，脚本列表仍返回原有的游戏活动归属。"""

from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.scripts import management


def test_script_list_keeps_activity_games_after_host_extraction(monkeypatch):
    expected = {
        "MaaConfig": "arknights",
        "MaaEndConfig": "endfield",
        "SrcConfig": "starrail",
        "HSRConfig": "starrail",
        "BetterGIConfig": "genshin",
        "ZzzOdConfig": "zenless",
        "OkwwConfig": "wutheringwaves",
        "OkNteConfig": "nte",
        "M9AConfig": "reverse1999",
        "BAAHConfig": "bluearchive",
        "MSSConfig": "stellasora",
        "WhimboxConfig": "infinitynikki",
        "GeneralConfig": None,
        "MaaFWConfig": None,
    }
    index = [{"uid": config, "type": config} for config in expected]
    monkeypatch.setattr(
        management.Config, "get_script", AsyncMock(return_value=(index, {}))
    )
    app = FastAPI()
    app.include_router(management.router, prefix="/api/scripts")
    with TestClient(app) as client:
        response = client.post("/api/scripts/get", json={})
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert {item["type"]: item["activityGame"] for item in data["index"]} == expected
