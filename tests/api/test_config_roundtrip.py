"""全局设置读写往返回归：部分更新不得丢失未提交字段。

历史 bug（#1217 #1251 #1192）都是「只改一个设置项，其它字段被整份丢弃/覆盖」。
接缝是 POST /api/setting/update -> Config.update_setting -> ConfigEntry.update，
以及 POST /api/setting/get -> Config.get_setting。

守的是：
- 只提交一个深层字段时，同一父对象下的兄弟字段和其它顶层分组保持原值；
- 缺省字段保持原值，Replay 保留其既有显式 null 不变更策略；
- 改动确实落盘，重新读取仍是新值。

破坏方式：去掉 update_script 里的 exclude_unset=True，未提交字段会以 None
进入 ConfigEntry.update，把兄弟字段改回默认值，本文件的用例随即变红。
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
from fastapi import FastAPI

import app.api.setting as setting_api
from app.config import config_manager
from app.core.config.manager import AppConfig
from app.models.config import GlobalConfig as RuntimeGlobalConfig
from app.utils import IS_WINDOWS
from app.utils import io as _utils_io
from tests.config_support import activate_config


class _TempConfig(AppConfig):
    """AppConfig 的最小实例：只保留真实的 update_setting/get_setting 行为。

    直接调用 AppConfig.__init__ 会建 config/data/debug/history 目录并注入
    truststore；测试只需要全局配置项本身。
    """

    def __init__(self) -> None:
        self.setting = RuntimeGlobalConfig.build()


@unittest.skipUnless(IS_WINDOWS, "secret storage uses Windows DPAPI")
class ConfigRoundtripTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._temp_directory = TemporaryDirectory()
        self.config_file = Path(self._temp_directory.name) / "setting.yaml"
        self.config = _TempConfig()
        await activate_config(self.config.setting, self.config_file)

        # 跨分组的非默认种子值，用来区分「保留原值」与「被默认值覆盖」。
        await self.config.setting.update(
            RuntimeGlobalConfig.model_validate(
                {
                    "Function": {
                        "IfAllowSleep": True,
                        "HistoryRetentionTime": 30,
                        "IfSilence": False,
                    },
                    "Update": {
                        "Source": "GitHub",
                        "Channel": "beta",
                        "GitHubMirror": "Off",
                    },
                    "Notify": {
                        "SMTPServerAddress": "smtp.seed.example",
                        "ToAddress": "seed@example.com",
                    },
                    "Replay": {
                        "Port": 4456,
                        "MaxReplayCount": 5,
                        "Password": "seed-secret",
                    },
                    "Display": {"VirtualDisplayMode": "1920x1080@30"},
                }
            )
        )

        self._original_router_config = setting_api.Config
        setting_api.Config = self.config
        app = FastAPI()
        app.include_router(setting_api.router)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        setting_api.Config = self._original_router_config
        self._temp_directory.cleanup()

    async def _update(self, data: dict) -> None:
        response = await self.client.post("/api/setting/update", json={"data": data})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["code"], 200, body)
        await config_manager.flush()

    async def _get(self) -> dict:
        response = await self.client.post("/api/setting/get")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["code"], 200, body)
        return body["data"]

    def _on_disk(self) -> dict:
        return _utils_io.read_dict_file(self.config_file)

    async def test_partial_update_keeps_siblings_and_other_groups(self) -> None:
        await self._update({"Update": {"Source": "MirrorChyan"}})

        data = await self._get()
        self.assertEqual(data["Update"]["Source"], "MirrorChyan")
        self.assertEqual(data["Update"]["Channel"], "beta")
        self.assertEqual(data["Update"]["GitHubMirror"], "Off")
        self.assertEqual(data["Function"]["IfAllowSleep"], True)
        self.assertEqual(data["Function"]["HistoryRetentionTime"], 30)
        self.assertEqual(data["Notify"]["SMTPServerAddress"], "smtp.seed.example")
        self.assertEqual(data["Replay"]["Port"], 4456)
        self.assertEqual(data["Display"]["VirtualDisplayMode"], "1920x1080@30")

        disk = self._on_disk()
        self.assertEqual(disk["Update"]["Source"], "MirrorChyan")
        self.assertEqual(disk["Update"]["Channel"], "beta")
        self.assertEqual(disk["Function"]["IfAllowSleep"], True)
        self.assertEqual(disk["Function"]["HistoryRetentionTime"], 30)

    async def test_deep_field_update_only_touches_target_field(self) -> None:
        await self._update({"Notify": {"SMTPServerAddress": "smtp.new.example"}})

        data = await self._get()
        self.assertEqual(data["Notify"]["SMTPServerAddress"], "smtp.new.example")
        self.assertEqual(data["Notify"]["ToAddress"], "seed@example.com")
        self.assertEqual(data["Function"]["IfSilence"], False)
        self.assertEqual(data["Function"]["IfAllowSleep"], True)
        self.assertEqual(data["Update"]["Channel"], "beta")

    async def test_empty_and_null_payloads_do_not_clear_values(self) -> None:
        before = await self._get()

        await self._update({})
        self.assertEqual(await self._get(), before)

        response = await self.client.post(
            "/api/setting/update",
            json={"data": {"Replay": {"Password": None, "Port": None}}},
        )
        self.assertEqual(response.json()["code"], 200)
        after_null = await self._get()
        self.assertEqual(after_null["Replay"]["Port"], 4456)
        self.assertTrue(after_null["Replay"]["PasswordConfigured"])

        self.assertEqual(await self._get(), before)

    async def test_replay_password_survives_other_updates(self) -> None:
        await self._update({"Replay": {"Port": 4457}})
        data = await self._get()
        self.assertEqual(data["Replay"]["Port"], 4457)
        self.assertTrue(data["Replay"]["PasswordConfigured"])
        self.assertEqual(self.config.setting.Replay.Password, "seed-secret")

        # PasswordConfigured 是只读回显，写回来不得改变真实密码
        await self._update({"Replay": {"PasswordConfigured": False}})
        data = await self._get()
        self.assertTrue(data["Replay"]["PasswordConfigured"])
        self.assertEqual(self.config.setting.Replay.Password, "seed-secret")


if __name__ == "__main__":
    unittest.main()
