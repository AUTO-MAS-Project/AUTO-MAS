"""养成数据优先下载 gzip 快照，失败时回退源站及兼容缓存。"""

import asyncio
import gzip
import json
import time
from copy import deepcopy

import httpx
import pytest

from app.task.MAA.tools.cultivate import yituliu

SNAPSHOT_URL = (
    "https://data.auto-mas.top/api/v1/files/auto-mas/Client/"
    "cultivate-dataset-json/download"
)


@pytest.fixture(autouse=True)
def isolated_memory_cache(monkeypatch):
    monkeypatch.setattr(yituliu, "_dataset_cache", None)
    monkeypatch.setattr(yituliu, "_dataset_lock", None)


@pytest.fixture
def sources():
    return {
        yituliu._DEMAND_URL: {
            "operator": {
                "name": "Upstream operator",
                "rarity": 6,
                "profession": "WARRIOR",
                "elite": [{}, {"3001": 2}],
                "allSkill": [{"3001": 1}],
                "skills": [],
                "equip": [],
            }
        },
        yituliu._MATRIX_URL: {
            "matrix": [
                {"stageId": "stage", "itemId": "3001", "times": 20, "quantity": 10}
            ]
        },
        yituliu._STAGE_INFO_URL: {
            "data": [{"stageId": "stage", "stageCode": "1-7", "apCost": 6}]
        },
        yituliu._RECIPE_URL: [
            {"itemId": "3002", "pathway": [{"itemId": "3001", "count": 3}]}
        ],
        yituliu._ITEM_INFO_URL: [],
    }


@pytest.fixture
def snapshot(sources):
    dataset = yituliu.normalize_dataset(
        demand_raw=sources[yituliu._DEMAND_URL],
        matrix_raw=sources[yituliu._MATRIX_URL],
        stage_raw=sources[yituliu._STAGE_INFO_URL],
        recipe_raw=sources[yituliu._RECIPE_URL],
        item_info_raw=sources[yituliu._ITEM_INFO_URL],
        data_version="published",
    )
    catalog = yituliu.parse_operator_catalog(sources[yituliu._DEMAND_URL])
    catalog[0]["label"] = "Published operator"
    return {
        "dataset": yituliu.dataset_to_json(dataset),
        "operators": catalog,
        # 日更快照的生成时间不能让本地一小时目录缓存始终过期。
        "saved_at": time.time() - 24 * 3600,
        "operators_saved_at": time.time() - 24 * 3600,
    }


@pytest.fixture
def network(monkeypatch, sources):
    client_type = httpx.AsyncClient

    def install(content=b"", *, status=200, upstream_status=200):
        requests = []

        def respond(request):
            url = str(request.url)
            requests.append(url)
            if url == SNAPSHOT_URL:
                return httpx.Response(status, content=content)
            assert url in sources, url
            return httpx.Response(upstream_status, json=sources[url])

        monkeypatch.setattr(
            yituliu.httpx,
            "AsyncClient",
            lambda **kwargs: client_type(
                transport=httpx.MockTransport(respond), **kwargs
            ),
        )
        return requests

    return install


def compressed(snapshot):
    return gzip.compress(json.dumps(snapshot).encode(), mtime=0)


