import asyncio
import hashlib
import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from app.core.community_activity import (
    _targets_for_roles,
    build_configured_community_activity_failures,
    collect_configured_community_activity,
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
    _raise_business_error,
)
from app.tools.community_activity_roles import (
    CommunityActivityCapability,
    CommunityActivityRole,
    CommunityActivityRoleDiscovery,
    normalize_skland_roles,
)
from app.tools.community_activity_transport import (
    CommunityActivityTransportError,
)
from app.tools.miyoushe import prepare_miyoushe_session


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

    def test_real_miyoushe_device_pair_is_only_attached_to_zzz(self) -> None:
        roles = tuple(
            CommunityActivityRole(
                platform="米游社",
                game=game,
                role_uid=f"role-{index}",
                server="server",
            )
            for index, game in enumerate(("原神", "星穹铁道", "绝区零"))
        )

        targets = _targets_for_roles(
            roles=roles,
            account_uid="account",
            account_name="用户 1",
            miyoushe_device_id="real-device-id",
            miyoushe_device_fp="real-device-fp",
        )

        self.assertEqual(targets[0].device_id, "")
        self.assertEqual(targets[1].device_fp, "")
        self.assertEqual(targets[2].device_id, "real-device-id")
        self.assertEqual(targets[2].device_fp, "real-device-fp")
        self.assertNotIn("real-device-id", repr(targets[2]))
        self.assertNotIn("real-device-fp", repr(targets[2]))


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

    def test_limited_miyoushe_capability_skips_detail_requests(self) -> None:
        account = _FakeAccount(
            {
                "Enabled": True,
                "Name": "用户 1",
                "MiyousheToken": "configured",
            }
        )

        class LimitedProvider:
            request_count = 0

            async def discover_roles(self, **_kwargs):
                return CommunityActivityRoleDiscovery(
                    platform="米游社",
                    roles=tuple(
                        CommunityActivityRole(
                            platform="米游社",
                            game=game,
                            role_uid=f"role-{index}",
                            server="server",
                        )
                        for index, game in enumerate(
                            ("原神", "星穹铁道", "绝区零"),
                            start=1,
                        )
                    ),
                    activity_capability=CommunityActivityCapability(
                        status="limited",
                        reason="米游社实时便笺需要完整的 stoken_v2 和 mid，当前凭据能力受限",
                    ),
                )

            async def request(self, _request):
                self.request_count += 1
                raise AssertionError("受限能力不应发送详细便笺请求")

        provider = LimitedProvider()
        with patch(
            "app.core.community_activity._selected_accounts",
            return_value=(("account", account),),
        ), patch(
            "app.core.community_activity.CommunityActivityProvider",
            return_value=provider,
        ):
            snapshots = asyncio.run(
                collect_configured_community_activity(proxy="")
            )

        self.assertEqual(provider.request_count, 0)
        self.assertEqual(
            [(snapshot.game, snapshot.status) for snapshot in snapshots],
            [("原神", "limited"), ("星穹铁道", "limited"), ("绝区零", "limited")],
        )
        self.assertTrue(
            all("stoken_v2" in snapshot.reason for snapshot in snapshots)
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
        self.assertEqual(request_kwargs["json"]["device_id"], "device-id")
        self.assertEqual(
            request_kwargs["headers"]["x-rpc-device_id"],
            "device-id",
        )
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
        provider = CommunityActivityProvider(
            "米游社",
            "stuid=10000001; cookie_token=cookie-token; stoken_v2=v2-token",
        )

        async def run_prepare() -> None:
            await provider._prepare_miyoushe(
                request,
                AsyncMock(),
            )

        with self.assertRaises(CommunityActivityTransportError) as context:
            asyncio.run(run_prepare())
        self.assertEqual(context.exception.status, "limited")
        self.assertNotIn("stoken_v2", context.exception.reason)
        self.assertIn("mid", context.exception.reason)

    def test_miyoushe_session_exposes_activity_capability(self) -> None:
        limited = prepare_miyoushe_session(
            "stuid=10000001; cookie_token=cookie-token"
        )
        ready = prepare_miyoushe_session(
            "stuid=10000001; cookie_token=cookie-token; "
            "stoken_v2=v2-token; mid=mid-value"
        )

        self.assertFalse(limited.capabilities.activity_ready)
        self.assertEqual(
            limited.capabilities.activity_missing_fields,
            ("stoken_v2", "mid"),
        )
        self.assertTrue(ready.capabilities.activity_ready)
        self.assertEqual(ready.capabilities.activity_missing_fields, ())

    def test_zzz_automatically_acquires_and_registers_device_pair(self) -> None:
        target = CommunityActivityTarget(
            account_uid="account",
            account_name="用户 1",
            platform="米游社",
            game="绝区零",
            role_uid="10000001",
            server="prod_gf_cn",
        )
        request = build_community_activity_requests(target)[0]
        provider = CommunityActivityProvider(
            "米游社",
            "stuid=10000001; cookie_token=cookie-token; "
            "stoken_v2=v2-token; mid=mid-value",
        )

        client = AsyncMock()
        provider._acquire_device_fp = AsyncMock(return_value="automatic-device-fp")
        provider._register_device = AsyncMock()

        _, device_id, device_fp = asyncio.run(
            provider._prepare_miyoushe(request, client)
        )

        self.assertTrue(device_id)
        self.assertEqual(device_fp, "automatic-device-fp")
        provider._acquire_device_fp.assert_awaited_once()
        provider._register_device.assert_awaited_once()

    def test_zzz_uses_persisted_real_device_pair_without_registration(self) -> None:
        target = CommunityActivityTarget(
            account_uid="account",
            account_name="用户 1",
            platform="米游社",
            game="绝区零",
            role_uid="10000001",
            server="prod_gf_cn",
            device_id="real-device-id",
            device_fp="real-device-fp",
        )
        request = build_community_activity_requests(target)[0]
        self.assertNotIn("real-device-id", repr(request))
        self.assertNotIn("real-device-fp", repr(request))
        self.assertNotIn("x-rpc-device_id", request.header_map)
        self.assertNotIn("x-rpc-device_fp", request.header_map)
        client = AsyncMock()
        provider = CommunityActivityProvider(
            "米游社",
            "stuid=10000001; cookie_token=cookie-token; "
            "stoken_v2=v2-token; mid=mid-value",
        )

        _, device_id, device_fp = asyncio.run(
            provider._prepare_miyoushe(request, client)
        )

        self.assertEqual(device_id, "real-device-id")
        self.assertEqual(device_fp, "real-device-fp")
        headers = provider._miyoushe_request_headers(
            request,
            device_id=device_id,
            device_fp=device_fp,
        )
        self.assertEqual(headers["x-rpc-device_id"], "real-device-id")
        self.assertEqual(headers["x-rpc-device_fp"], "real-device-fp")
        client.post.assert_not_awaited()

    def test_other_miyoushe_games_ignore_zzz_device_pair(self) -> None:
        target = CommunityActivityTarget(
            account_uid="account",
            account_name="用户 1",
            platform="米游社",
            game="星穹铁道",
            role_uid="10000001",
            server="prod_official_usa",
            device_id="real-device-id",
            device_fp="real-device-fp",
        )
        request = build_community_activity_requests(target)[0]
        provider = CommunityActivityProvider(
            "米游社",
            "stuid=10000001; cookie_token=cookie-token; "
            "stoken_v2=v2-token; mid=mid-value",
        )

        _, device_id, device_fp = asyncio.run(
            provider._prepare_miyoushe(request, AsyncMock())
        )

        self.assertNotEqual(device_id, "real-device-id")
        self.assertEqual(device_fp, "")

    def test_zzz_risk_code_remains_limited(self) -> None:
        with self.assertRaises(CommunityActivityTransportError) as context:
            _raise_business_error(
                {"retcode": 10041},
                platform="米游社",
                game="绝区零",
            )

        self.assertEqual(context.exception.status, "limited")

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
                    "campaign": {
                        "reward": {"current": 1725, "total": 1800}
                    },
                    "tower": {
                        "reward": {
                            "lowerItem": {"current": 12, "total": 60},
                            "higherItem": {"current": 3, "total": 24},
                        }
                    },
                    "status": {
                        "ap": {
                            "current": 20,
                            "max": 135,
                            "lastApAddTime": 1000,
                        },
                        "exp": {"current": 21966, "total": 76000},
                    },
                    "recruit": [
                        {"state": 1, "finishTs": -1},
                        {"state": 0, "finishTs": -1},
                        {"state": 2, "finishTs": 1720},
                    ],
                    "building": {
                        "hire": {
                            "refreshCount": 0,
                            "completeWorkTime": 1720,
                        },
                        "training": {
                            "trainee": {"charId": "char_1"},
                            "slotState": 1,
                            "remainSecs": 7200,
                        },
                        "labor": {
                            "value": 222,
                            "maxValue": 225,
                            "remainSecs": 540,
                        },
                        "manufactures": [
                            {
                                "complete": 16,
                                "capacity": 148,
                                "formulaId": "formula_1",
                            }
                        ],
                        "tradings": [
                            {"stock": [{}, {}, {}, {}, {}], "stockLimit": 21}
                        ],
                        "tiredChars": [{"charId": "char_2"}],
                    },
                    "charInfoMap": {"char_1": {"name": "阿米娅"}},
                    "manufactureFormulaInfoMap": {
                        "formula_1": {"weight": 2}
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
                        "dailyMission": {
                            "dailyActivation": 100,
                            "maxDailyActivation": 100,
                        },
                        "currentTs": 1000,
                        "dungeon": {
                            "curStamina": 80,
                            "maxStamina": 240,
                            "maxTs": 70120,
                        },
                        "weeklyMission": {"score": 2, "total": 10},
                        "bpSystem": {"curLevel": 45, "maxLevel": 60},
                        "seekSuspicion": {"count": 200000, "total": 200000},
                    }
                },
            },
            platform="森空岛",
        )

        self.assertEqual((arknights.completed, arknights.target), (8, 10))
        self.assertEqual(arknights.resources[0]["current"], 21)
        self.assertEqual(
            arknights.resources[0]["status"],
            "预计11小时24分钟后回满",
        )
        arknights_tasks = {item["name"]: item for item in arknights.tasks}
        self.assertEqual(
            arknights_tasks["每周报酬合成玉"]["completed"],
            1725,
        )
        self.assertEqual(arknights_tasks["数据增补条"]["target"], 60)
        self.assertEqual(arknights_tasks["数据增补仪"]["target"], 24)
        arknights_resources = {
            item["name"]: item for item in arknights.resources
        }
        self.assertEqual(arknights_resources["公开招募"]["current"], 2)
        self.assertEqual(
            arknights_resources["公招刷新"]["status"],
            "预计6分钟后获得刷新次数",
        )
        self.assertEqual(
            arknights_resources["训练室"]["status"],
            "阿米娅，预计2小时后完成训练",
        )
        self.assertEqual(arknights_resources["无人机"]["current"], 222)
        self.assertEqual(arknights_resources["制造进度"]["target"], 74)
        self.assertEqual(arknights_resources["订单进度"]["current"], 5)
        self.assertEqual(
            arknights_resources["干员疲劳"]["status"],
            "1名干员疲劳",
        )
        self.assertEqual((endfield.completed, endfield.target), (100, 100))
        self.assertEqual(endfield.resources[0]["name"], "理智")
        self.assertEqual(endfield.resources[0]["current"], 80)
        self.assertEqual(
            endfield.resources[0]["status"],
            "预计19小时12分钟后回满",
        )
        endfield_tasks = {item["name"]: item for item in endfield.tasks}
        self.assertEqual(endfield_tasks["每周事务"]["completed"], 2)
        self.assertEqual(endfield_tasks["通行证等级"]["target"], 60)
        self.assertEqual(endfield_tasks["蚀像寻遗"]["completed"], 200000)
        self.assertEqual(endfield_tasks["蚀像寻遗"]["period"], "weekly")

    def test_endfield_rejects_unconfirmed_daily_progress_shape(self) -> None:
        snapshot = self.parse(
            "终末地",
            {
                "code": 0,
                "data": {
                    "detail": {
                        "dailyMission": {"current": 100, "total": 100},
                        "dungeon": {"curStamina": 80, "maxStamina": 240},
                    }
                },
            },
            platform="森空岛",
        )

        self.assertEqual(snapshot.status, "unavailable")
        self.assertIn("每日任务进度", snapshot.reason)

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
                    "resin_recovery_time": 38400,
                    "current_home_coin": 30,
                    "max_home_coin": 2400,
                    "home_coin_recovery_time": 282960,
                    "max_expedition_num": 5,
                    "expeditions": [
                        {"status": "Ongoing"},
                        {"status": "Ongoing"},
                        {"status": "Ongoing"},
                        {"status": "Ongoing"},
                    ],
                    "remain_resin_discount_num": 1,
                    "resin_discount_num_limit": 3,
                    "transformer": {
                        "obtained": True,
                        "recovery_time": {
                            "reached": True,
                            "Day": 0,
                            "Hour": 0,
                            "Minute": 0,
                            "Second": 0,
                        },
                    },
                    "daily_task": {
                        "attendance_visible": True,
                        "is_extra_task_reward_received": True,
                        "stored_attendance": 298.8,
                    },
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
                    "stamina_recover_time": 21600,
                    "current_rogue_score": 12000,
                    "max_rogue_score": 18000,
                    "rogue_tourn_weekly_unlocked": True,
                    "rogue_tourn_weekly_cur": 1000,
                    "rogue_tourn_weekly_max": 14000,
                    "weekly_cocoon_cnt": 2,
                    "weekly_cocoon_limit": 3,
                    "current_reserve_stamina": 300,
                    "accepted_epedition_num": 3,
                    "total_expedition_num": 4,
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
                    "vhs_sale": {"sale_state": "SaleStateDone"},
                    "card_sign": "CardSignDone",
                    "bounty_commission": {"num": 3, "total": 5},
                    "survey_points": {"num": 400, "total": 8000},
                    "weekly_task": {"cur_point": 1200, "max_point": 1600},
                    "temple_running": {
                        "current_currency": 800,
                        "weekly_currency_max": 2000,
                    },
                },
            },
            platform="米游社",
        )

        self.assertEqual((genshin.completed, genshin.target), (4, 4))
        self.assertEqual(genshin.tasks[0]["status"], "奖励已领取")
        self.assertEqual(genshin.tasks[1]["name"], "周本减半次数")
        self.assertEqual(genshin.tasks[1]["status"], "剩余1次")
        self.assertEqual(
            genshin.resources[0]["status"],
            "预计10小时40分钟后回满",
        )
        genshin_tasks = {item["name"]: item for item in genshin.tasks}
        self.assertEqual(genshin_tasks["参量质变仪"]["status"], "可使用")
        genshin_resources = {item["name"]: item for item in genshin.resources}
        self.assertEqual(
            genshin_resources["长效历练点"]["status"],
            "现有298.8点",
        )
        self.assertEqual(genshin_resources["探索派遣"]["current"], 4)
        self.assertEqual(genshin_resources["探索派遣"]["target"], 5)
        self.assertEqual((hsr.completed, hsr.target), (300, 500))
        hsr_tasks = {item["name"]: item for item in hsr.tasks}
        self.assertEqual(hsr_tasks["模拟宇宙积分"]["period"], "weekly")
        self.assertEqual(hsr_tasks["差分宇宙同步积分"]["target"], 14000)
        self.assertEqual(hsr_tasks["历战余响次数"]["status"], "剩余2次")
        self.assertEqual(hsr.resources[0]["status"], "预计6小时后回满")
        hsr_resources = {item["name"]: item for item in hsr.resources}
        self.assertEqual(hsr_resources["储备开拓力"]["target"], 2400)
        self.assertEqual(hsr_resources["探索派遣"]["current"], 3)
        self.assertEqual((zzz.completed, zzz.target), (320, 400))
        self.assertEqual(zzz.resources[0]["current"], 180)
        self.assertEqual(zzz.resources[0]["status"], "预计1小时后回满")
        zzz_tasks = {item["name"]: item for item in zzz.tasks}
        self.assertEqual(zzz_tasks["录像店经营"]["status"], "待结算")
        self.assertEqual(zzz_tasks["录像店经营"]["target"], 0)
        self.assertEqual(zzz_tasks["悬赏委托"]["completed"], 3)
        self.assertEqual(zzz_tasks["零号空洞调查积分"]["target"], 8000)
        self.assertEqual(zzz_tasks["丽都周纪积分"]["completed"], 1200)
        self.assertEqual(zzz.resources[1]["name"], "随便观周收益")

    def test_starrail_ignores_reversed_synchronicity_progress(self) -> None:
        snapshot = self.parse(
            "星穹铁道",
            {
                "retcode": 0,
                "data": {
                    "current_train_score": 0,
                    "max_train_score": 500,
                    "rogue_tourn_weekly_unlocked": True,
                    "rogue_tourn_weekly_cur": 18000,
                    "rogue_tourn_weekly_max": 1000,
                },
            },
            platform="米游社",
        )

        task_names = {item["name"] for item in snapshot.tasks}
        self.assertNotIn("差分宇宙同步积分", task_names)

    def test_non_json_is_reported_as_limited_without_decoder_details(self) -> None:
        snapshot = self.parse("原神", "<html>blocked</html>", platform="米游社")

        self.assertEqual(snapshot.status, "limited")
        self.assertNotIn("JSONDecodeError", snapshot.reason)
        self.assertIn("非 JSON", snapshot.reason)

    def test_generic_numeric_fields_do_not_impersonate_daily_progress(self) -> None:
        snapshot = self.parse(
            "原神",
            {
                "retcode": 0,
                "data": {
                    "count": 4,
                    "limit": 4,
                    "score": 100,
                },
            },
            platform="米游社",
        )

        self.assertEqual(snapshot.status, "unavailable")
        self.assertIn("未返回可识别", snapshot.reason)


if __name__ == "__main__":
    unittest.main()
