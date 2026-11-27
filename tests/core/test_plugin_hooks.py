"""宿主扩展点按插件服务调用，并隔离单个插件的失败。"""

import asyncio
from types import SimpleNamespace

import pytest

from app.core.plugin import hooks
from app.plugin.services import ServiceRegistry


def test_service_registry_iter_prefix_returns_sorted_snapshot():
    registry = ServiceRegistry()
    registry.register("task.before_auto_proxy:z", object(), owner="z")
    registry.register("task.before_auto_proxy:a", object(), owner="a")
    registry.register("other", object(), owner="other")

    names = [name for name, _ in registry.iter_prefix("task.before_auto_proxy:")]

    assert names == [
        "task.before_auto_proxy:a",
        "task.before_auto_proxy:z",
    ]


@pytest.mark.asyncio
async def test_before_auto_proxy_hooks_continue_after_timeout_and_failure(monkeypatch):
    events: list[str] = []

    async def virtual_display():
        events.append("virtual_display")

    async def timed_out():
        await asyncio.sleep(1)

    async def after_failure():
        events.append("after_failure")
        raise RuntimeError("plugin failure")

    async def final_hook():
        events.append("final")

    services = SimpleNamespace(
        iter_prefix=lambda prefix: (
            ("task.before_auto_proxy:virtual_display", virtual_display),
            ("task.before_auto_proxy:timed_out", timed_out),
            ("task.before_auto_proxy:after_failure", after_failure),
            ("task.before_auto_proxy:final", final_hook),
        )
    )
    monkeypatch.setattr("app.core.Plugin", SimpleNamespace(services=services))
    monkeypatch.setattr(
        hooks,
        "_legacy_virtual_display_hook",
        lambda: pytest.fail("plugin hook should replace the legacy guard"),
    )

    await hooks.run_before_auto_proxy_hooks(timeout=0.01)

    assert events == ["virtual_display", "after_failure", "final"]


@pytest.mark.asyncio
async def test_before_auto_proxy_hooks_fall_back_to_legacy_guard(monkeypatch):
    legacy_called = asyncio.Event()

    async def legacy_guard():
        legacy_called.set()

    monkeypatch.setattr(
        "app.core.Plugin",
        SimpleNamespace(services=SimpleNamespace(iter_prefix=lambda prefix: ())),
    )
    monkeypatch.setattr(hooks, "_legacy_virtual_display_hook", lambda: legacy_guard)

    await hooks.run_before_auto_proxy_hooks()

    assert legacy_called.is_set()
