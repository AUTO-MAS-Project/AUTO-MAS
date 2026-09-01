import unittest
from unittest.mock import AsyncMock, patch

import app.api.qr_login as qr_login_api
import app.api.tools as tools_api


class CommunityErrorContractTest(unittest.IsolatedAsyncioTestCase):
    async def test_qr_create_hides_raw_exception_from_response_and_log(self) -> None:
        secret = "raw-secret-without-a-field-name"

        with patch(
            "app.tools.miyoushe_qr.create_qr_login",
            AsyncMock(side_effect=RuntimeError(secret)),
        ), patch.object(qr_login_api.logger, "warning") as warning:
            result = await qr_login_api.qr_create()

        self.assertEqual(result.code, 500)
        self.assertNotIn(secret, result.message)
        self.assertNotIn(secret, str(warning.call_args))
        self.assertIn("RuntimeError", str(warning.call_args))

    async def test_manual_sign_hides_raw_exception_from_response_and_log(self) -> None:
        secret = "raw-secret-without-a-field-name"

        with patch.object(
            tools_api,
            "run_community_sign_in",
            AsyncMock(side_effect=RuntimeError(secret)),
        ), patch.object(tools_api.logger, "warning") as warning:
            result = await tools_api.manual_game_sign()

        self.assertEqual(result.code, 500)
        self.assertNotIn(secret, result.message)
        self.assertNotIn(secret, str(warning.call_args))
        self.assertIn("RuntimeError", str(warning.call_args))


if __name__ == "__main__":
    unittest.main()
