from __future__ import annotations

from scripts.export_openapi_schema import build_openapi_schema


def test_offline_openapi_contains_game_center_contract() -> None:
    schema = build_openapi_schema()
    expected = {
        "/api/game_center/get",
        "/api/game_center/add",
        "/api/game_center/update",
        "/api/game_center/delete",
        "/api/game_center/order",
        "/api/game_center/providers",
        "/api/game_center/presets",
        "/api/game_center/check",
        "/api/game_center/install",
        "/api/game_center/cancel",
        "/api/game_center/task_status",
        "/api/game_center/launch",
        "/api/game_center/close",
    }
    assert expected.issubset(schema["paths"])
    assert "/api/game_center/update_game" not in schema["paths"]

    response = schema["paths"]["/api/game_center/get"]["post"]["responses"]["200"]
    assert response["content"]["application/json"]["schema"]["$ref"].endswith(
        "/GameGetOut"
    )

    components = schema["components"]["schemas"]
    assert components["GameActionIn"]["required"] == [
        "gameId",
        "expectedRevision",
    ]
    assert components["GameTaskCancelIn"]["required"] == [
        "gameId",
        "expectedRevision",
        "expectedTaskId",
    ]
    status_values = components["GameTaskStatusOut"]["properties"]["taskStatus"][
        "anyOf"
    ][0]["enum"]
    assert "handed_off" in status_values
    phase_schema = components["GameTaskStatusOut"]["properties"]["phase"]
    phase_values = next(
        item["enum"]
        for item in phase_schema.get("anyOf", [phase_schema])
        if "enum" in item
    )
    assert "awaiting_user" in phase_values
    assert "" not in phase_values
