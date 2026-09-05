import unittest

from app.tools.taygedo import (
    TAYGEDO_GAME_IDS,
    _format_community_reward,
    _format_taygedo_rewards,
)


class TaygedoRewardContractTest(unittest.TestCase):
    def test_only_confirmed_game_ids_are_queried(self) -> None:
        self.assertEqual(TAYGEDO_GAME_IDS, ("1256", "1289"))

    def test_formats_reward_for_the_requested_day(self) -> None:
        payload = {
            "items": [
                {"day": 2, "name": "环石", "num": 30},
                {"day": 3, "goodsName": "异环币", "quantity": 5},
            ]
        }

        self.assertEqual(_format_taygedo_rewards(payload, 2), "异环币×5")

    def test_ignores_unconfirmed_reward_shapes(self) -> None:
        self.assertEqual(
            _format_taygedo_rewards(
                {"items": [{"title": "未知奖励", "amount": 99}]},
                0,
            ),
            "",
        )

    def test_formats_confirmed_community_reward_fields(self) -> None:
        self.assertEqual(
            _format_community_reward({"exp": 10, "goldCoin": 5}),
            "经验10、金币5",
        )


if __name__ == "__main__":
    unittest.main()