@pytest.mark.asyncio
@pytest.mark.parametrize("first", ["dataset", "operators"])
async def test_gzip_populates_both_caches_once(tmp_path, snapshot, network, first):
    requests = network(compressed(snapshot))
    if first == "operators":
        await yituliu.load_operator_catalog(tmp_path)
    dataset = await yituliu.load_dataset(tmp_path)
    catalog = await yituliu.load_operator_catalog(tmp_path)
    assert dataset.data_version == "published"
    assert catalog == snapshot["operators"]
    assert requests == [SNAPSHOT_URL]
    cached = yituliu.read_snapshot(tmp_path)
    assert cached["saved_at"] > snapshot["saved_at"]
    assert cached["operators_saved_at"] > snapshot["operators_saved_at"]
    assert cached["dataset"]["schema_version"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("loader", ["load_dataset", "load_operator_catalog"])
@pytest.mark.parametrize(
    "failure",
    [
        "http",
        "gzip",
        "truncated",
        "json",
        "schema",
        "empty",
        "catalog",
        "catalog_type",
        "invalid_stages",
        "padded_recipes",
        "stale",
    ],
)
async def test_bad_snapshot_falls_back_to_source(
    tmp_path, snapshot, network, loader, failure
):
    if failure == "schema":
        snapshot["dataset"]["schema_version"] = 1
    elif failure == "empty":
        snapshot["dataset"]["stages"] = []
    elif failure == "catalog":
        snapshot["operators"].append(None)
    elif failure == "catalog_type":
        snapshot["operators"][0]["maxElite"] = None
    elif failure == "invalid_stages":
        for stage in snapshot["dataset"]["stages"]:
            stage["stage_code"] = ""
            stage["ap_cost"] = 0
    elif failure == "padded_recipes":
        local_ids = {
            recipe.result_item_id
            for recipe in yituliu._CHIP_RECIPES + yituliu._VOUCHER_RECIPES
        }
        snapshot["dataset"]["recipes"] = [
            recipe
            for recipe in snapshot["dataset"]["recipes"]
            if recipe["result"] in local_ids
        ]
    elif failure == "stale":
        snapshot["saved_at"] = snapshot["operators_saved_at"] = time.time() - 4 * 86400
    content = compressed(snapshot)
    if failure == "gzip":
        content = b"not gzip"
    elif failure == "truncated":
        content = content[:-5]
    elif failure == "json":
        content = gzip.compress(b"[]")
    requests = network(content, status=503 if failure == "http" else 200)
    result = await getattr(yituliu, loader)(tmp_path)
    assert requests[0] == SNAPSHOT_URL
    assert yituliu._DEMAND_URL in requests
    if loader == "load_dataset":
        assert result.demands["operator"]
        assert result.data_version != "published"
    else:
        assert result[0]["label"] == "Upstream operator"


@pytest.mark.asyncio
@pytest.mark.parametrize("loader", ["load_dataset", "load_operator_catalog"])
async def test_all_sources_fail_without_replacing_old_cache(
    tmp_path, snapshot, network, loader
):
    path = yituliu.snapshot_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    original = path.read_bytes()
    requests = network(status=503, upstream_status=503)
    result = await getattr(yituliu, loader)(tmp_path, max_age_hours=0)
    assert result
    assert requests[0] == SNAPSHOT_URL
    assert yituliu._DEMAND_URL in requests
    assert path.read_bytes() == original


@pytest.mark.asyncio
@pytest.mark.parametrize("loader", ["load_dataset", "load_operator_catalog"])
async def test_all_sources_fail_without_cache_raises(tmp_path, network, loader):
    network(status=503, upstream_status=503)
    with pytest.raises(yituliu.YituliuDataError):
        await getattr(yituliu, loader)(tmp_path)
    assert not yituliu.snapshot_path(tmp_path).exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("loader", ["load_dataset", "load_operator_catalog"])
async def test_partial_bundle_never_replaces_a_complete_cache(
    tmp_path, snapshot, network, loader
):
    path = yituliu.snapshot_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    original = path.read_bytes()
    partial = deepcopy(snapshot)
    partial["operators"] = []
    partial["dataset"]["data_version"] = "incomplete"
    network(compressed(partial), upstream_status=503)
    await getattr(yituliu, loader)(tmp_path, max_age_hours=0)
    assert path.read_bytes() == original


@pytest.mark.asyncio
@pytest.mark.parametrize("size_kind", ["compressed", "decoded"])
async def test_oversized_snapshot_falls_back(
    tmp_path, snapshot, network, monkeypatch, size_kind
):
    monkeypatch.setattr(yituliu, "_SNAPSHOT_MAX_BYTES", 8192)
    snapshot["padding"] = "x" * 16384
    content = b"x" * 8193 if size_kind == "compressed" else compressed(snapshot)
    requests = network(content)
    dataset = await yituliu.load_dataset(tmp_path)
    assert dataset.data_version != "published"
    assert requests[0] == SNAPSHOT_URL
    assert yituliu._DEMAND_URL in requests


@pytest.mark.asyncio
async def test_cache_write_failure_keeps_download_usable(
    tmp_path, snapshot, network, monkeypatch
):
    requests = network(compressed(snapshot))

    def fail_write(*args, **kwargs):
        raise OSError("read-only cache")

    monkeypatch.setattr(yituliu._utils_io, "write_file", fail_write)
    dataset = await yituliu.load_dataset(tmp_path)
    assert dataset.data_version == "published"
    catalog = await yituliu.load_operator_catalog(tmp_path)
    assert catalog == snapshot["operators"]
    assert requests == [SNAPSHOT_URL, SNAPSHOT_URL]


@pytest.mark.asyncio
async def test_catalog_waiter_cancellation_does_not_cancel_other_waiter(
    tmp_path, snapshot, monkeypatch
):
    entered, release = asyncio.Event(), asyncio.Event()
    requests = []
    client_type = httpx.AsyncClient

    async def respond(request):
        requests.append(str(request.url))
        entered.set()
        await release.wait()
        return httpx.Response(200, content=compressed(snapshot))

    monkeypatch.setattr(
        yituliu.httpx,
        "AsyncClient",
        lambda **kwargs: client_type(transport=httpx.MockTransport(respond), **kwargs),
    )
    cancelled = asyncio.create_task(yituliu.load_operator_catalog(tmp_path))
    await entered.wait()
    survivor = asyncio.create_task(yituliu.load_operator_catalog(tmp_path))
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    release.set()
    assert await survivor == snapshot["operators"]
    assert requests == [SNAPSHOT_URL]


@pytest.mark.asyncio
async def test_manual_refresh_bypasses_both_caches(tmp_path, snapshot, network):
    network(compressed(snapshot))
    await yituliu.get_dataset_cached(tmp_path)
    snapshot["dataset"]["data_version"] = "refreshed"
    snapshot["operators"][0]["label"] = "Refreshed operator"
    requests = network(compressed(snapshot))
    await yituliu.refresh_data(tmp_path)
    assert (await yituliu.get_dataset_cached(tmp_path)).data_version == "refreshed"
    assert (await yituliu.load_operator_catalog(tmp_path))[0][
        "label"
    ] == "Refreshed operator"
    assert requests == [SNAPSHOT_URL]


@pytest.mark.asyncio
async def test_manual_fallback_uses_one_demand_table_for_both_parts(tmp_path, network):
    requests = network(status=503)
    await yituliu.refresh_data(tmp_path)
    assert (await yituliu.load_operator_catalog(tmp_path))[0][
        "label"
    ] == "Upstream operator"
    assert (await yituliu.get_dataset_cached(tmp_path)).demands["operator"]
    assert len(requests) == 6
    assert requests.count(yituliu._DEMAND_URL) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["network", "cache"])
