"""神秘入口后端校验：口令派生、跨日失效与解锁状态持久化。

守的是：
- 口令按当日北京日期派生，与前端 frontend/src/utils/mysteryAccess.ts 同源；
- 错误口令、非法字符都不能解锁，解锁状态跨日自动失效；
- /api/mystery 的状态、解锁、重新锁定三个端点与落盘结果一致。

破坏方式：把 matches_access_code 改成只比长度、或把 is_unlocked 改成只看是否写过日期，
跨日用例与前缀用例随即变红。
"""

import hashlib
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
from fastapi import FastAPI

import app.api.mystery as mystery_api
import app.core.mystery as mystery_core
from app.config import config_manager
from app.core.config.manager import AppConfig
from app.models.config import GlobalConfig as RuntimeGlobalConfig
from app.utils import UTC8
from tests.config_support import activate_config


def _access_code(moment: datetime) -> str:
    """按前端算法派生当日完整口令。"""
    return (
        hashlib.sha256(moment.astimezone(UTC8).strftime("%Y%m%d").encode())
        .hexdigest()
        .upper()
    )


class _TempConfig(AppConfig):
    """只保留全局配置项本身的最小实例。"""

    def __init__(self) -> None:
        self.setting = RuntimeGlobalConfig.build()


class MysteryApiTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._temp_directory = TemporaryDirectory()
        self.config_file = Path(self._temp_directory.name) / "setting.yaml"
        self.config = _TempConfig()
        await activate_config(self.config.setting, self.config_file)

        self._original_core_config = mystery_core.Config
        mystery_core.Config = self.config
        app = FastAPI()
        app.include_router(mystery_api.router)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        mystery_core.Config = self._original_core_config
        self._temp_directory.cleanup()

    async def _status(self) -> dict:
        response = await self.client.get("/api/mystery/status")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["code"], 200, body)
        return body

    async def _unlock(self, access_code: str) -> dict:
        response = await self.client.post(
            "/api/mystery/unlock", json={"accessCode": access_code}
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    async def test_wrong_code_keeps_locked(self) -> None:
        body = await self._unlock("DEADBEEF")
        self.assertEqual(body["code"], 400, body)
        self.assertFalse((await self._status())["unlocked"])

        body = await self._unlock("not-hex")
        self.assertEqual(body["code"], 400, body)
        self.assertFalse((await self._status())["unlocked"])

    async def test_unlock_accepts_derived_code_and_lock_releases(self) -> None:
        today = datetime.now(tz=UTC8).strftime("%Y-%m-%d")
        body = await self._unlock(_access_code(datetime.now(tz=UTC8)))
        self.assertEqual(body["code"], 200, body)
        self.assertTrue(body["unlocked"])
        self.assertEqual(body["unlockedDate"], today)

        status = await self._status()
        self.assertTrue(status["unlocked"])
        self.assertEqual(status["unlockedDate"], today)

        response = await self.client.post("/api/mystery/lock")
        self.assertEqual(response.json()["code"], 200)
        status = await self._status()
        self.assertFalse(status["unlocked"])
        self.assertEqual(status["unlockedDate"], "")

    async def test_unlock_accepts_code_prefix(self) -> None:
        prefix = _access_code(datetime.now(tz=UTC8))[:8]
        body = await self._unlock(prefix)
        self.assertEqual(body["code"], 200, body)
        self.assertTrue((await self._status())["unlocked"])

    async def test_previous_day_unlock_expires(self) -> None:
        yesterday = datetime.now(tz=UTC8) - timedelta(days=1)
        async with config_manager.transaction():
            await self.config.setting.update(
                RuntimeGlobalConfig.model_validate(
                    {"mystery": {"UnlockedDate": yesterday}}
                ),
                check_visibility=False,
            )

        status = await self._status()
        self.assertFalse(status["unlocked"])
        self.assertEqual(status["unlockedDate"], yesterday.strftime("%Y-%m-%d"))


if __name__ == "__main__":
    unittest.main()
