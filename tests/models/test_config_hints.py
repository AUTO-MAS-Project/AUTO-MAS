"""配置公共提示推导：数值边界及现有元数据顺序行为。"""

import json
from typing import Annotated, Optional

import pytest
from annotated_types import Ge, Gt, Le, Lt
from pydantic import BaseModel, Field, TypeAdapter

from app.config.fields.hints import ComponentHint, hint_for_field


class NumericFields(BaseModel):
    ge_zero: int = Field(ge=0)
    le_zero: int = Field(le=0)
    ge_positive: int = Field(ge=5)
    ge_negative: int = Field(ge=-5)
    le_positive: int = Field(le=5)
    le_negative: int = Field(le=-5)
    zero_range: int = Field(ge=0, le=0)
    optional_ge_zero: Optional[int] = Field(default=None, ge=0)
    optional_le_zero: int | None = Field(default=None, le=0)
    annotated_ge_zero: Annotated[int, Field(ge=0)]
    annotated_le_zero: Annotated[int, Field(le=0)]
    unconstrained: int
    optional_unconstrained: int | None = None
    gt_zero: int = Field(gt=0)
    lt_zero: int = Field(lt=0)
    gt_positive: int = Field(gt=5)
    gt_negative: int = Field(gt=-5)
    lt_positive: int = Field(lt=5)
    lt_negative: int = Field(lt=-5)
    last_lower_strict: Annotated[int, Ge(5), Gt(1)]
    last_lower_inclusive: Annotated[int, Gt(5), Ge(1)]
    last_upper_strict: Annotated[int, Le(-5), Lt(-1)]
    last_upper_inclusive: Annotated[int, Lt(-5), Le(-1)]


@pytest.mark.parametrize(
    ("field_name", "expected_bounds"),
    [
        pytest.param("ge_zero", {"min": 0}, id="ge_zero"),
        pytest.param("le_zero", {"max": 0}, id="le_zero"),
        pytest.param("ge_positive", {"min": 5}, id="ge_positive"),
        pytest.param("ge_negative", {"min": -5}, id="ge_negative"),
        pytest.param("le_positive", {"max": 5}, id="le_positive"),
        pytest.param("le_negative", {"max": -5}, id="le_negative"),
        pytest.param("zero_range", {"min": 0, "max": 0}, id="zero_range"),
        pytest.param("optional_ge_zero", {"min": 0}, id="optional_ge_zero"),
        pytest.param("optional_le_zero", {"max": 0}, id="optional_le_zero"),
        pytest.param("annotated_ge_zero", {"min": 0}, id="annotated_ge_zero"),
        pytest.param("annotated_le_zero", {"max": 0}, id="annotated_le_zero"),
        pytest.param("unconstrained", {}, id="unconstrained"),
        pytest.param("optional_unconstrained", {}, id="optional_unconstrained"),
        # 严格边界仍沿用 min/max；本次不新增严格性契约。
        pytest.param("gt_zero", {"min": 0}, id="gt_zero"),
        pytest.param("lt_zero", {"max": 0}, id="lt_zero"),
        pytest.param("gt_positive", {"min": 5}, id="gt_positive"),
        pytest.param("gt_negative", {"min": -5}, id="gt_negative"),
        pytest.param("lt_positive", {"max": 5}, id="lt_positive"),
        pytest.param("lt_negative", {"max": -5}, id="lt_negative"),
        # 保持按元数据顺序覆盖，不在零值修复中改为取最强约束。
        pytest.param("last_lower_strict", {"min": 1}, id="last_lower_strict"),
        pytest.param("last_lower_inclusive", {"min": 1}, id="last_lower_inclusive"),
        pytest.param("last_upper_strict", {"max": -1}, id="last_upper_strict"),
        pytest.param("last_upper_inclusive", {"max": -1}, id="last_upper_inclusive"),
    ],
)
def test_numeric_field_hints(field_name: str, expected_bounds: dict[str, int]):
    hint = hint_for_field(field_name, NumericFields.model_fields[field_name])
    expected = {"field": field_name, "component": "number", **expected_bounds}

    for actual in (
        hint,
        json.loads(json.dumps(hint)),
        json.loads(TypeAdapter(ComponentHint).dump_json(hint)),
    ):
        assert actual == expected
        for key in expected_bounds:
            assert type(actual[key]) in (int, float)
