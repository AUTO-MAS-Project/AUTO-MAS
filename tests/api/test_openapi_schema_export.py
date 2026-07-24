"""离线 OpenAPI 导出契约测试。"""

from __future__ import annotations

import warnings
from pathlib import Path

from scripts.export_openapi_schema import build_openapi_schema


def test_offline_schema_contains_current_emulator_operation_contract() -> None:
    with warnings.catch_warnings(record=True) as captured_warnings:
        warnings.simplefilter("always")
        schema = build_openapi_schema()

    operation = schema["paths"]["/api/emulator/operate"]["post"]
    response_schema = operation["responses"]["200"]["content"]["application/json"][
        "schema"
    ]

    assert response_schema["$ref"] == "#/components/schemas/EmulatorOperateOut"
    assert "/api/plugins/reload_instance" in schema["paths"]
    assert "/api/script-types/get" in schema["paths"]
    assert not any(
        "Duplicate Operation ID" in str(warning.message)
        for warning in captured_warnings
    )


def test_offline_schema_export_is_independent_of_callers_working_directory(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    schema = build_openapi_schema()

    assert "/api/emulator/operate" in schema["paths"]
