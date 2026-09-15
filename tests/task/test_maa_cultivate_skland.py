"""森空岛练度编排层测试：TTL 缓存、降级链路与 token 轮换回写（决策 38）。

外部接口（client/凭据准备/刷新/player/info）全部打桩，不触网；
serialize_skland_credential 用真实实现以锁定回写序列化形状。
"""

import json
import unittest
from unittest.mock import patch

from app.task.MAA.tools.cultivate.skland import (
    SklandAccountRef,
    clear_skland_progression_cache,
    fetch_skland_progression,
)
from app.tools.skland import SklandCredentialExpiredError

REF = SklandAccountRef(
    account_uid="018f3c2a-1111-7000-8000-000000000001", game_uid="100000001"
)

_PLAYER_INFO = {
    "chars": [
        {
            # 真机实测（2026-09-15）：干员标识字段是 charId，不是 id
            "charId": "char_002_amiya",
            "name": None,
            "level": 80,
            "evolvePhase": 2,
            "skills": [{"id": "skchr_amiya_2", "specializeLevel": 3}],
            "equip": [{"id": "uniequip_002_amiya", "level": 2, "locked": False}],
        }
    ]
}


class _FakeClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FetchSklandProgressionTest(unittest.TestCase):
    def setUp(self) -> None:
        clear_skland_progression_cache()

    def _patch_transport(self, *, refresh_token: str = "t1"):
        """打桩全部外部接口；prepare/refresh 返回固定凭据，refresh 可轮换 token。"""

        credential = {
            "oauthToken": "o",
            "token": refresh_token,
            "cred": "c",
            "userId": "u",
        }

        async def fake_device_id(proxy=None, client=None):
            return "device"

        async def fake_prepare(client, raw, device_id):
            return dict(credential)

        async def fake_refresh(client, credential, device_id):
            return dict(credential)

        async def fake_fetch(client, **kwargs):
            return dict(_PLAYER_INFO)

        return patch.multiple(
            "app.task.MAA.tools.cultivate.skland",
            create_skland_client=lambda proxy=None: _FakeClient(),
            get_cached_device_id=fake_device_id,
            prepare_skland_session_credential=fake_prepare,
            refresh_skland_session_credential=fake_refresh,
            fetch_skland_player_info=fake_fetch,
        )

    def test_success_parses_and_hits_cache(self) -> None:
        loads: list[str] = []

        async def load(account_uid):
            loads.append(account_uid)
            return "raw-token"

        with self._patch_transport():
            first = _run(
                fetch_skland_progression(
                    REF, load_credential=load, force=True, now=1000.0
                )
            )
            # TTL 内复用缓存：不重复装凭据、不重复拉取
            second = _run(
                fetch_skland_progression(REF, load_credential=load, now=1100.0)
            )

        self.assertEqual(loads, [REF.account_uid])
        self.assertEqual(first, second)
        assert first is not None
        progressions, captured_at = first
        self.assertEqual(captured_at, 1000)
        self.assertEqual(progressions["char_002_amiya"].elite, 2)
        self.assertEqual(progressions["char_002_amiya"].masteries, {"skchr_amiya_2": 3})

    def test_force_bypasses_cache(self) -> None:
        loads: list[str] = []

        async def load(account_uid):
            loads.append(account_uid)
            return "raw-token"

        with self._patch_transport():
            _run(
                fetch_skland_progression(
                    REF, load_credential=load, force=True, now=1000.0
                )
            )
            _run(
                fetch_skland_progression(
                    REF, load_credential=load, force=True, now=1100.0
                )
            )

        self.assertEqual(len(loads), 2)

    def test_missing_credential_degrades_with_negative_cache(self) -> None:
        loads: list[str] = []

        async def load(account_uid):
            loads.append(account_uid)
            return None

        with self._patch_transport():
            first = _run(
                fetch_skland_progression(REF, load_credential=load, now=1000.0)
            )
            # 失败负缓存：60s 窗口内不重复装凭据（避免预览连点打外部接口）
            second = _run(
                fetch_skland_progression(REF, load_credential=load, now=1050.0)
            )

        self.assertIsNone(first)
        self.assertIsNone(second)
        self.assertEqual(len(loads), 1)

    def test_empty_progressions_degrades_with_negative_cache(self) -> None:
        """接口可解析但练度为空（形状漂移）按失败负缓存，不当成功缓存（复审 P2）。"""

        loads: list[str] = []

        async def load(account_uid):
            loads.append(account_uid)
            return "raw-token"

        async def fetch_empty(client, **kwargs):
            return {}

        patches = self._patch_transport()
        with (
            patches,
            patch(
                "app.task.MAA.tools.cultivate.skland.fetch_skland_player_info",
                fetch_empty,
            ),
        ):
            first = _run(
                fetch_skland_progression(REF, load_credential=load, now=1000.0)
            )
            # 空练度与失败同路：60s 窗口内不重复装凭据
            second = _run(
                fetch_skland_progression(REF, load_credential=load, now=1050.0)
            )

        self.assertIsNone(first)
        self.assertIsNone(second)
        self.assertEqual(len(loads), 1)

    def test_token_rotation_is_written_back(self) -> None:
        saved: list[tuple[str, str]] = []

        async def load(account_uid):
            return "raw-token"

        async def save(account_uid, serialized):
            saved.append((account_uid, serialized))

        async def refresh_rotates(client, credential, device_id):
            return {**credential, "token": "t2-rotated"}

        patches = self._patch_transport()
        with (
            patches,
            patch(
                "app.task.MAA.tools.cultivate.skland.refresh_skland_session_credential",
                refresh_rotates,
            ),
        ):
            result = _run(
                fetch_skland_progression(
                    REF,
                    load_credential=load,
                    save_credential=save,
                    force=True,
                    now=1000.0,
                )
            )

        self.assertIsNotNone(result)
        self.assertEqual(len(saved), 1)
        account_uid, serialized = saved[0]
        self.assertEqual(account_uid, REF.account_uid)
        # 回写内容是真实 serialize 形状，且带轮换后的 token
        self.assertEqual(json.loads(serialized)["token"], "t2-rotated")

    def test_expired_credential_degrades(self) -> None:
        async def load(account_uid):
            return "raw-token"

        def refresh_expired(client, credential, device_id):
            raise SklandCredentialExpiredError("森空岛凭据已失效")

        patches = self._patch_transport()
        with (
            patches,
            patch(
                "app.task.MAA.tools.cultivate.skland.refresh_skland_session_credential",
                refresh_expired,
            ),
        ):
            result = _run(
                fetch_skland_progression(
                    REF, load_credential=load, force=True, now=1000.0
                )
            )

        self.assertIsNone(result)

    def test_unexpected_error_degrades(self) -> None:
        """设备 ID 等接口抛裸 Exception 时同样 fail-open 降级（评审 P1-1）。"""

        async def load(account_uid):
            return "raw-token"

        async def device_id_boom(proxy=None, client=None):
            raise Exception("设备ID计算失败: {resp}")

        patches = self._patch_transport()
        with (
            patches,
            patch(
                "app.task.MAA.tools.cultivate.skland.get_cached_device_id",
                device_id_boom,
            ),
        ):
            result = _run(
                fetch_skland_progression(
                    REF, load_credential=load, force=True, now=1000.0
                )
            )

        self.assertIsNone(result)


def _run(awaitable):
    import asyncio

    return asyncio.run(awaitable)


if __name__ == "__main__":
    unittest.main()
