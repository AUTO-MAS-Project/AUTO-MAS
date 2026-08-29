import unittest

from app.MaaFW.ArknightWin32 import (
    CONNECT_RETRY_BASE_SECONDS,
    CONNECT_RETRY_MAX_SECONDS,
    connect_retry_delay,
)


class ConnectRetryDelayTest(unittest.TestCase):
    def test_first_failure_waits_base_interval(self):
        self.assertEqual(connect_retry_delay(1), CONNECT_RETRY_BASE_SECONDS)

    def test_delay_grows_exponentially(self):
        self.assertEqual(connect_retry_delay(2), CONNECT_RETRY_BASE_SECONDS * 2)
        self.assertEqual(connect_retry_delay(3), CONNECT_RETRY_BASE_SECONDS * 4)

    def test_delay_is_capped(self):
        self.assertEqual(connect_retry_delay(100), CONNECT_RETRY_MAX_SECONDS)

    def test_delay_never_below_base(self):
        """失败次数异常传 0 或负数时不应退化成 0 秒间隔。"""

        self.assertEqual(connect_retry_delay(0), CONNECT_RETRY_BASE_SECONDS)
        self.assertEqual(connect_retry_delay(-5), CONNECT_RETRY_BASE_SECONDS)


if __name__ == "__main__":
    unittest.main()
