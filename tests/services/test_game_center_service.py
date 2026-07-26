from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.models.game_center import (
    StoredGame,
    StoredGameData,
    StoredGameDataPatch,
    StoredGameInfo,
    StoredGameInfoPatch,
    StoredGamePatch,
    StoredGameTask,
)
from app.services import game_providers
from app.services.game_center import (
    GameCenterError,
    GameCenterPersistenceError,
    GameCenterService,
    GameCheckResult,
    GameProgressEvent,
    GameProvider,
    GameProviderDescriptor,
    GameProviderRegistry,
    JsonGameCenterRepository,
)
from app.services.game_presets import BUILTIN_GAME_PRESETS
from app.services.game_providers import (
    AdbApkGameProvider,
    register_builtin_game_providers,
)


class _Provider(GameProvider):
    descriptor = GameProviderDescriptor(
        name="test.provider",
        display_name="Test Provider",
        platforms=frozenset({"pc"}),
        capabilities=frozenset({"check", "launch", "close"}),
    )

    def __init__(self) -> None:
        self.actions: list[str] = []

    async def check(self, game):
        self.actions.append(f"check:{game.game_id}")
        return GameCheckResult(
            local_version="1.0",
            latest_version="1.1",
            needs_update=True,
            installed=True,
        )

    async def launch(self, game) -> None:
        self.actions.append(f"launch:{game.game_id}")

    async def close(self, game) -> None:
        self.actions.append(f"close:{game.game_id}")


class _InstallProvider(_Provider):
    descriptor = GameProviderDescriptor(
        name="test.provider",
        display_name="Test Provider",
        platforms=frozenset({"pc"}),
        capabilities=frozenset(
            {"check", "install_or_update", "launch", "close"}
        ),
    )

    def __init__(
        self,
        started: asyncio.Event,
        release: asyncio.Event,
        *,
        fail: bool = False,
    ) -> None:
        super().__init__()
        self.started = started
        self.release = release
        self.fail = fail

    async def install_or_update(
        self,
        game,
        progress,
        cancel_event,
    ) -> None:
        await progress(
            GameProgressEvent(
                phase="download",
                percent=42.0,
                downloaded=42,
                total=100,
                speed=10.0,
                message="fake download",
            )
        )
        self.started.set()
        if self.fail:
            raise RuntimeError("fake provider failed")
        await self.release.wait()
        if cancel_event.is_set():
            raise asyncio.CancelledError
        await progress(
            GameProgressEvent(
                phase="install",
                percent=100.0,
                message="fake install complete",
            )
        )
        return "completed"


def _run(coro):
    return asyncio.run(coro)


def _service(path: Path) -> GameCenterService:
    return GameCenterService(JsonGameCenterRepository(path))


def _game_patch(name: str, provider: str = "") -> StoredGamePatch:
    return StoredGamePatch(
        Info=StoredGameInfoPatch(
            Name=name,
            Platform="pc",
            Provider=provider,
        ),
        Data=StoredGameDataPatch(InstallPath=f"C:/{name}"),
    )


def test_crud_reorder_and_persistence_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "GameCenter.json"
    service = _service(path)

    first = _run(service.add_game(_game_patch("first")))
    second = _run(service.add_game(_game_patch("second")))
    updated = _run(
        service.update_game(
            first.game_id,
            StoredGamePatch(Info=StoredGameInfoPatch(Name="updated")),
            expected_revision=first.Revision,
        )
    )
    _run(service.reorder_games([second.game_id, first.game_id]))

    restarted = _service(path)
    order, games = _run(restarted.get_games())
    assert order == [second.game_id, first.game_id]
    assert games[first.game_id].Info.Name == "updated"
    assert games[first.game_id].Revision == updated.Revision

    _run(
        restarted.delete_game(
            second.game_id,
            expected_revision=second.Revision,
        )
    )
    assert _run(restarted.get_games())[0] == [first.game_id]


def test_revision_conflict_and_invalid_order_do_not_change_file(tmp_path: Path) -> None:
    path = tmp_path / "GameCenter.json"
    service = _service(path)
    game = _run(service.add_game(_game_patch("stable")))
    before = path.read_bytes()

    with pytest.raises(GameCenterError, match="已更新") as revision_error:
        _run(
            service.update_game(
                game.game_id,
                StoredGamePatch(Info=StoredGameInfoPatch(Name="stale")),
                expected_revision=game.Revision + 1,
            )
        )
    assert revision_error.value.code == 409
    assert path.read_bytes() == before

    with pytest.raises(GameCenterError, match="重复"):
        _run(service.reorder_games([game.game_id, game.game_id]))
    assert path.read_bytes() == before


