import asyncio
import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.plugins import EventBus
from app.plugins.event_bus import EventDispatchError


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _run_authoritative_import(
    source: str,
    *,
    cwd: Path = REPOSITORY_ROOT,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(REPOSITORY_ROOT)
    environment["AUTO_MAS_CONFIG_V2_MODE"] = "authoritative"
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(source)],
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


class EventBusTest(unittest.TestCase):
    def setUp(self) -> None:
        self.bus = EventBus()

    def _run(self, coro):
        return asyncio.run(coro)

    def test_emit_dispatches_by_priority_order(self) -> None:
        order: list[str] = []

        async def scenario():
            self.bus.on("task.start", lambda _: order.append("low"), priority=0)
            self.bus.on("task.start", lambda _: order.append("high"), priority=10)
            await self.bus.emit("task.start", {})

        self._run(scenario())
        self.assertEqual(order, ["high", "low"])

    def test_once_listener_removed_after_first_emit(self) -> None:
        hits: list[int] = []

        async def scenario():
            self.bus.on("task.start", lambda _: hits.append(1), once=True)
            await self.bus.emit("task.start", {})
            await self.bus.emit("task.start", {})

        self._run(scenario())
        self.assertEqual(hits, [1])
        self.assertEqual(self.bus.handler_count, {})

    def test_instance_scope_routes_by_instance_id(self) -> None:
        hits: list[str] = []

        async def scenario():
            self.bus.on(
                "script.exit",
                lambda _: hits.append("a"),
                scope="instance",
                owner_instance_id="ins-a",
            )
            self.bus.on(
                "script.exit",
                lambda _: hits.append("b"),
                scope="instance",
                owner_instance_id="ins-b",
            )
            self.bus.on("script.exit", lambda _: hits.append("global"))
            await self.bus.emit(
                "script.exit", {}, scope="instance", source_instance_id="ins-a"
            )

        self._run(scenario())
        self.assertEqual(hits, ["a"])

    def test_global_scope_skips_instance_listeners(self) -> None:
        hits: list[str] = []

        async def scenario():
            self.bus.on(
                "script.exit",
                lambda _: hits.append("instance"),
                scope="instance",
                owner_instance_id="ins-a",
            )
            self.bus.on("script.exit", lambda _: hits.append("global"))
            await self.bus.emit("script.exit", {})

        self._run(scenario())
        self.assertEqual(hits, ["global"])

    def test_continue_policy_swallows_handler_error(self) -> None:
        hits: list[str] = []

        def bad_handler(_):
            raise RuntimeError("boom")

        async def scenario():
            self.bus.on("task.exit", bad_handler, priority=10)
            self.bus.on("task.exit", lambda _: hits.append("ok"))
            await self.bus.emit("task.exit", {}, error_policy="continue")

        self._run(scenario())
        self.assertEqual(hits, ["ok"])

    def test_raise_policy_aggregates_errors(self) -> None:
        def bad_handler(_):
            raise RuntimeError("boom")

        async def scenario():
            self.bus.on("task.exit", bad_handler)
            await self.bus.emit("task.exit", {}, error_policy="raise")

        with self.assertRaises(EventDispatchError):
            self._run(scenario())

    def test_off_by_listener_id(self) -> None:
        hits: list[int] = []

        async def scenario():
            listener_id = self.bus.on("task.start", lambda _: hits.append(1))
            self.bus.off("task.start", listener_id=listener_id)
            await self.bus.emit("task.start", {})

        self._run(scenario())
        self.assertEqual(hits, [])

    def test_off_by_instance_unbinds_all(self) -> None:
        hits: list[int] = []

        async def scenario():
            self.bus.on(
                "task.start",
                lambda _: hits.append(1),
                scope="instance",
                owner_instance_id="ins-a",
            )
            self.bus.on(
                "task.exit",
                lambda _: hits.append(2),
                scope="instance",
                owner_instance_id="ins-a",
            )
            self.bus.off_by_instance("ins-a")
            await self.bus.emit(
                "task.start", {}, scope="instance", source_instance_id="ins-a"
            )
            await self.bus.emit(
                "task.exit", {}, scope="instance", source_instance_id="ins-a"
            )

        self._run(scenario())
        self.assertEqual(hits, [])
        self.assertEqual(self.bus.handler_count, {})

    def test_duplicate_registration_returns_existing_id(self) -> None:
        def handler(_):
            pass

        first = self.bus.on("task.start", handler)
        second = self.bus.on("task.start", handler, priority=99)
        self.assertEqual(first, second)
        self.assertEqual(self.bus.handler_count, {"task.start": 1})

    def test_async_handler_supported(self) -> None:
        hits: list[int] = []

        async def async_handler(_):
            hits.append(1)

        async def scenario():
            self.bus.on("task.start", async_handler)
            await self.bus.emit("task.start", {})

        self._run(scenario())
        self.assertEqual(hits, [1])

    def test_instance_emit_requires_source_id(self) -> None:
        async def scenario():
            await self.bus.emit("task.start", {}, scope="instance")

        with self.assertRaises(ValueError):
            self._run(scenario())


