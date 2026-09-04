import unittest

from app.models.schema import GameSignAccountsListOut


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

if __name__ == "__main__":
    unittest.main()
