"""已下载候选必须经过基线和预检门，不能重签或提前登记。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.task.MaaFW.tools.core.project_update import updater


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changed,blocked", [(False, False), (True, False), (False, True)]
)
async def test_prefetched_candidate_consumption_checks_baseline_and_gate(
    tmp_path, monkeypatch, changed, blocked
):
    candidate = updater.MaaFWProjectUpdateCandidate(
        source="github_release",
        version="2.0",
        download_url="https://example.invalid/package.zip",
        package_type="full",
    )
    discovery = updater.MaaFWProjectUpdateDiscovery(
        source="github_release", version="2.0", candidate=candidate
    )
    discover = AsyncMock(return_value=(None, None, "no newer version"))
    apply = AsyncMock(return_value={})
    gate = AsyncMock(return_value="environment unavailable" if blocked else None)
    monkeypatch.setattr(updater, "_discover_project_update_detailed", discover)
    monkeypatch.setattr(updater, "apply_maafw_project_update", apply)
    result = await updater.update_maafw_project_if_needed(
        tmp_path,
        SimpleNamespace(version="1.1" if changed else "1.0"),
        source_config={"project_shell_hint": "MXU"},
        precheck_gate=gate,
        prefetch_full_package=True,
        prefetched=("1.0", discovery),
    )
    if changed:
        discover.assert_awaited_once()
        apply.assert_not_awaited()
    else:
        discover.assert_not_awaited()
        gate.assert_awaited_once_with("2.0")
        if blocked:
            assert not result.updated
            apply.assert_not_awaited()
        else:
            assert result.updated
            apply.assert_awaited_once()
            assert apply.await_args.kwargs["range_delta"] is False

@pytest.mark.asyncio
async def test_shared_artifact_cache_serializes_coroutines(tmp_path, monkeypatch):
    """Prefetch and regular updating the same asset must not write concurrently."""
    import asyncio
    from contextlib import nullcontext

    from app.task.MaaFW.tools.core.project_update import transport

    monkeypatch.setattr(transport, "artifact_lock", lambda *args: nullcontext())
    active = 0
    maximum = 0
    first_started, release_first = asyncio.Event(), asyncio.Event()

    async def writer(name):
        nonlocal active, maximum
        async with transport._artifact_download_access(tmp_path, "same-asset"):
            active += 1
            maximum = max(maximum, active)
            try:
                if name == "first":
                    first_started.set()
                    await release_first.wait()
            finally:
                active -= 1

    first = asyncio.create_task(writer("first"))
    await asyncio.wait_for(first_started.wait(), 1)
    second = asyncio.create_task(writer("second"))
    await asyncio.sleep(0)
    assert active == 1
    assert not second.done()
    release_first.set()
    await asyncio.wait_for(asyncio.gather(first, second), 1)
    assert maximum == 1

@pytest.mark.asyncio
async def test_prefetch_discovery_forwards_precheck_gate_before_url(monkeypatch):
    """Public discovery must pass the failed-version gate to the URL resolver."""
    from app.task.MaaFW.tools.core.project_update import updater

    discovered = updater.MaaFWProjectUpdateDiscovery(
        source="mirrorchyan",
        version="2.0",
        unavailable_reason="previous runtime precheck failed",
    )
    detailed = AsyncMock(return_value=(discovered, None, None))
    monkeypatch.setattr(updater, "_discover_project_update_detailed", detailed)
    gate = AsyncMock(return_value="previous runtime precheck failed")
    result = await updater.discover_maafw_project_update(
        SimpleNamespace(),
        source_config={"package_source": "mirrorchyan"},
        precheck_gate=gate,
    )
    assert result is discovered
    assert detailed.await_args.kwargs["precheck_gate"] is gate
