from app.core.config import AppConfig


def test_parse_maaend_pull_count_statistics_from_focus_output() -> None:
    logs = [
        "资源折算：43 抽\n",
        "可留到下版本的券：3 抽\n",
        "下版本商店：5 抽\n",
        "下版本签到：5 抽\n",
        "当前池可用：46 抽\n",
        "下版本池子总计：56 抽\n",
    ]

    result = AppConfig.parse_maaend_pull_count_statistics(None, logs)

    assert result == {
        "resource_pulls": 43,
        "carry_over_pulls": 3,
        "next_pool_shop_pulls": 5,
        "next_pool_signin_pulls": 5,
        "current_pool_total": 46,
        "next_pool_total": 56,
    }


def test_parse_maaend_pull_count_statistics_from_structured_agent_log() -> None:
    logs = [
        'result={"ResourcePulls":43,"CarryToNextPulls":3,'
        '"NextPoolShopPulls":5,"NextPoolSigninPulls":5,'
        '"CurrentPoolTotal":46,"NextPoolTotal":56} '
        'message="pull count calculated"\n'
    ]

    result = AppConfig.parse_maaend_pull_count_statistics(None, logs)

    assert result is not None
    assert result["current_pool_total"] == 46
    assert result["next_pool_total"] == 56


def test_parse_maaend_pull_count_statistics_requires_complete_result() -> None:
    result = AppConfig.parse_maaend_pull_count_statistics(None, ["当前池可用：46 抽\n"])

    assert result is None
