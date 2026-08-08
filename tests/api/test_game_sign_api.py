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
            _sync_legacy_skland_user = AppConfig._sync_legacy_skland_user

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
    class AccountCollection(dict):
        async def add(self, _config_type):
            account_id = uuid.uuid4()
            account = MagicMock()
            account.get.side_effect = lambda group, name: {
                ("GameSignAccount", "Enabled"): True,
            }.get((group, name), "")
            account.set = AsyncMock()
            self[account_id] = account
            return account_id, account

    class ConfigHarness:
        update_user = AppConfig.update_user
        del_user = AppConfig.del_user
        _sync_legacy_skland_user = AppConfig._sync_legacy_skland_user
        _find_game_sign_account_by_skland_token = (
            AppConfig._find_game_sign_account_by_skland_token
        )
        _legacy_skland_token_state = AppConfig._legacy_skland_token_state
        _clear_game_sign_account_results = AppConfig._clear_game_sign_account_results
        _safe_config_get = staticmethod(AppConfig._safe_config_get)

    class UserCollection(dict):
        async def remove(self, user_id):
            self.pop(user_id)

    @staticmethod
    def make_user_config(
        name: str = "旧用户", token: str = "old-token"
    ) -> MagicMock:
        user_config = MagicMock()
        values = {
            ("Info", "Name"): name,
            ("Info", "SklandToken"): token,
            ("Info", "IfSkland"): True,
        }
        user_config.get.side_effect = lambda group, key: values.get((group, key), "")
        user_config.set = AsyncMock()
        return user_config

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

        config = self.ConfigHarness()
        config.ScriptConfig = {script_id: script_config}
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

    async def test_new_token_creates_one_tool_account(self) -> None:
        accounts = self.AccountCollection()
        config = self.ConfigHarness()
        config.ToolsConfig = SimpleNamespace(GameSign_Accounts=accounts)
        config._clear_game_sign_account_results = MagicMock()

        await config._sync_legacy_skland_user(
            user_config=self.make_user_config(token=""),
            user_id=str(uuid.uuid4()),
            old_token="",
            token="new-token",
            enabled=True,
            name="新用户",
        )

        self.assertEqual(len(accounts), 1)
        account = next(iter(accounts.values()))
        account.set.assert_any_await("GameSignAccount", "Name", "新用户")
        account.set.assert_any_await("GameSignAccount", "Enabled", True)
        account.set.assert_any_await("GameSignAccount", "SklandToken", "new-token")
        account.set.assert_any_await(
            "GameSignAccount", "LastSignDate", "2000-01-01"
        )

    async def test_changed_token_reuses_existing_new_token_account(self) -> None:
        old_uid = uuid.uuid4()
        new_uid = uuid.uuid4()
        old_account = MagicMock()
        old_account.get.side_effect = lambda group, key: {
            ("GameSignAccount", "SklandToken"): "old-token",
            ("GameSignAccount", "Enabled"): True,
        }.get((group, key), "")
        old_account.set = AsyncMock()
        new_account = MagicMock()
        new_account.get.side_effect = lambda group, key: {
            ("GameSignAccount", "SklandToken"): "new-token",
            ("GameSignAccount", "Enabled"): True,
        }.get((group, key), "")
        new_account.set = AsyncMock()
        accounts = self.AccountCollection({old_uid: old_account, new_uid: new_account})
        config = self.ConfigHarness()
        config.ToolsConfig = SimpleNamespace(GameSign_Accounts=accounts)
        config._clear_game_sign_account_results = MagicMock()

        await config._sync_legacy_skland_user(
            user_config=self.make_user_config(),
            user_id=str(uuid.uuid4()),
            old_token="old-token",
            token="new-token",
            enabled=True,
            name="更新用户",
        )

        old_account.set.assert_any_await("GameSignAccount", "SklandToken", "")
        old_account.set.assert_any_await(
            "GameSignAccount", "LastSignDate", "2000-01-01"
        )
        new_account.set.assert_any_await(
            "GameSignAccount", "SklandToken", "new-token"
        )
        self.assertFalse(
            any(
                call.args[:3]
                == ("GameSignAccount", "LastSignDate", "2000-01-01")
                for call in new_account.set.await_args_list
            )
        )
        config._clear_game_sign_account_results.assert_called_once_with(str(old_uid))

    async def test_shared_old_token_change_creates_a_separate_tool_account(
        self,
    ) -> None:
        old_uid = uuid.uuid4()
        old_account = MagicMock()
        old_account.get.side_effect = lambda group, key: {
            ("GameSignAccount", "SklandToken"): "shared-token",
            ("GameSignAccount", "Enabled"): True,
        }.get((group, key), "")
        old_account.set = AsyncMock()
        accounts = self.AccountCollection({old_uid: old_account})

        remaining_user = self.make_user_config(token="shared-token")
        script_config = MaaConfig()
        script_config.UserData = {uuid.uuid4(): remaining_user}
        config = self.ConfigHarness()
        config.ScriptConfig = {uuid.uuid4(): script_config}
        config.ToolsConfig = SimpleNamespace(GameSign_Accounts=accounts)
        config._clear_game_sign_account_results = MagicMock()

        await config._sync_legacy_skland_user(
            user_config=self.make_user_config(token="new-token"),
            user_id=str(uuid.uuid4()),
            old_token="shared-token",
            token="new-token",
            enabled=True,
            name="更新用户",
        )

        self.assertEqual(len(accounts), 2)
        old_account.set.assert_not_awaited()
        new_account = next(
            account for uid, account in accounts.items() if uid != old_uid
        )
        new_account.set.assert_any_await(
            "GameSignAccount", "SklandToken", "new-token"
        )

    async def test_shared_old_token_change_reuses_existing_new_token_account(
        self,
    ) -> None:
        old_uid = uuid.uuid4()
        new_uid = uuid.uuid4()
        old_account = MagicMock()
        old_account.get.side_effect = lambda group, key: {
            ("GameSignAccount", "SklandToken"): "shared-token",
            ("GameSignAccount", "Enabled"): True,
        }.get((group, key), "")
        old_account.set = AsyncMock()
        new_account = MagicMock()
        new_account.get.side_effect = lambda group, key: {
            ("GameSignAccount", "SklandToken"): "new-token",
            ("GameSignAccount", "Enabled"): True,
        }.get((group, key), "")
        new_account.set = AsyncMock()
        accounts = self.AccountCollection(
            {old_uid: old_account, new_uid: new_account}
        )

        remaining_user = self.make_user_config(token="shared-token")
        script_config = MaaConfig()
        script_config.UserData = {uuid.uuid4(): remaining_user}
        config = self.ConfigHarness()
        config.ScriptConfig = {uuid.uuid4(): script_config}
        config.ToolsConfig = SimpleNamespace(GameSign_Accounts=accounts)
        config._clear_game_sign_account_results = MagicMock()

        await config._sync_legacy_skland_user(
            user_config=self.make_user_config(token="new-token"),
            user_id=str(uuid.uuid4()),
            old_token="shared-token",
            token="new-token",
            enabled=True,
            name="更新用户",
        )

        self.assertEqual(len(accounts), 2)
        old_account.set.assert_not_awaited()
        new_account.set.assert_any_await(
            "GameSignAccount", "SklandToken", "new-token"
        )
        self.assertFalse(
            any(
                call.args[:3]
                == ("GameSignAccount", "LastSignDate", "2000-01-01")
                for call in new_account.set.await_args_list
            )
        )
        config._clear_game_sign_account_results.assert_not_called()

    async def test_startup_sync_keeps_existing_sign_date_for_same_token(self) -> None:
        account_uid = uuid.uuid4()
        account = MagicMock()
        account.get.side_effect = lambda group, key: {
            ("GameSignAccount", "SklandToken"): "same-token",
            ("GameSignAccount", "Enabled"): True,
        }.get((group, key), "")
        account.set = AsyncMock()
        accounts = self.AccountCollection({account_uid: account})
        config = self.ConfigHarness()
        config.ToolsConfig = SimpleNamespace(GameSign_Accounts=accounts)
        config._clear_game_sign_account_results = MagicMock()

        await config._sync_legacy_skland_user(
            user_config=self.make_user_config(token="same-token"),
            user_id=str(uuid.uuid4()),
            token="same-token",
            enabled=True,
            name="旧用户",
        )

        self.assertFalse(
            any(
                call.args[:3] == ("GameSignAccount", "LastSignDate", "2000-01-01")
                for call in account.set.await_args_list
            )
        )

    async def test_clearing_legacy_token_resets_tool_account_state(self) -> None:
        account_uid = uuid.uuid4()
        account = MagicMock()
        account.get.side_effect = lambda group, key: {
            ("GameSignAccount", "SklandToken"): "old-token",
            ("GameSignAccount", "Enabled"): True,
        }.get((group, key), "")
        account.set = AsyncMock()
        accounts = self.AccountCollection({account_uid: account})
        config = self.ConfigHarness()
        config.ToolsConfig = SimpleNamespace(GameSign_Accounts=accounts)
        config._clear_game_sign_account_results = MagicMock()

        await config._sync_legacy_skland_user(
            user_config=self.make_user_config(token=""),
            user_id=str(uuid.uuid4()),
            old_token="old-token",
            token="",
            enabled=False,
        )

        account.set.assert_any_await("GameSignAccount", "SklandToken", "")
        account.set.assert_any_await(
            "GameSignAccount", "LastSignDate", "2000-01-01"
        )
        config._clear_game_sign_account_results.assert_called_once_with(
            str(account_uid)
        )

    async def test_update_user_syncs_legacy_token_to_tool_account(self) -> None:
        script_id = uuid.uuid4()
        user_id = uuid.uuid4()
        user_config = self.make_user_config(token="")
        script_config = MaaConfig()
        script_config.UserData = {user_id: user_config}
        accounts = self.AccountCollection()
        config = self.ConfigHarness()
        config.ScriptConfig = {script_id: script_config}
        config.ToolsConfig = SimpleNamespace(GameSign_Accounts=accounts)
        config._clear_game_sign_account_results = MagicMock()

        await config.update_user(
            str(script_id),
            str(user_id),
            {"Info": {"Name": "新用户", "IfSkland": True, "SklandToken": "new-token"}},
        )

        self.assertEqual(len(accounts), 1)
        account = next(iter(accounts.values()))
        account.set.assert_any_await("GameSignAccount", "SklandToken", "new-token")

    async def test_deleting_last_legacy_user_unlinks_tool_token(self) -> None:
        script_id = uuid.uuid4()
        user_id = uuid.uuid4()
        user_config = self.make_user_config(token="legacy-token")
        user_data = self.UserCollection({user_id: user_config})
        script_config = MaaConfig()
        script_config.UserData = user_data

        account_uid = uuid.uuid4()
        account = MagicMock()
        account.get.side_effect = lambda group, key: {
            ("GameSignAccount", "SklandToken"): "legacy-token",
        }.get((group, key), "")
        account.set = AsyncMock()
        accounts = self.AccountCollection({account_uid: account})

        config = self.ConfigHarness()
        config.ScriptConfig = {script_id: script_config}
        config.ToolsConfig = SimpleNamespace(GameSign_Accounts=accounts)
        config._clear_game_sign_account_results = MagicMock()

        await config.del_user(str(script_id), str(user_id))

        account.set.assert_any_await("GameSignAccount", "SklandToken", "")
        account.set.assert_any_await(
            "GameSignAccount", "LastSignDate", "2000-01-01"
        )
        config._clear_game_sign_account_results.assert_called_once_with(
            str(account_uid)
        )

    async def test_shared_legacy_token_is_not_unlinked_until_last_user_is_deleted(
        self,
    ) -> None:
        script_id = uuid.uuid4()
        first_user_id = uuid.uuid4()
        second_user_id = uuid.uuid4()
        first_user = self.make_user_config(token="shared-token")
        second_user = self.make_user_config(token="shared-token")
        user_data = self.UserCollection(
            {first_user_id: first_user, second_user_id: second_user}
        )
        script_config = MaaConfig()
        script_config.UserData = user_data

        account = MagicMock()
        account.get.side_effect = lambda group, key: {
            ("GameSignAccount", "SklandToken"): "shared-token",
        }.get((group, key), "")
        account.set = AsyncMock()
        accounts = self.AccountCollection({uuid.uuid4(): account})

        config = self.ConfigHarness()
        config.ScriptConfig = {script_id: script_config}
        config.ToolsConfig = SimpleNamespace(GameSign_Accounts=accounts)
        config._clear_game_sign_account_results = MagicMock()

        await config.del_user(str(script_id), str(first_user_id))

        account.set.assert_not_awaited()
        config._clear_game_sign_account_results.assert_not_called()

    async def test_clearing_shared_legacy_token_keeps_tool_account(self) -> None:
        script_id = uuid.uuid4()
        first_user_id = uuid.uuid4()
        second_user_id = uuid.uuid4()
        first_user = self.make_user_config(token="")
        second_user = self.make_user_config(token="shared-token")
        user_data = self.UserCollection(
            {first_user_id: first_user, second_user_id: second_user}
        )
        script_config = MaaConfig()
        script_config.UserData = user_data

        account = MagicMock()
        account.get.side_effect = lambda group, key: {
            ("GameSignAccount", "SklandToken"): "shared-token",
        }.get((group, key), "")
        account.set = AsyncMock()
        accounts = self.AccountCollection({uuid.uuid4(): account})
        config = self.ConfigHarness()
        config.ScriptConfig = {script_id: script_config}
        config.ToolsConfig = SimpleNamespace(GameSign_Accounts=accounts)
        config._clear_game_sign_account_results = MagicMock()

        await config._sync_legacy_skland_user(
            user_config=first_user,
            user_id=str(first_user_id),
            old_token="shared-token",
            token="",
            enabled=False,
        )

        account.set.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
