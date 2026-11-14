import pytest

from app.tools.common.community.providers import skland as _tool_skland


@pytest.mark.parametrize(
    "payload",
    [
        {"code": 10001, "message": "attendance already completed"},
        {"code": 1, "message": "请勿重复签到！"},
        {"code": 1, "message": "Please do not sign in again!"},
    ],
)
def test_already_signed_responses(payload):
    assert _tool_skland.is_skland_already_signed(payload)
