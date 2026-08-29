import unittest

from app.services.telemetry import sanitize_event


def _log_hint(exc_info=None):
    class _Record:
        pass

    record = _Record()
    record.exc_info = exc_info
    return {"log_record": record}


class SanitizeEventTest(unittest.TestCase):
    def test_masks_user_name_in_log_message(self):
        event = {
            "logentry": {
                "message": (
                    "程序自启动任务计划创建或更新失败\n"
                    r"  File \"C:\Users\alice\AppData\Roaming\Python\x.py\", line 1"
                )
            }
        }

        result = sanitize_event(event, _log_hint(exc_info=(None, None, None)))

        self.assertIsNotNone(result)
        message = result["logentry"]["message"]
        self.assertNotIn("alice", message)
        self.assertIn(r"C:\Users\<user>", message)

    def test_masks_user_name_in_formatted_and_params(self):
        event = {
            "logentry": {
                "formatted": r"打开 C:\Users\bob\Desktop\a.txt 失败",
                "params": [r"C:/Users/carol/tmp.xml", 42],
            }
        }

        result = sanitize_event(event, _log_hint(exc_info=(None, None, None)))

        self.assertNotIn("bob", result["logentry"]["formatted"])
        self.assertNotIn("carol", result["logentry"]["params"][0])
        self.assertEqual(result["logentry"]["params"][1], 42)

    def test_masks_user_name_in_repr_escaped_path(self):
        """Loguru 以 repr 渲染局部变量，路径分隔符是转义后的双反斜杠。"""

        event = {
            "logentry": {
                "message": (
                    r"-> ('schtasks', '/xml', 'C:\\Users\\erin\\AppData\\Temp\\t.xml')"
                )
            }
        }

        result = sanitize_event(event, _log_hint(exc_info=(None, None, None)))

        self.assertNotIn("erin", result["logentry"]["message"])

    def test_masks_user_name_in_exception_value(self):
        event = {
            "exception": {
                "values": [
                    {
                        "type": "PermissionError",
                        "value": r"[WinError 5] 拒绝访问。 C:\Users\dave\Temp\t.xml",
                    }
                ]
            }
        }

        result = sanitize_event(event, {})

        self.assertNotIn("dave", result["exception"]["values"][0]["value"])

    def test_keeps_paths_without_user_directory(self):
        event = {
            "logentry": {"message": r"读取 C:\Program Files\AUTO-MAS\main.py 失败"}
        }

        result = sanitize_event(event, {})

        self.assertIn(
            r"C:\Program Files\AUTO-MAS\main.py", result["logentry"]["message"]
        )

    def test_drops_log_event_without_exception(self):
        event = {"logentry": {"message": "连接明日方舟失败: 任务执行失败"}}

        self.assertIsNone(sanitize_event(event, _log_hint(exc_info=None)))

    def test_keeps_log_event_with_exception(self):
        event = {"logentry": {"message": "任务失败"}}

        self.assertIsNotNone(
            sanitize_event(event, _log_hint(exc_info=(None, None, None)))
        )

    def test_drops_non_actionable_exception(self):
        event = {
            "exception": {
                "values": [
                    {"type": "ConnectionResetError", "value": "[WinError 10054]"}
                ]
            }
        }

        self.assertIsNone(sanitize_event(event, {}))

    def test_keeps_chain_containing_actionable_exception(self):
        event = {
            "exception": {
                "values": [
                    {"type": "ConnectionResetError", "value": "[WinError 10054]"},
                    {"type": "ValueError", "value": "string too long"},
                ]
            }
        }

        self.assertIsNotNone(sanitize_event(event, {}))

    def test_keeps_exception_without_type(self):
        event = {"exception": {"values": [{"value": "未知异常"}]}}

        self.assertIsNotNone(sanitize_event(event, {}))


if __name__ == "__main__":
    unittest.main()
