import unittest
from unittest.mock import AsyncMock, patch


class QrLoginApiTest(unittest.IsolatedAsyncioTestCase):
    async def test_check_maps_empty_helper_result_to_stable_error(self) -> None:
        from app.api.qr_login import QrCheckIn, qr_check

        with patch(
            "app.tools.miyoushe_qr.check_qr_status",
            new=AsyncMock(return_value=None),
        ):
            result = await qr_check(QrCheckIn(ticket="ticket", device="device"))

        self.assertEqual(result.code, 500)
        self.assertEqual(result.status, "error")
        self.assertEqual(result.message, "二维码状态响应格式无效")


if __name__ == "__main__":
    unittest.main()
