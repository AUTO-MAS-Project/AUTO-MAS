import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "cnb_trigger.py"
SPEC = importlib.util.spec_from_file_location("auto_mas_cnb_trigger", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load {MODULE_PATH}")
CNB_TRIGGER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CNB_TRIGGER)


class FakeResponse:
    def __init__(self, status: int, body: bytes):
        self.status = status
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self, limit: int) -> bytes:
        return self._body[:limit]


class CnbTriggerTests(unittest.TestCase):
    def test_success_uses_bounded_stdlib_request(self):
        response = FakeResponse(200, b'{"ok":true}')
        with patch.object(CNB_TRIGGER.urllib.request, "urlopen", return_value=response) as urlopen:
            result = CNB_TRIGGER.trigger_build(
                "test-token",
                branch="dev",
                runid="123",
                release_body="notes",
                version_tag="v6.0.0-alpha.1",
                is_prerelease="true",
            )

        self.assertEqual(result, {"ok": True})
        request = urlopen.call_args.args[0]
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 60)
        self.assertEqual(request.full_url, "https://api.cnb.cool/AUTO-MAS-Project/AUTO-MAS/-/build/start")
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.get_header("Authorization"), "test-token")
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["branch"], "dev")
        self.assertEqual(payload["env"]["RUN_ID"], "123")
        self.assertEqual(payload["env"]["VERSION_TAG"], "v6.0.0-alpha.1")

    def test_oversized_response_fails_closed(self):
        response = FakeResponse(200, b"x" * (1024 * 1024 + 1))
        with patch.object(CNB_TRIGGER.urllib.request, "urlopen", return_value=response):
            result = CNB_TRIGGER.trigger_build("test-token")

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