def test_corrupt_state_is_preserved_and_blocks_writes(tmp_path: Path) -> None:
    path = tmp_path / "GameCenter.json"
    corrupt = b'{"version": 1, "order": ["lost"], "games": {}}'
    path.write_bytes(corrupt)
    service = _service(path)

    with pytest.raises(GameCenterPersistenceError, match="停止写入"):
        _run(service.add_game(_game_patch("must-not-overwrite")))

    assert path.read_bytes() == corrupt


def test_provider_registry_rejects_cross_owner_collision() -> None:
    registry = GameProviderRegistry()
    provider = _Provider()
    registry.register(provider, owner="plugin:a")
    registry.register(provider, owner="plugin:a")

    with pytest.raises(ValueError, match="其他插件"):
        registry.register(_Provider(), owner="plugin:b")

    registry.unregister_owner("plugin:a")
    assert registry.list() == []


def test_provider_actions_are_awaited_and_check_cache_is_persisted(
    tmp_path: Path,
) -> None:
    path = tmp_path / "GameCenter.json"
    provider = _Provider()
    service = _service(path)
    service.register_provider(provider, owner="plugin:test")
    game = _run(service.add_game(_game_patch("provided", "test.provider")))

    result = _run(service.check_game(game.game_id))
    assert result.needs_update is True
    assert _run(service.launch_game(game.game_id)) == "test.provider"
    assert _run(service.close_game(game.game_id)) == "test.provider"
    assert provider.actions == [
        f"check:{game.game_id}",
        f"launch:{game.game_id}",
        f"close:{game.game_id}",
    ]

    persisted = _run(_service(path).get_games(game.game_id))[1][game.game_id]
    assert persisted.Cache.LocalVersion == "1.0"
    assert persisted.Cache.LastChecked is not None
    assert persisted.Revision == game.Revision + 1


def test_missing_provider_never_reports_action_success(tmp_path: Path) -> None:
    service = _service(tmp_path / "GameCenter.json")
    game = _run(service.add_game(_game_patch("missing", "disabled.provider")))

    with pytest.raises(GameCenterError, match="当前不可用") as error:
        _run(service.launch_game(game.game_id))
    assert error.value.code == 503


def test_slow_check_blocks_conflicting_config_write(tmp_path: Path) -> None:
    class _SlowProvider(_Provider):
        def __init__(self, started: asyncio.Event, release: asyncio.Event) -> None:
            super().__init__()
            self.started = started
            self.release = release

        async def check(self, game):
            self.started.set()
            await self.release.wait()
            return await super().check(game)

    async def scenario() -> None:
        service = _service(tmp_path / "GameCenter.json")
        started = asyncio.Event()
        release = asyncio.Event()
        service.register_provider(
            _SlowProvider(started, release),
            owner="plugin:test",
        )
        game = await service.add_game(_game_patch("before", "test.provider"))

        check_task = asyncio.create_task(service.check_game(game.game_id))
        await started.wait()
        with pytest.raises(GameCenterError, match="已有操作") as conflict:
            await service.update_game(
                game.game_id,
                StoredGamePatch(Info=StoredGameInfoPatch(Name="after")),
                expected_revision=game.Revision,
            )
        assert conflict.value.code == 409
        release.set()
        await check_task

        current = (await service.get_games(game.game_id))[1][game.game_id]
        assert current.Info.Name == "before"
        assert current.Revision == game.Revision + 1
        assert current.Cache.LastChecked is not None

    _run(scenario())


def test_builtin_catalog_has_seven_presets_and_four_real_capability_descriptors(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path / "catalog.json")

    register_builtin_game_providers(service)

    assert len(BUILTIN_GAME_PRESETS) == 7
    providers = {item.provider.descriptor.name: item for item in service.list_providers()}
    assert set(providers) == {
        "local.pc",
        "mihoyo_pc",
        "hypergryph_pc",
        "adb_apk",
    }
    assert providers["local.pc"].provider.descriptor.capabilities == {
        "check",
        "launch",
        "close",
    }
    assert providers["adb_apk"].provider.descriptor.capabilities == {
        "check",
        "launch",
        "close",
    }
    for name in ("mihoyo_pc", "hypergryph_pc"):
        assert providers[name].provider.descriptor.capabilities == {
            "check",
            "install_or_update",
            "launch",
            "close",
        }


