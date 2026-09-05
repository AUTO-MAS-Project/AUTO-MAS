from types import SimpleNamespace

from app.tools.push_log import build_user_result_text
from app.utils.LogPatternExtractor import LOG_TYPE_ERROR, LOG_TYPE_NORMAL


def test_build_user_result_text_keeps_each_user_detail_with_result() -> None:
    users = [
        SimpleNamespace(
            name="甲",
            result="完成",
            push_log=[(LOG_TYPE_NORMAL, "节点甲")],
        ),
        SimpleNamespace(
            name="乙",
            result="异常",
            push_log=[(LOG_TYPE_ERROR, "失败详情")],
        ),
    ]

    assert build_user_result_text(users, has_uncompleted=True) == (
        "甲: 完成\n节点甲\n\n乙: 异常\n失败详情"
    )


def test_build_user_result_text_hides_failure_details_when_all_completed() -> None:
    users = [
        SimpleNamespace(
            name="甲",
            result="完成",
            push_log=[(LOG_TYPE_ERROR, "失败详情")],
        )
    ]

    assert build_user_result_text(users, has_uncompleted=False) == "甲: 完成"
