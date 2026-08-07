import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.tools import (
    get_game_sign_account,
    list_game_sign_accounts,
    update_game_sign_account,
)
from app.core.config import AppConfig
from app.models.config import MaaConfig, MaaEndConfig
from app.models.schema import (
    GameSignAccountGetIn,
    GameSignAccountGroupConfig,
    GameSignAccountUpdateIn,
)


class GameSignAccountApiTest(unittest.IsolatedAsyncioTestCase):
    async def test_list_returns_decrypted_credentials(self) -> None:
        account_id = str(uuid.uuid4())
        raw = {
            "instances": [{"uid": account_id, "type": "GameSignAccountGroup"}],
            account_id: {
                "GameSignAccount": {
                    "Name": "用户",
                    "Enabled": True,
                    "MiyousheToken": "miyoushe-token",
                    "KuroToken": "kuro-token",
                    "SklandToken": "",
                }
            },
        }

        with patch(
            "app.api.tools.Config.get_game_sign_accounts",
            new=AsyncMock(return_value=raw),
        ) as get_accounts:
            response = await list_game_sign_accounts()

        get_accounts.assert_awaited_once_with()
        account = response.data[account_id]["GameSignAccount"]
        self.assertEqual(account["MiyousheToken"], "miyoushe-token")
        self.assertEqual(account["KuroToken"], "kuro-token")
        self.assertEqual(account["SklandToken"], "")

    async def test_get_returns_decrypted_credentials(self) -> None:
        account_id = str(uuid.uuid4())
        raw = {
            "GameSignAccount": {
                "Name": "用户",
                "MiyousheToken": "miyoushe-token",
                "KuroToken": "",
                "SklandToken": "skland-token",
            }
        }

        with patch(
            "app.api.tools.Config.get_game_sign_account",
            new=AsyncMock(return_value=raw),
        ) as get_account:
            response = await get_game_sign_account(
                GameSignAccountGetIn(accountId=account_id)
            )

        get_account.assert_awaited_once_with(account_id)
        self.assertEqual(response.data.MiyousheToken, "miyoushe-token")
        self.assertEqual(response.data.KuroToken, "")
        self.assertEqual(response.data.SklandToken, "skland-token")

    async def test_update_writes_submitted_credentials(self) -> None:
        account_id = str(uuid.uuid4())
        request = GameSignAccountUpdateIn(
            accountId=account_id,
            data=GameSignAccountGroupConfig(
                Name="新名称",
                MiyousheToken="miyoushe-token",
                KuroToken="new-kuro-token",
                SklandToken="",
            ),
        )

        with patch(
            "app.api.tools.Config.update_game_sign_account",
            new=AsyncMock(),
        ) as update_account:
            response = await update_game_sign_account(request)

        self.assertEqual(response.code, 200)
        update_account.assert_awaited_once_with(
            account_id,
            {
                "GameSignAccount": {
                    "Name": "新名称",
                    "MiyousheToken": "miyoushe-token",
                    "KuroToken": "new-kuro-token",
                    "SklandToken": "",
                }
            },
        )


class GameSignAccountConfigTest(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def make_config(tools_config: SimpleNamespace) -> object:
        class ConfigHarness:
            _clear_game_sign_account_results = (
                AppConfig._clear_game_sign_account_results
            )

        config = ConfigHarness()
        config.ToolsConfig = tools_config
        return config

    async def test_credential_change_resets_date_and_clears_result(self) -> None:
        account_id = str(uuid.uuid4())
        account = MagicMock()
        account.get.return_value = "old-token"
        account.set = AsyncMock()
        tools_config = SimpleNamespace(
            GameSign_Accounts={uuid.UUID(account_id): account},
            _game_sign_result_data={
                "米游社": [
                    {"account_uid": account_id},
                    {"account_uid": "other-account"},
                ]
            },
        )
        config = self.make_config(tools_config)

        await AppConfig.update_game_sign_account(
            config,
            account_id,
            {"GameSignAccount": {"MiyousheToken": "new-token"}},
        )

        account.set.assert_any_await(
            "GameSignAccount", "MiyousheToken", "new-token"
        )
        account.set.assert_any_await(
            "GameSignAccount", "LastSignDate", "2000-01-01"
        )
        self.assertEqual(
            tools_config._game_sign_result_data,
            {"米游社": [{"account_uid": "other-account"}]},
        )

    async def test_unchanged_credential_keeps_completion_state(self) -> None:
        account_id = str(uuid.uuid4())
        account = MagicMock()
        account.get.return_value = "same-token"
        account.set = AsyncMock()
        tools_config = SimpleNamespace(
            GameSign_Accounts={uuid.UUID(account_id): account},
            _game_sign_result_data={
                "米游社": [{"account_uid": account_id}]
            },
        )
        config = self.make_config(tools_config)

        await AppConfig.update_game_sign_account(
            config,
            account_id,
            {"GameSignAccount": {"MiyousheToken": "same-token"}},
        )

        account.set.assert_awaited_once_with(
            "GameSignAccount", "MiyousheToken", "same-token"
        )
        self.assertEqual(
            tools_config._game_sign_result_data,
            {"米游社": [{"account_uid": account_id}]},
        )
class LegacyUserSklandCredentialTest(unittest.IsolatedAsyncioTestCase):
    async def _assert_token_change_resets_date(self, script_config_type) -> None:
        script_id = uuid.uuid4()
        user_id = uuid.uuid4()
        values = {
            ("Info", "SklandToken"): "old-token",
            ("Data", "LastSklandDate"): "2026-08-07",
        }
        user_config = MagicMock()
        user_config.get.side_effect = lambda group, name: values[(group, name)]

        async def set_value(group: str, name: str, value: str) -> None:
            values[(group, name)] = value

        user_config.set = AsyncMock(side_effect=set_value)
        script_config = script_config_type()
        script_config.UserData = {user_id: user_config}

        config = SimpleNamespace(ScriptConfig={script_id: script_config})
        await AppConfig.update_user(
            config,
            str(script_id),
            str(user_id),
            {"Info": {"SklandToken": "new-token"}},
        )

        user_config.set.assert_any_await("Info", "SklandToken", "new-token")
        user_config.set.assert_any_await("Data", "LastSklandDate", "2000-01-01")

    async def test_maa_token_change_resets_skland_date(self) -> None:
        await self._assert_token_change_resets_date(MaaConfig)

    async def test_maaend_token_change_resets_skland_date(self) -> None:
        await self._assert_token_change_resets_date(MaaEndConfig)


if __name__ == "__main__":
    unittest.main()
