import unittest

from app.tools.miyoushe_coin import build_miyoushe_coin_task_plan


class MiyousheCoinTaskPlanTest(unittest.TestCase):
    def test_builds_confirmed_tasks_in_fixed_order(self) -> None:
        missions = [
            {
                "mission_key": "share_post_0",
                "name": "分享帖子",
                "points": 10,
                "threshold": 1,
            },
            {
                "mission_key": "unknown_task",
                "name": "未知任务",
                "points": 99,
                "threshold": 9,
            },
            {
                "mission_key": "continuous_sign",
                "name": "讨论区签到",
                "points": 30,
                "threshold": 1,
            },
            {
                "mission_key": "view_post_0",
                "name": "阅读帖子",
                "points": 10,
                "threshold": 3,
            },
            {
                "mission_key": "post_up_0",
                "name": "点赞帖子",
                "points": 10,
                "threshold": 5,
            },
        ]
        states = [
            {"mission_key": "continuous_sign", "happened_times": 1},
            {"mission_key": "view_post_0", "happened_times": 1},
            {"mission_key": "post_up_0", "happened_times": 4},
            {"mission_key": "share_post_0", "happened_times": 0},
        ]

        plan = build_miyoushe_coin_task_plan(missions, states)

        self.assertEqual(
            [task.key for task in plan],
            [
                "continuous_sign",
                "view_post_0",
                "post_up_0",
                "share_post_0",
            ],
        )
        self.assertEqual([task.remaining for task in plan], [0, 2, 1, 1])

    def test_rejects_generic_or_malformed_progress_fields(self) -> None:
        missions = [
            {
                "mission_key": "view_post_0",
                "name": "阅读帖子",
                "points": 10,
                "threshold": 3,
            }
        ]

        with self.assertRaisesRegex(ValueError, "happened_times"):
            build_miyoushe_coin_task_plan(
                missions,
                [{"mission_key": "view_post_0", "progress": 2}],
            )


if __name__ == "__main__":
    unittest.main()