async def test_failed_manual_refresh_preserves_disk_and_memory(
    tmp_path, snapshot, network, monkeypatch, failure
):
    network(compressed(snapshot))
    previous = await yituliu.get_dataset_cached(tmp_path)
    path = yituliu.snapshot_path(tmp_path)
    original = path.read_bytes()
    if failure == "cache":
        snapshot["dataset"]["data_version"] = "must-not-commit"
        network(compressed(snapshot))

        def fail_write(*args, **kwargs):
            raise OSError("read-only cache")

        monkeypatch.setattr(yituliu._utils_io, "write_file", fail_write)
        error = OSError
    else:
        network(status=503, upstream_status=503)
        error = yituliu.YituliuDataError
    with pytest.raises(error):
        await yituliu.refresh_data(tmp_path)
    assert path.read_bytes() == original
    assert await yituliu.get_dataset_cached(tmp_path) is previous


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", ["empty_stages", "invalid_stages", "empty_recipes", "invalid_recipes"]
)
async def test_incomplete_source_refresh_cannot_be_masked_by_local_supplements(
    tmp_path, snapshot, sources, network, failure
):
    network(compressed(snapshot))
    previous = await yituliu.get_dataset_cached(tmp_path)
    path = yituliu.snapshot_path(tmp_path)
    original = path.read_bytes()
    if failure == "empty_stages":
        sources[yituliu._STAGE_INFO_URL] = {"data": []}
    elif failure == "invalid_stages":
        sources[yituliu._STAGE_INFO_URL] = {
            "data": [{"stageId": "stage", "stageCode": "", "apCost": 0}]
        }
    elif failure == "empty_recipes":
        sources[yituliu._RECIPE_URL] = []
    else:
        sources[yituliu._RECIPE_URL] = [{}]
    network(status=503)
    with pytest.raises(yituliu.YituliuDataError):
        await yituliu.refresh_data(tmp_path)
    assert path.read_bytes() == original
    assert await yituliu.get_dataset_cached(tmp_path) is previous


@pytest.mark.asyncio
async def test_manual_refresh_waits_for_old_catalog_and_shares_new_result(
    tmp_path, snapshot, monkeypatch
):
    entered, release = asyncio.Event(), asyncio.Event()
    client_type = httpx.AsyncClient
    requests = []
    fresh = deepcopy(snapshot)
    fresh["operators"][0]["label"] = "Refreshed operator"

    async def respond(request):
        requests.append(str(request.url))
        if len(requests) == 1:
            entered.set()
            await release.wait()
            return httpx.Response(200, content=compressed(snapshot))
        return httpx.Response(200, content=compressed(fresh))

    monkeypatch.setattr(
        yituliu.httpx,
        "AsyncClient",
        lambda **kwargs: client_type(transport=httpx.MockTransport(respond), **kwargs),
    )
    old = asyncio.create_task(yituliu.load_operator_catalog(tmp_path))
    await entered.wait()
    refresh = asyncio.create_task(yituliu.refresh_data(tmp_path))
    await asyncio.sleep(0)
    reader = asyncio.create_task(yituliu.load_operator_catalog(tmp_path))
    other_refresh = asyncio.create_task(yituliu.refresh_data(tmp_path))
    release.set()
    await asyncio.gather(old, refresh, other_refresh)
    assert (await reader)[0]["label"] == "Refreshed operator"
    assert requests == [SNAPSHOT_URL, SNAPSHOT_URL]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure, expected_code",
    [
        (None, 200),
        (yituliu.YituliuDataError("source unavailable"), 503),
        (OSError("read-only cache"), 507),
        (RuntimeError("unknown error"), 500),
    ],
)
async def test_refresh_http_contract_calls_domain(monkeypatch, failure, expected_code):
    from unittest.mock import AsyncMock

    from fastapi import FastAPI

    from app.task.MAA import api, api_service

    refresh = AsyncMock(side_effect=failure)
    monkeypatch.setattr(api_service, "refresh_cultivate_data", refresh)
    app = FastAPI()
    app.include_router(api.router, prefix="/api/scripts")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/scripts/maa/cultivate/refresh", json={"scriptId": "script"}
        )
    assert response.status_code == 200
    assert response.json()["code"] == expected_code
    refresh.assert_awaited_once_with("script")
