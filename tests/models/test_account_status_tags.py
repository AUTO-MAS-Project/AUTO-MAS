"""账号结果颜色与普通配置标签的显示契约。"""

import json

import pytest

from app.models.config import BetterGIUserConfig, OkNteUserConfig, OkwwUserConfig


@pytest.mark.parametrize(
    "config_type", [OkwwUserConfig, OkNteUserConfig, BetterGIUserConfig]
)
@pytest.mark.parametrize("status,color", [("失败", "red"), ("成功", "green")])
def test_last_result_color(config_type, status, color):
    config = config_type.model_validate({"Data": {"LastProxyStatus": status}})
    tags = json.loads(config.getTags())
    assert tags[0]["color"] == color


def test_ordinary_account_details_use_neutral_color():
    config = OkNteUserConfig.model_validate(
        {"Info": {"RemainedDay": -1, "Notes": "无"}}
    )
    tags = json.loads(config.getTags())
    assert tags[-2]["color"] == "default"
    assert tags[-1]["color"] == "default"
