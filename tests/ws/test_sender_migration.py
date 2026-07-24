from __future__ import annotations

import ast
from pathlib import Path
from unittest import TestCase


MIGRATED_SOURCE_ROOTS = (
    Path("app/task"),
    Path("app/MaaFW"),
    Path("app/plugins"),
    Path("plugins/ok_script_adapter/src"),
    Path("plugins/okww_adapter/src"),
)


class TestWebSocketSenderMigration(TestCase):
    def test_host_and_bundled_plugins_do_not_call_legacy_sender(self) -> None:
        remaining: list[str] = []

        for root in MIGRATED_SOURCE_ROOTS:
            for source_path in root.rglob("*.py"):
                tree = ast.parse(
                    source_path.read_text(encoding="utf-8"),
                    filename=str(source_path),
                )
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call):
                        continue
                    if not isinstance(node.func, ast.Attribute):
                        continue
                    if node.func.attr != "send_websocket_message":
                        continue
                    remaining.append(f"{source_path}:{node.lineno}")

        self.assertEqual(
            remaining,
            [],
            "宿主或随包官方插件重新调用了 Legacy WS 发送器: "
            + ", ".join(remaining),
        )

    def test_legacy_bridge_remains_for_external_plugins(self) -> None:
        config_tree = ast.parse(
            Path("app/core/config.py").read_text(encoding="utf-8")
        )
        legacy_tree = ast.parse(
            Path("app/core/ws/legacy.py").read_text(encoding="utf-8")
        )

        config_functions = {
            node.name
            for node in ast.walk(config_tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        legacy_functions = {
            node.name
            for node in ast.walk(legacy_tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

        self.assertIn("send_websocket_message", config_functions)
        self.assertIn("send_websocket_message", legacy_functions)

    def test_plugin_market_uses_the_shared_main_connection(self) -> None:
        source = Path("frontend/src/views/PluginMarket.vue").read_text(encoding="utf-8")

        self.assertIn("useWebSocket", source)
        self.assertNotIn("new WebSocket", source)
        self.assertNotIn("/api/ws/plugin", source)
