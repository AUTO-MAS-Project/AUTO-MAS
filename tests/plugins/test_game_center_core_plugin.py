from __future__ import annotations

from pathlib import Path

from app.plugins.event_bus import EventBus
from app.plugins.loader import (
    GAME_CENTER_SERVICE_NAME,
    HOST_GAME_CENTER_OWNER,
    PluginLoader,
)
from app.plugins.service_registry import ServiceRegistry
from app.services.game_center import (
    GameCenterService,
    GameProvider,
    GameProviderDescriptor,
    get_default_game_center_service,
)


def _loader(tmp_path: Path) -> PluginLoader:
    return PluginLoader(
        EventBus(),
        plugins_dir=tmp_path / "plugins",
        service=ServiceRegistry(),
    )


def test_host_publishes_typed_game_center_service(tmp_path: Path) -> None:
    loader = _loader(tmp_path)

    loader._configure_host_compat_services({})

    service = loader.service.get(GAME_CENTER_SERVICE_NAME)
    assert loader.service.owners(GAME_CENTER_SERVICE_NAME) == {
        HOST_GAME_CENTER_OWNER
    }
    assert isinstance(service, GameCenterService)
    assert service is get_default_game_center_service()


def test_real_game_center_provider_replaces_host_without_collision(
    tmp_path: Path,
) -> None:
    loader = _loader(tmp_path)
    loader._configure_host_compat_services({})
    real = object()
    meta_map = {
        "game-center:real": ({GAME_CENTER_SERVICE_NAME}, set(), set()),
    }

    loader._configure_host_compat_services(meta_map)
    loader.service.set(GAME_CENTER_SERVICE_NAME, real, "game-center:real")

    assert loader.service.get(GAME_CENTER_SERVICE_NAME) is real
    assert HOST_GAME_CENTER_OWNER not in loader.service.owners(
        GAME_CENTER_SERVICE_NAME
    )


def test_failed_real_provider_restores_host_service(tmp_path: Path) -> None:
    loader = _loader(tmp_path)

    loader._restore_host_game_center_after_provider_failure(
        {GAME_CENTER_SERVICE_NAME}
    )

    assert loader.service.owners(GAME_CENTER_SERVICE_NAME) == {
        HOST_GAME_CENTER_OWNER
    }


def test_extension_provider_is_removed_with_plugin_owner(tmp_path: Path) -> None:
    class ExtensionProvider(GameProvider):
        descriptor = GameProviderDescriptor(
            name="extension.game",
            display_name="Extension",
            platforms=frozenset({"pc"}),
            capabilities=frozenset({"check"}),
        )

    loader = _loader(tmp_path)
    loader._configure_host_compat_services({})
    service = loader.service.get(GAME_CENTER_SERVICE_NAME)
    assert isinstance(service, GameCenterService)
    service.register_provider(ExtensionProvider(), owner="plugin:extension")

    loader._unregister_game_provider_owner("plugin:extension")

    assert service.providers.get("extension.game") is None
