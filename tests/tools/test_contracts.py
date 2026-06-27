import unittest

from app.tools.game_sign import build_skland_sign_results
from app.tools.miyoushe import PASSPORT_COOKIE_URL


class GameSignContractTest(unittest.TestCase):
    def test_skland_results_include_community_fields(self) -> None:
        raw_result = {
            "arknights": {
                "成功": ["博士/博士(10001)"],
                "重复": [],
                "失败": [],
                "总计": 1,
            },
            "endfield": {
                "成功": [],
                "重复": ["管理员/管理员(20001)"],
                "失败": [],
                "总计": 1,
            },
        }

        results = build_skland_sign_results(
            raw_result,
            account_name="测试用户",
            account_uid="account-1",
        )

        self.assertEqual([item["platform"] for item in results], ["森空岛", "森空岛"])
        self.assertEqual([item["game"] for item in results], ["明日方舟", "终末地"])
        self.assertEqual([item["status"] for item in results], ["成功", "已签到"])
        self.assertTrue(all(item["account_uid"] == "account-1" for item in results))

    def test_skland_flat_failure_still_produces_community_result(self) -> None:
        raw_result = {
            "成功": [],
            "重复": [],
            "失败": ["认证失败"],
            "总计": 0,
        }

        results = build_skland_sign_results(
            raw_result,
            account_name="测试用户",
            account_uid="account-1",
        )

        self.assertEqual(results[0]["platform"], "森空岛")
        self.assertEqual(results[0]["status"], "失败")
        self.assertEqual(results[0]["reason"], "认证失败")

    def test_stoken_exchange_uses_passport_api_domain(self) -> None:
        self.assertEqual(
            PASSPORT_COOKIE_URL,
            "https://passport-api.mihoyo.com/account/auth/api/getCookieAccountInfoBySToken",
        )


if __name__ == "__main__":
    unittest.main()