class AuthoritativeImportBoundaryTest(unittest.TestCase):
    def test_lightweight_exports_do_not_load_legacy_config(self) -> None:
        result = _run_authoritative_import(
            """
            import sys
            import app.plugins as plugins

            blocked = (
                "app.core.config",
                "app.models.ConfigBase",
                "app.models.config",
            )
            assert set(plugins.__all__) == set(plugins._LAZY_EXPORTS)
            assert not any(name in sys.modules for name in blocked)

            from app.plugins import (
                EventBus,
                PluginConfigStore,
                PluginEventFactory,
                PluginEventNames,
            )

            assert EventBus is not None
            assert PluginConfigStore is not None
            assert PluginEventFactory is not None
            assert PluginEventNames is not None
            assert not any(name in sys.modules for name in blocked)
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_plugin_manager_import_isolated_from_worktree(self) -> None:
        # PluginManager creates runtime paths from cwd.  Put the child process
        # in a disposable directory so this import boundary test neither
        # writes to the worktree nor keeps a Windows log handle open during
        # directory cleanup.
        with TemporaryDirectory(prefix="automas-plugin-manager-") as directory:
            result = _run_authoritative_import(
                """
                import sys

                from app.plugins import PluginManager

                assert PluginManager is not None
                assert "app.core.config" not in sys.modules
                assert "app.models.ConfigBase" not in sys.modules
                assert "app.models.config" not in sys.modules
                """,
                cwd=Path(directory),
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_setting_router_does_not_eagerly_load_legacy_webhook_model(self) -> None:
        result = _run_authoritative_import(
            """
            import sys

            import app.api.setting

            assert "app.core.config" not in sys.modules
            assert "app.models.ConfigBase" not in sys.modules
            assert "app.models.config" not in sys.modules
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_non_task_api_routes_keep_authoritative_import_boundary(self) -> None:
        # These routes are part of normal app assembly but do not need the
        # legacy TaskManager.  Keep their imports independent from the two
        # remaining task-runtime migration blockers (core and dispatch).
        result = _run_authoritative_import(
            """
            import importlib
            import sys

            for module_name in (
                "app.api.info",
                "app.api.scripts",
                "app.api.scripts2",
                "app.api.websocket",
                "app.api.plugins",
                "app.api.setting",
            ):
                importlib.import_module(module_name)

            assert "app.core.config" not in sys.modules
            assert "app.models.ConfigBase" not in sys.modules
            assert "app.models.config" not in sys.modules
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_task_manager_and_dispatch_router_are_import_safe(self) -> None:
        """Router assembly must not bind ConfigBase before a task is started."""

        result = _run_authoritative_import(
            """
            import sys

            import app.api.core
            import app.api.dispatch
            from app.core import TaskManager

            assert TaskManager is not None
            assert "app.core.config" not in sys.modules
            assert "app.models.ConfigBase" not in sys.modules
            assert "app.models.config" not in sys.modules
            assert "app.core.script_types" not in sys.modules
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_authoritative_task_dispatch_fails_closed_before_runner_import(self) -> None:
        result = _run_authoritative_import(
            """
            import asyncio
            import sys

            from app.core import TaskManager
            from app.core.task_manager import TaskRuntimeUnavailableError

            async def main():
                try:
                    await TaskManager.add_task(
                        "AutoProxy", "00000000-0000-0000-0000-000000000000"
                    )
                except TaskRuntimeUnavailableError:
                    return
                raise AssertionError("authoritative task dispatch unexpectedly proceeded")

            asyncio.run(main())
            assert "app.core.config" not in sys.modules
            assert "app.models.ConfigBase" not in sys.modules
            assert "app.models.config" not in sys.modules
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_dispatch_api_reports_authoritative_gate_as_unavailable(self) -> None:
        result = _run_authoritative_import(
            """
            import asyncio
            import sys

            from app.api.dispatch import add_task
            from app.models.schema import TaskCreateIn

            response = asyncio.run(
                add_task(
                    TaskCreateIn(
                        mode="AutoProxy",
                        taskId="00000000-0000-0000-0000-000000000000",
                    )
                )
            )
            assert response.code == 503, response
            assert response.status == "unavailable", response
            assert response.taskId == "", response
            assert "app.core.config" not in sys.modules
            assert "app.models.ConfigBase" not in sys.modules
            assert "app.models.config" not in sys.modules
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_authoritative_timer_uses_native_runtime_without_legacy_import(
        self,
    ) -> None:
        with TemporaryDirectory(prefix="automas-native-timer-") as directory:
            result = _run_authoritative_import(
                """
                import asyncio
                import sys
                from unittest.mock import AsyncMock, patch

                from app.core import Config, MainTimer

                async def main():
                    await Config.init_config()
                    try:
                        with (
                            patch.object(MainTimer, "second_task", AsyncMock()),
                            patch.object(MainTimer, "hour_task", AsyncMock()),
                        ):
                            await MainTimer.start()
                            assert MainTimer.started is True
                            await MainTimer.stop()
                            assert MainTimer.started is False
                    finally:
                        Config.close()

                asyncio.run(main())
                assert "app.core.config" not in sys.modules
                assert "app.models.ConfigBase" not in sys.modules
                assert "app.models.config" not in sys.modules
                """,
                cwd=Path(directory),
            )
        self.assertEqual(result.returncode, 0, result.stderr)
    def test_authoritative_legacy_script_routes_support_static_crud_contract(self) -> None:
        """The established /api/scripts transport works for native static roots."""

        # The child writes its debug log under this disposable working
        # directory.  Parent-side cleanup happens only after the child exits,
        # avoiding Windows file-handle races from loguru's queued sink.
        with TemporaryDirectory(prefix="automas-native-script-api-") as directory:
            result = _run_authoritative_import(
                """
                import asyncio

                from app.api import scripts
                from app.core import Config
                from app.models.schema import (
                    ScriptCreateIn,
                    ScriptDeleteIn,
                    ScriptGetIn,
                    ScriptReorderIn,
                    ScriptUpdateIn,
                    UserDeleteIn,
                    UserGetIn,
                    UserInBase,
                    UserReorderIn,
                    UserUpdateIn,
                )

                async def main():
                    await Config.init_config()
                    try:
                        created = await scripts.add_script(ScriptCreateIn(type="MAA"))
                        assert created.code == 200, created
                        assert created.scriptId
                        assert created.data.Info["Name"] == "新 MAA 脚本"

                        fetched = await scripts.get_script(
                            ScriptGetIn(scriptId=created.scriptId)
                        )
                        assert fetched.code == 200, fetched
                        assert len(fetched.index) == 1
                        assert fetched.index[0].uid == created.scriptId
                        assert fetched.index[0].type == "MaaConfig"

                        user = await scripts.add_user(
                            UserInBase(scriptId=created.scriptId)
                        )
                        assert user.code == 200, user
                        users = await scripts.get_user(
                            UserGetIn(scriptId=created.scriptId)
                        )
                        assert users.code == 200, users
                        assert len(users.index) == 1
                        assert users.index[0].uid == user.userId
                        assert users.index[0].type == "MaaUserConfig"

                        updated_user = await scripts.update_user(
                            UserUpdateIn(
                                scriptId=created.scriptId,
                                userId=user.userId,
                                data=user.data,
                            )
                        )
                        assert updated_user.code == 200, updated_user
                        reordered_user = await scripts.reorder_user(
                            UserReorderIn(
                                scriptId=created.scriptId,
                                indexList=[user.userId],
                            )
                        )
                        assert reordered_user.code == 200, reordered_user
                        deleted_user = await scripts.delete_user(
                            UserDeleteIn(
                                scriptId=created.scriptId,
                                userId=user.userId,
                            )
                        )
                        assert deleted_user.code == 200, deleted_user

                        updated_script = await scripts.update_script(
                            ScriptUpdateIn(
                                scriptId=created.scriptId,
                                data=created.data,
                            )
                        )
                        assert updated_script.code == 200, updated_script
                        reordered_script = await scripts.reorder_script(
                            ScriptReorderIn(indexList=[created.scriptId])
                        )
                        assert reordered_script.code == 200, reordered_script
                        deleted_script = await scripts.delete_script(
                            ScriptDeleteIn(scriptId=created.scriptId)
                        )
                        assert deleted_script.code == 200, deleted_script
                    finally:
                        Config.close()

                asyncio.run(main())
                """,
                cwd=Path(directory),
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_authoritative_queue_routes_support_nested_collection_contract(self) -> None:
        """Queue, TimeSet and QueueItem routes use the native nested roots."""

        with TemporaryDirectory(prefix="automas-native-queue-api-") as directory:
            result = _run_authoritative_import(
                """
                import asyncio

                from app.api import queue as queue_api
                from app.core import Config
                from app.models.schema import (
                    QueueGetIn,
                    QueueItemGetIn,
                    QueueSetInBase,
                    TimeSetGetIn,
                )

                async def main():
                    await Config.init_config()
                    try:
                        queue = await queue_api.add_queue()
                        assert queue.code == 200, queue
                        assert queue.queueId

                        queues = await queue_api.get_queues(
                            QueueGetIn(queueId=queue.queueId)
                        )
                        assert queues.code == 200, queues
                        assert queues.index[0].uid == queue.queueId
                        assert queues.index[0].type == "QueueConfig"

                        time_set = await queue_api.add_time_set(
                            QueueSetInBase(queueId=queue.queueId)
                        )
                        assert time_set.code == 200, time_set
                        time_sets = await queue_api.get_time_set(
                            TimeSetGetIn(queueId=queue.queueId)
                        )
                        assert time_sets.code == 200, time_sets
                        assert time_sets.index[0].uid == time_set.timeSetId
                        assert time_sets.index[0].type == "TimeSet"

                        item = await queue_api.add_item(
                            QueueSetInBase(queueId=queue.queueId)
                        )
                        assert item.code == 200, item
                        items = await queue_api.get_item(
                            QueueItemGetIn(queueId=queue.queueId)
                        )
                        assert items.code == 200, items
                        assert items.index[0].uid == item.queueItemId
                        assert items.index[0].type == "QueueItem"
                    finally:
                        Config.close()

                asyncio.run(main())
                """,
                cwd=Path(directory),
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_authoritative_plan_routes_support_native_plan_root(self) -> None:
        with TemporaryDirectory(prefix="automas-native-plan-api-") as directory:
            result = _run_authoritative_import(
                """
                import asyncio

                from app.api import plan as plan_api
                from app.core import Config
                from app.models.schema import PlanCreateIn, PlanGetIn

                async def main():
                    await Config.init_config()
                    try:
                        created = await plan_api.add_plan(PlanCreateIn(type="MaaPlan"))
                        assert created.code == 200, created
                        assert created.planId
                        assert created.data.Info.Name == "新 MAA 计划表"

                        fetched = await plan_api.get_plan(
                            PlanGetIn(planId=created.planId)
                        )
                        assert fetched.code == 200, fetched
                        assert len(fetched.index) == 1
                        assert fetched.index[0].uid == created.planId
                        assert fetched.index[0].type == "MaaPlanConfig"
                    finally:
                        Config.close()

                asyncio.run(main())
                """,
                cwd=Path(directory),
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_authoritative_setting_and_global_webhook_routes_use_native_roots(self) -> None:
        with TemporaryDirectory(prefix="automas-native-setting-api-") as directory:
            result = _run_authoritative_import(
                """
                import asyncio

                from app.api import setting as setting_api
                from app.core import Config
                from app.models.schema import WebhookGetIn

                async def main():
                    await Config.init_config()
                    try:
                        setting = await setting_api.get_scripts()
                        assert setting.code == 200, setting
                        assert setting.data.Function is not None

                        created = await setting_api.add_webhook()
                        assert created.code == 200, created
                        assert created.webhookId
                        fetched = await setting_api.get_webhook(WebhookGetIn())
                        assert fetched.code == 200, fetched
                        assert len(fetched.index) == 1
                        assert fetched.index[0].uid == created.webhookId
                        assert fetched.index[0].type == "Webhook"
                    finally:
                        Config.close()

                asyncio.run(main())
                """,
                cwd=Path(directory),
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_authoritative_manual_game_sign_uses_native_root_without_legacy_import(
        self,
    ) -> None:
        """The native signer boundary must not instantiate ConfigBase."""

        with TemporaryDirectory(prefix="automas-native-game-sign-run-") as directory:
            result = _run_authoritative_import(
                """
                import asyncio
                import sys
                from unittest.mock import AsyncMock, patch

                from app.api import tools
                from app.core import Config

                async def main():
                    await Config.init_config()
                    try:
                        with patch(
                            "app.tools.game_sign.run_all_sign_in",
                            AsyncMock(return_value=[]),
                        ):
                            response = await tools.manual_game_sign()
                        assert response.code == 200, response
                        assert response.status == "success", response
                    finally:
                        Config.close()

                asyncio.run(main())
                assert "app.core.config" not in sys.modules
                assert "app.models.ConfigBase" not in sys.modules
                assert "app.models.config" not in sys.modules
                """,
                cwd=Path(directory),
            )
        self.assertEqual(result.returncode, 0, result.stderr)
    def test_authoritative_game_sign_account_routes_use_native_root_only(
        self,
    ) -> None:
        """Account CRUD remains usable while the native signer stays gated.

        This deliberately exercises only the configuration surface in a
        disposable directory.  It must never start a real sign-in, QR flow,
        network client, or legacy ``ConfigBase`` runtime.
        """

        with TemporaryDirectory(prefix="automas-native-game-sign-api-") as directory:
            result = _run_authoritative_import(
                """
                import asyncio
                import sys

                from app.api import tools
                from app.core import Config
                from app.models.schema import (
                    GameSignAccountDeleteIn,
                    GameSignAccountGetIn,
                    GameSignAccountReorderIn,
                    GameSignAccountGroupConfig,
                    GameSignAccountUpdateIn,
                )

                async def main():
                    await Config.init_config()
                    try:
                        created = await tools.add_game_sign_account()
                        assert created.code == 200, created
                        assert created.accountId
                        assert created.data.Name == "用户 1", created

                        listed = await tools.list_game_sign_accounts()
                        assert listed.code == 200, listed
                        assert listed.data["instances"] == [
                            {
                                "uid": created.accountId,
                                "type": "GameSignAccountGroup",
                            }
                        ], listed

                        fetched = await tools.get_game_sign_account(
                            GameSignAccountGetIn(accountId=created.accountId)
                        )
                        assert fetched.code == 200, fetched
                        assert fetched.data.Name == "用户 1", fetched

                        # A token field is accepted as an explicit empty
                        # value.  It also verifies that native ToolsConfig's
                        # in-memory result cache is cleared without loading
                        # the legacy signer.
                        Config.ToolsConfig._game_sign_result_data = {
                            "米游社": [
                                {"account_uid": created.accountId},
                                {"account_uid": "another-account"},
                            ]
                        }
                        updated = await tools.update_game_sign_account(
                            GameSignAccountUpdateIn(
                                accountId=created.accountId,
                                data=GameSignAccountGroupConfig(
                                    Name="native account",
                                    MiyousheToken="",
                                ),
                            )
                        )
                        assert updated.code == 200, updated
                        assert Config.ToolsConfig._game_sign_result_data == {
                            "米游社": [{"account_uid": "another-account"}]
                        }

                        fetched = await tools.get_game_sign_account(
                            GameSignAccountGetIn(accountId=created.accountId)
                        )
                        assert fetched.data.Name == "native account", fetched

                        reordered = await tools.reorder_game_sign_accounts(
                            GameSignAccountReorderIn(order=[created.accountId])
                        )
                        assert reordered.code == 200, reordered
                        deleted = await tools.delete_game_sign_account(
                            GameSignAccountDeleteIn(accountId=created.accountId)
                        )
                        assert deleted.code == 200, deleted
                    finally:
                        Config.close()

                asyncio.run(main())
                assert "app.tools.game_sign" not in sys.modules
                assert "app.core.config" not in sys.modules
                assert "app.models.ConfigBase" not in sys.modules
                """,
                cwd=Path(directory),
            )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
