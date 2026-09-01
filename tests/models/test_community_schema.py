import unittest

from pydantic import SecretStr, ValidationError

from app.models.schema import (
    GameSignAccountsListOut,
    KuroSmsLoginIn,
    KuroSmsSendIn,
)


class CommunitySchemaTest(unittest.TestCase):
    def test_account_list_accepts_order_and_dynamic_account_entries(self) -> None:
        response = GameSignAccountsListOut(
            data={
                "instances": [
                    {"uid": "account-1", "type": "GameSignAccountGroup"}
                ],
                "account-1": {
                    "GameSignAccount": {
                        "Name": "账号A",
                        "Enabled": True,
                        "LastSignDate": "2026-09-01",
                    }
                },
            }
        )

        data = response.model_dump()["data"]
        self.assertEqual(data["instances"][0]["uid"], "account-1")
        self.assertEqual(
            data["account-1"]["GameSignAccount"]["Name"],
            "账号A",
        )
        self.assertEqual(
            data["account-1"]["GameSignAccount"]["LastSignDate"],
            "2026-09-01",
        )

    def test_kuro_sms_contract_normalizes_phone_and_keeps_code_secret(self) -> None:
        request = KuroSmsLoginIn(
            accountId="account-1",
            sessionId="session-1",
            phone=" 13800138000 ",
            code=SecretStr("123456"),
        )

        self.assertEqual(request.phone, "13800138000")
        self.assertEqual(request.code.get_secret_value(), "123456")
        self.assertNotIn("123456", repr(request))

    def test_kuro_sms_contract_rejects_non_mobile_or_non_numeric_code(self) -> None:
        with self.assertRaises(ValidationError):
            KuroSmsSendIn(accountId="account-1", phone="1380013800")
        with self.assertRaises(ValidationError):
            KuroSmsLoginIn(
                accountId="account-1",
                sessionId="session-1",
                phone="13800138000",
                code="12ab56",
            )


if __name__ == "__main__":
    unittest.main()
