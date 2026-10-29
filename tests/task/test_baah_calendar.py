"""BAAH 账号排期到公共活动来源和展示名称的契约。"""

import pytest

from app.models.config import BAAHUserConfig
from app.task.BAAH.calendar_service import calendar_target


@pytest.mark.parametrize(
    "line,source,label",
    [
        ("CN", "ba-cn", "国服"),
        ("JP", "ba-jp", "日服"),
        ("Globle", "ba-global", "国际服"),
    ],
)
def test_calendar_target(line, source, label):
    user = BAAHUserConfig.model_validate({"Info": {"ActivityLineType": line}})
    assert calendar_target(user) == (source, f"碧蓝档案（{label}）")
