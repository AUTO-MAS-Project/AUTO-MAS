import unittest
from unittest.mock import patch

from app.core.community_activity import (
    build_configured_community_activity_failures,
)
from app.tools.community import (
    CommunityActivityTarget,
    build_community_activity_requests,
    parse_community_activity_snapshot,
)
from app.tools.community_activity_roles import normalize_skland_roles


class _FakeAccount:
    def __init__(self, values: dict[str, object]) -> None:
        self.values = values

    def get(self, section: str, name: str) -> object:
        if section != "GameSignAccount":
            raise KeyError(section)
        return self.values.get(name, "")


class CommunityActivityRoleTest(unittest.TestCase):
    def test_direct_binding_list_keeps_games_isolated(self) -> None:
        payload = {
            "data": {
                "bindingList": [
                    {
                        "uid": "arknights-uid",
                        "nickName": "Doctor",
                        "channelName": "官服",
                    },
                    {
                        "userId": "endfield-user",
                        "roles": [
                            {
                                "roleId": "endfield-role",
                                "serverId": "1",
                                "nickname": "管理员",
                            }
                        ],
                    },
                ]
            }
        }

        discovery = normalize_skland_roles(payload)

        self.assertEqual(
            [(role.game, role.role_uid) for role in discovery.roles],
            [("明日方舟", "arknights-uid"), ("终末地", "endfield-role")],
        )


class CommunityActivityFailureTest(unittest.TestCase):
    def test_global_failure_keeps_five_game_cards(self) -> None:
        account = _FakeAccount(
            {
                "Enabled": True,
                "Name": "用户 1",
                "SklandToken": "skland-token",
                "MiyousheToken": "miyoushe-token",
            }
        )

        with patch(
            "app.core.community_activity._selected_accounts",
            return_value=(("account", account),),
        ):
            snapshots = build_configured_community_activity_failures()

        self.assertEqual(
            [(snapshot.platform, snapshot.game) for snapshot in snapshots],
            [
                ("森空岛", "明日方舟"),
                ("森空岛", "终末地"),
                ("米游社", "原神"),
                ("米游社", "星穹铁道"),
                ("米游社", "绝区零"),
            ],
        )
        self.assertTrue(
            all(snapshot.status == "failed" for snapshot in snapshots)
        )


class CommunityActivityRequestTest(unittest.TestCase):
    def test_skland_request_contracts(self) -> None:
        arknights = CommunityActivityTarget(
            account_uid="account",
            account_name="用户 1",
            platform="森空岛",
            game="明日方舟",
            role_uid="arknights-uid",
        )
        endfield = CommunityActivityTarget(
            account_uid="account",
            account_name="用户 1",
            platform="森空岛",
            game="终末地",
            role_uid="endfield-role",
            server="1",
            user_id="must-not-enter-query",
        )

        arknights_request = build_community_activity_requests(
            arknights, timestamp=123456
        )[0]
        endfield_request = build_community_activity_requests(endfield)[0]

        self.assertEqual(
            arknights_request.query,
            {"uid": "arknights-uid", "ts": "123456"},
        )
        self.assertTrue(
            endfield_request.source.endswith(
                "/web/v1/game/endfield/card/detail"
            )
        )
        self.assertEqual(
            endfield_request.query,
            {"roleId": "endfield-role", "serverId": "1"},
        )
        self.assertEqual(
            endfield_request.header_map["sk-game-role"],
            "3_endfield-role_1",
        )

    def test_zzz_note_contract(self) -> None:
        target = CommunityActivityTarget(
            account_uid="account",
            account_name="用户 1",
            platform="米游社",
            game="绝区零",
            role_uid="10000001",
            server="prod_gf_cn",
        )

        request = build_community_activity_requests(target)[0]

        self.assertTrue(
            request.source.endswith("/event/game_record_zzz/api/zzz/note")
        )
        self.assertEqual(
            request.query,
            {"role_id": "10000001", "server": "prod_gf_cn"},
        )
        self.assertTrue(request.requires_device_fingerprint)


class CommunityActivityParserTest(unittest.TestCase):
    def parse(self, game: str, payload: object, *, platform: str):
        return parse_community_activity_snapshot(
            payload,
            account_uid="account",
            account_name="用户 1",
            platform=platform,
            game=game,
            role={
                "roleId": "role",
                "name": "角色",
                "serverName": "服务器",
            },
        )

    def test_arknights_and_endfield_progress(self) -> None:
        arknights = self.parse(
            "明日方舟",
            {
                "code": 0,
                "data": {
                    "currentTs": 1360,
                    "routine": {
                        "daily": {"current": 8, "total": 10},
                        "weekly": {"current": 20, "total": 100},
                    },
                    "status": {
                        "ap": {
                            "current": 20,
                            "max": 135,
                            "lastApAddTime": 1000,
                        }
                    },
                },
            },
            platform="森空岛",
        )
        endfield = self.parse(
            "终末地",
            {
                "code": 0,
                "data": {
                    "detail": {
                        "dailyActivation": 100,
                        "maxDailyActivation": 100,
                        "dungeon": {"curStamina": 80, "maxStamina": 240},
                    }
                },
            },
            platform="森空岛",
        )

        self.assertEqual((arknights.completed, arknights.target), (8, 10))
        self.assertEqual(arknights.resources[0]["current"], 21)
        self.assertEqual((endfield.completed, endfield.target), (100, 100))
        self.assertEqual(endfield.resources[0]["current"], 80)

    def test_miyoushe_three_game_progress(self) -> None:
        genshin = self.parse(
            "原神",
            {
                "retcode": 0,
                "data": {
                    "finished_task_num": 4,
                    "total_task_num": 4,
                    "current_resin": 120,
                    "max_resin": 200,
                },
            },
            platform="米游社",
        )
        hsr = self.parse(
            "星穹铁道",
            {
                "retcode": 0,
                "data": {
                    "current_training_score": 300,
                    "max_training_score": 500,
                    "current_stamina": 120,
                    "max_stamina": 300,
                },
            },
            platform="米游社",
        )
        zzz = self.parse(
            "绝区零",
            {
                "retcode": 0,
                "data": {
                    "energy": {
                        "progress": {"current": 180, "max": 240},
                        "restore": 3600,
                    },
                    "vitality": {"current": 320, "max": 400},
                    "vhs_sale": {"sale_state": "SaleStateDoing"},
                    "card_sign": "CardSignDone",
                },
            },
            platform="米游社",
        )

        self.assertEqual((genshin.completed, genshin.target), (4, 4))
        self.assertEqual((hsr.completed, hsr.target), (300, 500))
        self.assertEqual((zzz.completed, zzz.target), (320, 400))
        self.assertEqual(zzz.resources[0]["current"], 180)

    def test_non_json_is_reported_as_limited_without_decoder_details(self) -> None:
        snapshot = self.parse("原神", "<html>blocked</html>", platform="米游社")

        self.assertEqual(snapshot.status, "limited")
        self.assertNotIn("JSONDecodeError", snapshot.reason)
        self.assertIn("非 JSON", snapshot.reason)


if __name__ == "__main__":
    unittest.main()