def test_adb_provider_check_launch_close_use_exact_serial_and_package(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    async def fake_run_adb(_adb_path: str, arguments: list[str]) -> str:
        calls.append(arguments)
        return "versionName=2.5.1"

    async def fake_resolve_device(
        _self,
        _game: StoredGame,
        *,
        start_if_offline: bool,
    ) -> str:
        return "127.0.0.1:16384"

    monkeypatch.setattr(game_providers, "_run_adb", fake_run_adb)
    monkeypatch.setattr(AdbApkGameProvider, "_resolve_device", fake_resolve_device)
    monkeypatch.setattr(
        AdbApkGameProvider,
        "_adb_path",
        lambda _self, _game: "adb.exe",
    )
    provider = AdbApkGameProvider()
    game = StoredGame(
        game_id="game-adb",
        Info=StoredGameInfo(
            Name="Arknights",
            Platform="emulator",
            Provider="adb_apk",
        ),
        Data=StoredGameData(PackageName="com.hypergryph.arknights"),
    )

    checked = _run(provider.check(game))
    _run(provider.launch(game))
    _run(provider.close(game))

    assert checked.local_version == "2.5.1"
    assert [call[3] for call in calls] == ["dumpsys", "monkey", "am"]
    assert all("com.hypergryph.arknights" in call for call in calls)


def test_install_task_is_exclusive_and_progress_survives_page_refresh(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        service = _service(tmp_path / "GameCenter.json")
        started = asyncio.Event()
        release = asyncio.Event()
        service.register_provider(
            _InstallProvider(started, release),
            owner="plugin:test",
        )
        game = await service.add_game(_game_patch("install", "test.provider"))

        created = await service.start_install_or_update(game.game_id)
        await started.wait()
        refreshed = (await service.get_operation_tasks(game.game_id))[game.game_id]

        assert created.status == "running"
        assert refreshed.status == "running"
        assert refreshed.phase == "download"
        assert refreshed.percent == 42.0
        assert refreshed.downloaded == 42
        with pytest.raises(GameCenterError, match="已有") as conflict:
            await service.start_install_or_update(game.game_id)
        assert conflict.value.code == 409
        with pytest.raises(GameCenterError, match="安装或更新"):
            await service.launch_game(game.game_id)

        release.set()
        while (
            await service.get_operation_tasks(game.game_id)
        )[game.game_id].status == "running":
            await asyncio.sleep(0)
        finished = (await service.get_operation_tasks(game.game_id))[game.game_id]
        assert finished.status == "completed"
        assert finished.phase == "completed"
        assert finished.percent == 100.0
        assert finished.message == "fake install complete"

    _run(scenario())


def test_cancel_waits_for_cancelled_terminal_and_never_reports_fake_success(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        service = _service(tmp_path / "GameCenter.json")
        started = asyncio.Event()
        release = asyncio.Event()
        service.register_provider(
            _InstallProvider(started, release),
            owner="plugin:test",
        )
        game = await service.add_game(_game_patch("cancel", "test.provider"))
        created = await service.start_install_or_update(game.game_id)
        await started.wait()

        cancelled = await service.cancel_operation(
            game.game_id,
            expected_task_id=created.task_id,
        )

        assert cancelled.status == "cancelled"
        assert cancelled.phase == "cancelled"
        assert cancelled.finished_at is not None
        with pytest.raises(GameCenterError, match="没有可取消") as duplicate:
            await service.cancel_operation(
                game.game_id,
                expected_task_id=created.task_id,
            )
        assert duplicate.value.code == 409

    _run(scenario())


def test_start_races_are_serialized_with_update_delete_and_reorder(
    tmp_path: Path,
) -> None:
    async def wait_terminal(
        service: GameCenterService,
        game_id: str,
    ) -> StoredGameTask:
        while True:
            task = (await service.get_operation_tasks(game_id)).get(game_id)
            if task is not None and task.status != "running":
                return task
            await asyncio.sleep(0)

    async def scenario() -> None:
        service = _service(tmp_path / "GameCenter.json")

        update_started = asyncio.Event()
        update_release = asyncio.Event()
        service.register_provider(
            _InstallProvider(update_started, update_release),
            owner="plugin:test",
        )
        update_game = await service.add_game(
            _game_patch("update-race", "test.provider")
        )
        start_result, update_result = await asyncio.gather(
            service.start_install_or_update(update_game.game_id),
            service.update_game(
                update_game.game_id,
                StoredGamePatch(Info=StoredGameInfoPatch(Name="updated")),
                expected_revision=update_game.Revision,
            ),
            return_exceptions=True,
        )
        await update_started.wait()
        assert not isinstance(start_result, Exception)
        if isinstance(update_result, GameCenterError):
            assert update_result.code == 409
        else:
            assert update_result.Info.Name == "updated"
        persisted_update = (await service.get_games(update_game.game_id))[1][
            update_game.game_id
        ]
        assert persisted_update.Info.Name == (
            "update-race" if isinstance(update_result, GameCenterError) else "updated"
        )
        assert (
            await service.get_operation_tasks(update_game.game_id)
        )[update_game.game_id].status == "running"
        update_release.set()
        assert (await wait_terminal(service, update_game.game_id)).status == "completed"

        delete_started = asyncio.Event()
        delete_release = asyncio.Event()
        service.providers.unregister_owner("plugin:test")
        service.register_provider(
            _InstallProvider(delete_started, delete_release),
            owner="plugin:test",
        )
        delete_game = await service.add_game(
            _game_patch("delete-race", "test.provider")
        )
        delete_start, delete_result = await asyncio.gather(
            service.start_install_or_update(delete_game.game_id),
            service.delete_game(
                delete_game.game_id,
                expected_revision=delete_game.Revision,
            ),
            return_exceptions=True,
        )
        if isinstance(delete_start, GameCenterError):
            assert delete_start.code == 404
            assert delete_result is None
            assert delete_game.game_id not in (await service.get_games())[1]
        else:
            await delete_started.wait()
            assert isinstance(delete_result, GameCenterError)
            assert delete_result.code == 409
            assert delete_game.game_id in (await service.get_games())[1]
            delete_release.set()
            assert (await wait_terminal(service, delete_game.game_id)).status == "completed"

        reorder_started = asyncio.Event()
        reorder_release = asyncio.Event()
        service.providers.unregister_owner("plugin:test")
        service.register_provider(
            _InstallProvider(reorder_started, reorder_release),
            owner="plugin:test",
        )
        reorder_game = await service.add_game(
            _game_patch("reorder-race", "test.provider")
        )
        order, _ = await service.get_games()
        desired_order = list(reversed(order))
        started_task, reordered = await asyncio.gather(
            service.start_install_or_update(reorder_game.game_id),
            service.reorder_games(desired_order),
        )
        await reorder_started.wait()
        assert started_task.status == "running"
        assert reordered is None
        assert (await service.get_games())[0] == desired_order
        assert (
            await service.get_operation_tasks(reorder_game.game_id)
        )[reorder_game.game_id].status == "running"
        reorder_release.set()
        assert (await wait_terminal(service, reorder_game.game_id)).status == "completed"

    _run(scenario())


def test_cancel_and_provider_completion_race_has_one_truthful_terminal_state(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        service = _service(tmp_path / "GameCenter.json")
        started = asyncio.Event()
        release = asyncio.Event()
        service.register_provider(
            _InstallProvider(started, release),
            owner="plugin:test",
        )
        game = await service.add_game(_game_patch("terminal-race", "test.provider"))
        created = await service.start_install_or_update(game.game_id)
        await started.wait()

        release.set()
        cancel_result = await asyncio.gather(
            service.cancel_operation(
                game.game_id,
                expected_task_id=created.task_id,
            ),
            return_exceptions=True,
        )
        final = (await service.get_operation_tasks(game.game_id))[game.game_id]

        assert final.status in {"completed", "cancelled"}
        assert final.phase == final.status
        assert final.finished_at is not None
        result = cancel_result[0]
        if isinstance(result, GameCenterError):
            assert result.code == 409
            assert final.status == "completed"
        else:
            assert result.status == "cancelled"
            assert final.status == "cancelled"

    _run(scenario())


def test_pc_install_or_update_hands_off_to_official_launcher_without_fake_patch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[str] = []
    progress: list[GameProgressEvent] = []

    monkeypatch.setattr(
        game_providers,
        "_open_official_launcher",
        lambda game: opened.append(game.game_id),
    )
    provider = game_providers.PcGameProvider(
        GameProviderDescriptor(
            name="hypergryph_pc",
            display_name="Hypergryph",
            platforms=frozenset({"pc"}),
            capabilities=frozenset({"install_or_update"}),
        )
    )
    game = StoredGame(
        game_id="game-safe-handoff",
        Info=StoredGameInfo(
            Name="Arknights: Endfield",
            Platform="pc",
            Provider="hypergryph_pc",
        ),
    )

    async def scenario() -> None:
        outcome = await provider.install_or_update(
            game,
            lambda event: _append_progress(progress, event),
            asyncio.Event(),
        )
        assert outcome == "handed_off"

    async def _append_progress(
        events: list[GameProgressEvent],
        event: GameProgressEvent,
    ) -> None:
        events.append(event)

    _run(scenario())

    assert opened == ["game-safe-handoff"]
    assert [event.phase for event in progress] == ["handoff", "handoff"]
    assert progress[-1].percent == 100.0
    assert "官方启动器" in progress[-1].message


def test_stale_cancel_cannot_cancel_a_newer_task(tmp_path: Path) -> None:
    async def scenario() -> None:
        service = _service(tmp_path / "GameCenter.json")
        first_started = asyncio.Event()
        first_release = asyncio.Event()
        service.register_provider(
            _InstallProvider(first_started, first_release),
            owner="plugin:test",
        )
        game = await service.add_game(_game_patch("stale-cancel", "test.provider"))
        first = await service.start_install_or_update(game.game_id)
        await first_started.wait()
        assert (
            await service.cancel_operation(
                game.game_id,
                expected_task_id=first.task_id,
            )
        ).status == "cancelled"

        second_started = asyncio.Event()
        second_release = asyncio.Event()
        service.providers.unregister_owner("plugin:test")
        service.register_provider(
            _InstallProvider(second_started, second_release),
            owner="plugin:test",
        )
        second = await service.start_install_or_update(game.game_id)
        await second_started.wait()

        with pytest.raises(GameCenterError, match="任务已变化") as stale:
            await service.cancel_operation(
                game.game_id,
                expected_task_id=first.task_id,
            )
        assert stale.value.code == 409
        current = (await service.get_operation_tasks(game.game_id))[game.game_id]
        assert current.task_id == second.task_id
        assert current.status == "running"

        cancelled = await service.cancel_operation(
            game.game_id,
            expected_task_id=second.task_id,
        )
        assert cancelled.task_id == second.task_id
        assert cancelled.status == "cancelled"

    _run(scenario())


def test_launcher_discovery_rejects_unlisted_launcher_like_executables(
    tmp_path: Path,
) -> None:
    untrusted = tmp_path / "community-super-launcher.exe"
    untrusted.write_bytes(b"not executable")
    game = StoredGame(
        game_id="game-untrusted-launcher",
        Info=StoredGameInfo(
            Name="Arknights: Endfield",
            Platform="pc",
            Provider="hypergryph_pc",
        ),
        Data=StoredGameData(InstallPath=str(tmp_path)),
    )

    with pytest.raises(GameCenterError, match="未找到官方启动器"):
        game_providers._find_official_launcher(game)


def test_install_failure_and_interrupted_restart_are_persisted(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        path = tmp_path / "GameCenter.json"
        service = _service(path)
        started = asyncio.Event()
        release = asyncio.Event()
        service.register_provider(
            _InstallProvider(started, release, fail=True),
            owner="plugin:test",
        )
        game = await service.add_game(_game_patch("failed", "test.provider"))
        await service.start_install_or_update(game.game_id)
        await started.wait()
        while (
            await service.get_operation_tasks(game.game_id)
        )[game.game_id].status == "running":
            await asyncio.sleep(0)

        failed = (await service.get_operation_tasks(game.game_id))[game.game_id]
        assert failed.status == "failed"
        assert failed.phase == "failed"
        assert failed.message == "fake provider failed"

        repository = JsonGameCenterRepository(path)
        state = repository.load()
        state.operations[game.game_id] = StoredGameTask(
            task_id="orphaned",
            game_id=game.game_id,
            message="still running",
        )
        repository.save(state)

        restarted = _service(path)
        interrupted = (await restarted.get_operation_tasks(game.game_id))[
            game.game_id
        ]
        assert interrupted.status == "failed"
        assert interrupted.phase == "failed"
        assert "中断" in interrupted.message

    _run(scenario())
