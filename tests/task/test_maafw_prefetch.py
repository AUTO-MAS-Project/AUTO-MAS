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
