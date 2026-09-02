import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import app.tools.community_sign_provider as community_sign_provider
import app.tools.game_sign as game_sign


class CommunitySignProviderCompatibilityTest(unittest.TestCase):
    def test_cloud_genshin_has_an_independent_credential_provider(self) -> None:
        providers = {
            provider.token_field: provider
            for provider in community_sign_provider.get_community_sign_providers()
        }

        cloud_genshin = providers["CloudGenshinToken"]
        self.assertEqual(cloud_genshin.log_name, "云原神")
        self.assertEqual(cloud_genshin.resolve_platforms("opaque-token"), ("米游社",))
        self.assertEqual(cloud_genshin.error_game("米游社"), "云原神")

    def test_legacy_registry_aliases_share_canonical_objects(self) -> None:
        self.assertIs(
            game_sign._GAME_SIGN_PROVIDERS,
            community_sign_provider._COMMUNITY_SIGN_PROVIDERS,
        )
        self.assertIs(
            game_sign.GAME_SIGN_TOKEN_FIELDS,
            community_sign_provider.COMMUNITY_TOKEN_FIELDS,
        )
        self.assertIs(
            game_sign._run_provider,
            community_sign_provider.run_community_provider,
        )

    def test_legacy_time_patch_is_forwarded_without_patching_asyncio_clock(self) -> None:
        time_source = object()
        implementation = AsyncMock()

        with patch.object(
            game_sign,
            "_check_community_system_time_impl",
            implementation,
        ), patch.object(game_sign, "time", time_source):
            asyncio.run(game_sign._check_system_time())

        implementation.assert_awaited_once_with(time_source=time_source)


if __name__ == "__main__":
    unittest.main()
