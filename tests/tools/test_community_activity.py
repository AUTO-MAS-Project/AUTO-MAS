import asyncio
import hashlib
import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from app.core.community_activity import (
    build_configured_community_activity_failures,
)
from app.tools.community import (
    CommunityActivityTarget,
    build_community_activity_requests,
    parse_community_activity_snapshot,
)
from app.tools.community_activity_provider import (
    CommunityActivityProvider,
    _device_fp_body,
    _miyoushe_request_cookies,
)
from app.tools.community_activity_roles import normalize_skland_roles
from app.tools.community_activity_transport import (
    CommunityActivityTransportError,
)


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
        self.assertEqual(request.header_map["x-rpc-client_type"], "2")
        self.assertEqual(request.header_map["x-rpc-channel"], "mihoyo")
        self.assertEqual(
            request.header_map["Origin"], "https://act.mihoyo.com"
        )
        self.assertTrue(request.requires_device_fingerprint)

    def test_starrail_widget_is_primary_contract(self) -> None:
        target = CommunityActivityTarget(
            account_uid="account",
            account_name="用户 1",
            platform="米游社",
            game="星穹铁道",
            role_uid="10000001",
            server="prod_official_usa",
        )

        requests = build_community_activity_requests(target)

        self.assertTrue(requests[0].source.endswith("/hkrpg/aapi/widget"))
        self.assertEqual(requests[0].query, {})
        self.assertEqual(requests[0].signature_profile, "miyoushe_data")
        self.assertFalse(requests[0].requires_device_fingerprint)
        self.assertTrue(requests[1].source.endswith("/hkrpg/api/note"))

    def test_starrail_widget_matches_reference_header_contract(self) -> None:
        target = CommunityActivityTarget(
            account_uid="account",
            account_name="用户 1",
            platform="米游社",
            game="星穹铁道",
            role_uid="10000001",
            server="prod_official_usa",
        )
        request = build_community_activity_requests(target)[0]

        with patch(
            "app.tools.community_activity_provider.time.time",
            return_value=1700000000,
        ), patch(
            "app.tools.community_activity_provider.random.randint",
            return_value=123456,
        ):
            headers = CommunityActivityProvider._miyoushe_request_headers(
                request,
                device_id="device-id",
                device_fp="device-fp",
            )

        expected_hash = hashlib.md5(
            "salt=t0qEgfub6cvueAPgR5m9aQWWVciEer7v"
            "&t=1700000000&r=123456&b=&q=".encode()
        ).hexdigest()
        self.assertEqual(
            headers["DS"],
            f"1700000000,123456,{expected_hash}",
        )
        self.assertEqual(headers["x-rpc-app_version"], "2.63.1")
        self.assertEqual(headers["x-rpc-channel"], "appstore")
        self.assertEqual(headers["x-rpc-page"], "")
        self.assertEqual(headers["x-rpc-device_id"], "")
        self.assertEqual(headers["x-rpc-device_fp"], "")
        self.assertEqual(headers["x-rpc-device_model"], "iPhone10,2")
        self.assertEqual(headers["x-rpc-device_name"], "iPhone")
        self.assertEqual(headers["x-rpc-sys_version"], "16.2")
        self.assertEqual(headers["Connection"], "keep-alive")
        self.assertEqual(headers["Host"], "api-takumi-record.mihoyo.com")
        self.assertEqual(
            headers["User-Agent"],
            "WidgetExtension/231 CFNetwork/1390 Darwin/22.0.0",
        )

    def test_widget_cookie_copy_prefers_v2_stoken_without_mutation(self) -> None:
        original = {
            "stoken": "legacy-token",
            "stoken_v2": "v2-token",
            "mid": "mid-value",
        }

        request_cookies = _miyoushe_request_cookies(
            original,
            require_v2_stoken=True,
        )

        self.assertEqual(request_cookies["stoken"], "v2-token")
        self.assertNotIn("stoken_v2", request_cookies)
        self.assertEqual(original["stoken"], "legacy-token")
        self.assertEqual(original["stoken_v2"], "v2-token")

    def test_device_fp_request_receives_v2_cookie_view(self) -> None:
        client = AsyncMock()
        client.post.return_value = httpx.Response(
            200,
            json={"retcode": 0, "data": {"device_fp": "fp-value"}},
            request=httpx.Request(
                "POST", "https://public-data-api.mihoyo.com/device-fp/api/getFp"
            ),
        )
        original = {
            "stoken": "legacy-token",
            "stoken_v2": "v2-token",
            "mid": "mid-value",
        }
        request_cookies = _miyoushe_request_cookies(
            original,
            require_v2_stoken=True,
        )
        provider = CommunityActivityProvider("米游社", "placeholder")

        device_fp = asyncio.run(
            provider._acquire_device_fp(
                client,
                "device-id",
                game="绝区零",
                seed_id="11111111-2222-4333-8444-555555555555",
                cookies=request_cookies,
            )
        )

        self.assertEqual(device_fp, "fp-value")
        request_kwargs = client.post.call_args.kwargs
        self.assertEqual(request_kwargs["cookies"]["stoken"], "v2-token")
        self.assertNotIn("stoken_v2", request_kwargs["cookies"])
        self.assertEqual(original["stoken"], "legacy-token")
        self.assertEqual(original["stoken_v2"], "v2-token")

    def test_zzz_device_registration_matches_reference_name(self) -> None:
        client = AsyncMock()
        client.post.return_value = httpx.Response(
            200,
            json={"retcode": 0},
            request=httpx.Request(
                "POST", "https://bbs-api.mihoyo.com/apihub/api/deviceLogin"
            ),
        )
        provider = CommunityActivityProvider("米游社", "placeholder")

        asyncio.run(
            provider._register_device(
                client,
                device_id="device-id",
                device_fp="fp-value",
                cookies={"stoken": "v2-token"},
                game="绝区零",
            )
        )

        self.assertEqual(client.post.call_count, 2)
        for call in client.post.call_args_list:
            body = json.loads(call.kwargs["content"])
            self.assertEqual(body["device_name"], "XiaomiMI 8 SE")

    def test_widget_requires_paired_mid(self) -> None:
        target = CommunityActivityTarget(
            account_uid="account",
            account_name="用户 1",
            platform="米游社",
            game="星穹铁道",
            role_uid="10000001",
            server="prod_official_usa",
        )
        request = build_community_activity_requests(target)[0]
        provider = CommunityActivityProvider("米游社", "placeholder")

        async def run_prepare() -> None:
            await provider._prepare_miyoushe(
                request,
                object(),
                ensure_auth_aliases=lambda cookies: None,
                generate_device_id=lambda cookie: "device-id",
                parse_cookie=lambda cookie: {
                    "stuid": "10000001",
                    "stoken_v2": "v2-token",
                },
                validate_cookie=lambda cookie: None,
            )

        with self.assertRaises(CommunityActivityTransportError) as context:
            asyncio.run(run_prepare())
        self.assertEqual(context.exception.status, "limited")
        self.assertIn("stoken_v2", context.exception.reason)
        self.assertIn("mid", context.exception.reason)

    def test_zzz_uses_separate_bbs_device_fp_contract(self) -> None:
        account_device = "DEVICE-ID"
        seed_id = "11111111-2222-4333-8444-555555555555"
        body = _device_fp_body(
            account_device,
            game="绝区零",
            seed_id=seed_id,
        )

        self.assertEqual(body["app_name"], "bbs_cn")
        self.assertEqual(body["platform"], "2")
        self.assertEqual(body["seed_id"], seed_id)
        self.assertEqual(body["bbs_device_id"], seed_id)
        self.assertNotEqual(body["bbs_device_id"], account_device.lower())
        self.assertEqual(body["device_id"], account_device.lower())
        self.assertEqual(body["device_fp"], "38d805c20d53d")
        ext_fields = json.loads(body["ext_fields"])
        self.assertEqual(ext_fields["packageName"], "com.mihoyo.hyperion")
        self.assertEqual(ext_fields["deviceInfo"], "Xiaomi/MI 8 SE/MI 8 SE/MI 8 SE")
        self.assertEqual(ext_fields["display"], "MI 8 SE")
        self.assertEqual(ext_fields["board"], "qcom")
        for key in (
            "sdCapacity",
            "buildTime",
            "buildUser",
            "simState",
            "ramRemain",
            "appUpdateTimeDiff",
            "isAirMode",
            "ringMode",
            "chargeStatus",
            "appMemory",
            "vendor",
            "accelerometer",
            "sdRemain",
            "buildTags",
            "ramCapacity",
            "magnetometer",
            "appInstallTimeDiff",
            "gyroscope",
            "batteryStatus",
            "hasKeyboard",
        ):
            self.assertIn(key, ext_fields)

    def test_zzz_note_uses_numeric_xv8_ds(self) -> None:
        target = CommunityActivityTarget(
            account_uid="account",
            account_name="用户 1",
            platform="米游社",
            game="绝区零",
            role_uid="10000001",
            server="prod_gf_cn",
        )
        request = build_community_activity_requests(target)[0]

        with patch(
            "app.tools.community_activity_provider.time.time",
            return_value=1700000000,
        ), patch(
            "app.tools.community_activity_provider.random.randint",
            return_value=654321,
        ):
            headers = CommunityActivityProvider._miyoushe_request_headers(
                request,
                device_id="device-id",
                device_fp="device-fp",
            )

        expected_hash = hashlib.md5(
            (
                "salt=xV8v4Qu54lUKrEYFZkJhB8cuOh9Asafs"
                "&t=1700000000&r=654321&b=&q="
                "role_id=10000001&server=prod_gf_cn"
            ).encode()
        ).hexdigest()
        self.assertEqual(
            headers["DS"],
            f"1700000000,654321,{expected_hash}",
        )
        self.assertEqual(headers["x-rpc-device_id"], "device-id")
        self.assertEqual(headers["x-rpc-device_fp"], "device-fp")


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
                    "current_train_score": 300,
                    "max_train_score": 500,
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
