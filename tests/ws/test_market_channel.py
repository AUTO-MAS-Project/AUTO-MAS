from __future__ import annotations

from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from app.core.ws import protocol
from app.models.schema import WSEnvelope
from app.plugins import market_channel


class TestPluginMarketChannel(IsolatedAsyncioTestCase):
    async def test_snapshot_response_keeps_request_correlation(self) -> None:
        publisher = AsyncMock(return_value=True)
        snapshot = {"items": [], "total": 0}
        envelope = WSEnvelope(
            id=protocol.ID_PLUGIN_MARKET,
            type=protocol.MARKET_SNAPSHOT_REQUEST,
            data={"requestId": "req-1", "perPrefixLimit": 42},
        )

        with (
            patch.object(
                market_channel,
                "fetch_market_snapshot",
                new=AsyncMock(return_value=snapshot),
            ) as fetch_snapshot,
            patch.object(market_channel.Publisher, "send", new=publisher),
        ):
            await market_channel._handle_snapshot_request(envelope)

        fetch_snapshot.assert_awaited_once()
        self.assertEqual(fetch_snapshot.await_args.kwargs["per_prefix_limit"], 42)
        publisher.assert_awaited_once_with(
            id=protocol.ID_PLUGIN_MARKET,
            type=protocol.MARKET_SNAPSHOT_RESPONSE,
            data={
                "requestId": "req-1",
                "status": "success",
                "message": "",
                "payload": snapshot,
            },
        )

    async def test_snapshot_failure_uses_canonical_error(self) -> None:
        publisher = AsyncMock(return_value=True)
        envelope = WSEnvelope(
            id=protocol.ID_PLUGIN_MARKET,
            type=protocol.MARKET_SNAPSHOT_REQUEST,
            data={"requestId": "req-failed"},
        )

        with (
            patch.object(
                market_channel,
                "fetch_market_snapshot",
                new=AsyncMock(side_effect=RuntimeError("offline")),
            ),
            patch.object(market_channel.Publisher, "send", new=publisher),
        ):
            await market_channel._handle_snapshot_request(envelope)

        call = publisher.await_args
        self.assertEqual(call.kwargs["type"], protocol.MARKET_ERROR)
        self.assertEqual(call.kwargs["data"]["requestId"], "req-failed")
        self.assertEqual(call.kwargs["data"]["status"], "error")
        self.assertIn("offline", call.kwargs["data"]["message"])

    async def test_install_emits_progress_result_and_installed_sync(self) -> None:
        publisher = AsyncMock(return_value=True)
        envelope = WSEnvelope(
            id=protocol.ID_PLUGIN_MARKET,
            type=protocol.PLUGIN_INSTALL_REQUEST,
            data={"requestId": "req-install", "package": "Demo-Plugin"},
        )

        with (
            patch.object(
                market_channel.PluginManager,
                "install_plugin_package",
                new=AsyncMock(),
            ) as install,
            patch.object(
                market_channel,
                "collect_installed_distribution_names",
                return_value={"demo_plugin"},
            ),
            patch.object(market_channel.Publisher, "send", new=publisher),
        ):
            await market_channel._handle_install_request(envelope)

        install.assert_awaited_once_with("Demo-Plugin")
        emitted_types = [call.kwargs["type"] for call in publisher.await_args_list]
        self.assertEqual(
            emitted_types,
            [
                protocol.PLUGIN_INSTALL_PROGRESS,
                protocol.PLUGIN_INSTALL_PROGRESS,
                protocol.PLUGIN_INSTALL_PROGRESS,
                protocol.PLUGIN_INSTALL_RESULT,
                protocol.PLUGIN_INSTALLED_SYNC,
            ],
        )
        self.assertEqual(
            publisher.await_args_list[-1].kwargs["data"]["payload"],
            {"package": "Demo-Plugin", "installed": True},
        )

    async def test_missing_package_is_rejected_without_install(self) -> None:
        publisher = AsyncMock(return_value=True)
        envelope = WSEnvelope(
            id=protocol.ID_PLUGIN_MARKET,
            type=protocol.PLUGIN_INSTALL_REQUEST,
            data={"requestId": "req-empty", "package": "  "},
        )

        with (
            patch.object(
                market_channel.PluginManager,
                "install_plugin_package",
                new=AsyncMock(),
            ) as install,
            patch.object(market_channel.Publisher, "send", new=publisher),
        ):
            await market_channel._handle_install_request(envelope)

        install.assert_not_awaited()
        self.assertEqual(publisher.await_args.kwargs["type"], protocol.MARKET_ERROR)


class TestPluginMarketRegistration(TestCase):
    def test_register_is_idempotent(self) -> None:
        previous = market_channel._registered
        market_channel._registered = False
        try:
            with patch.object(
                market_channel.Dispatcher,
                "register",
                return_value=lambda: None,
            ) as register:
                market_channel.register()
                market_channel.register()

            self.assertEqual(register.call_count, 4)
        finally:
            market_channel._registered = previous
