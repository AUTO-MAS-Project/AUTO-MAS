"""养成数据优先下载 gzip 快照，失败时回退源站及兼容缓存。"""

import asyncio
import gzip
import json
import time
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from maa_adapter import api as maa_api
from maa_adapter.config.script import MaaConfig
from maa_adapter.config.user import MaaUserConfig
from maa_adapter.cultivate import editor as api_service
from maa_adapter.cultivate import skland, yituliu

from app.config import ConfigCollection

HTTPX_CLIENT = httpx.AsyncClient

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
    client_type = HTTPX_CLIENT

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


def test_skill_summary_recipes_are_added_to_source_and_old_snapshot(snapshot):
    expected = {"3302": {"3301": 3}, "3303": {"3302": 3}}
    raw = snapshot["dataset"]  # 夹具经真实源站规范化入口构建。
    assert {
        recipe["result"]: recipe["ingredients"]
        for recipe in raw["recipes"]
        if recipe["result"] in expected
    } == expected
    raw["recipes"] = [
        recipe for recipe in raw["recipes"] if recipe["result"] not in expected
    ]
    restored = yituliu.dataset_from_json(raw)
    assert {
        recipe.result_item_id: dict(recipe.ingredients)
        for recipe in restored.recipes
        if recipe.result_item_id in expected
    } == expected


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
            for recipe in (
                yituliu._CHIP_RECIPES
                + yituliu._VOUCHER_RECIPES
                + yituliu._SKILL_SUMMARY_RECIPES
            )
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
async def test_all_sources_fail_without_cache_raises(tmp_path, network, loader):
    network(status=503, upstream_status=503)
    with pytest.raises(yituliu.YituliuDataError):
        await getattr(yituliu, loader)(tmp_path)
    assert not yituliu.snapshot_path(tmp_path).exists()


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


@pytest_asyncio.fixture
async def refresh_host(monkeypatch, tmp_path, snapshot, network):
    config = SimpleNamespace(
        ScriptConfig=ConfigCollection.build([MaaConfig]),
        config_path=tmp_path,
        proxy=None,
    )
    await config.ScriptConfig.activate()
    script_id = config.ScriptConfig.add(MaaConfig)
    await config.ScriptConfig.commit()
    script = config.ScriptConfig[script_id]
    user_id = script.UserData.add(
        MaaUserConfig,
        payload={
            "Task": {
                "CultivateSklandAccount": "account",
                "CultivateSklandUid": "role",
            }
        },
    )
    await script.UserData.commit()
    monkeypatch.setattr(api_service, "Config", config)
    from maa_adapter.config import access
    from maa_adapter.cultivate import inventory

    monkeypatch.setattr(access, "Config", config)
    monkeypatch.setattr(inventory, "Config", config)
    credential = {"raw": json.dumps({"cred": "test", "token": "test"})}

    async def load_credential(_account_uid):
        return credential["raw"]

    async def save_credential(_account_uid, raw):
        credential["raw"] = raw

    monkeypatch.setattr(
        api_service,
        "_cultivate_skland_callbacks",
        lambda: (load_credential, save_credential),
    )
    state = SimpleNamespace(level=1, failed=False, player_requests=[])

    def respond(request):
        if request.method == "HEAD":
            return httpx.Response(200)
        if request.url.path == "/web/v1/auth/refresh":
            return httpx.Response(200, json={"code": 0, "data": {"token": "test"}})
        assert request.url.path == "/api/v1/game/player/info"
        state.player_requests.append(request.url.params["uid"])
        if state.failed == "payload":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {"chars": [{"charId": "operator", "skills": 7}]},
                },
            )
        if state.failed:
            return httpx.Response(503, json={"code": 503})
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "chars": [
                        {"charId": "operator", "evolvePhase": 0, "level": state.level}
                    ]
                },
            },
        )

    client_type = HTTPX_CLIENT
    monkeypatch.setattr(
        skland._tool_skland,
        "create_skland_client",
        lambda **kwargs: HTTPX_CLIENT(transport=httpx.MockTransport(respond)),
    )
    monkeypatch.setattr(
        skland._tool_skland, "get_cached_device_id", AsyncMock(return_value="device")
    )
    monkeypatch.setattr(skland._tool_skland, "_server_clock", None)
    network(compressed(snapshot))
    skland.clear_skland_progression_cache()
    app = FastAPI()
    app.include_router(maa_api.router)
    try:
        async with client_type(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield SimpleNamespace(
                client=client,
                config=config,
                script=script,
                user=script.UserData[user_id],
                state=state,
                load_credential=load_credential,
                save_credential=save_credential,
            )
    finally:
        skland.clear_skland_progression_cache()


@pytest.mark.asyncio
async def test_refresh_endpoint_updates_cached_progression_and_deduplicates_bindings(
    refresh_host,
):
    host = refresh_host
    script_id, user_id = str(host.script.uid), str(host.user.uid)
    previous = await api_service.get_cultivate_skland_progression(script_id, user_id)
    assert previous[0]["operator"].level == 1
    host.state.level = 50
    assert (
        await api_service.get_cultivate_skland_progression(script_id, user_id)
        == previous
    )
    host.script.UserData.add(
        MaaUserConfig,
        payload={
            "Task": {"CultivateSklandAccount": "account", "CultivateSklandUid": "role"}
        },
    )
    await host.script.UserData.commit()
    response = await host.client.post(
        "/maa/cultivate/refresh", json={"scriptId": script_id}
    )
    assert response.json()["code"] == 200, response.json()
    refreshed = await api_service.get_cultivate_skland_progression(script_id, user_id)
    assert refreshed[0]["operator"].level == 50
    assert host.state.player_requests == ["role", "role"]
    assert (
        yituliu.read_snapshot(host.config.config_path)["operators"][0]["label"]
        == "Published operator"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("previous_age", "failure"),
    [(0, True), (301, True), (None, True), (301, "payload")],
)
async def test_refresh_failure_preserves_old_progression_but_execution_requires_fresh(
    refresh_host, previous_age, failure
):
    host = refresh_host
    script_id, user_id = str(host.script.uid), str(host.user.uid)
    previous = None
    if previous_age is not None:
        previous = await skland.fetch_skland_progression(
            skland.SklandAccountRef(account_uid="account", game_uid="role"),
            load_credential=host.load_credential,
            save_credential=host.save_credential,
            now=time.time() - previous_age,
        )
    host.state.failed = failure
    response = await host.client.post(
        "/maa/cultivate/refresh", json={"scriptId": script_id}
    )
    assert response.json()["code"] == 200, response.json()
    assert (
        await api_service.get_cultivate_skland_progression(script_id, user_id)
        == previous
    )
    host.state.failed = False
    host.state.level = 50
    response = await host.client.post(
        "/maa/cultivate/refresh", json={"scriptId": script_id}
    )
    assert response.json()["code"] == 200, response.json()
    refreshed = await api_service.get_cultivate_skland_progression(script_id, user_id)
    assert refreshed[0]["operator"].level == 50
    host.state.failed = True
    assert (
        await api_service.get_cultivate_skland_progression(
            script_id, user_id, force=True
        )
        is None
    )


@pytest.mark.asyncio
async def test_refresh_without_skland_binding_only_updates_shared_data(refresh_host):
    host = refresh_host
    host.user.Task.CultivateSklandUid = ""
    await host.user.commit()
    host.state.failed = True
    response = await host.client.post(
        "/maa/cultivate/refresh", json={"scriptId": str(host.script.uid)}
    )
    assert response.json()["code"] == 200, response.json()
    assert host.state.player_requests == []
    assert yituliu.read_snapshot(host.config.config_path) is not None


@pytest.mark.asyncio
async def test_slow_batch_refresh_keeps_old_progression_for_preview_reads(
    refresh_host, monkeypatch
):
    host = refresh_host
    second_id = host.script.UserData.add(
        MaaUserConfig,
        payload={
            "Task": {
                "CultivateSklandAccount": "account",
                "CultivateSklandUid": "second",
            }
        },
    )
    await host.script.UserData.commit()
    script_id = str(host.script.uid)
    user_ids = [str(host.user.uid), str(second_id)]
    previous = [
        await api_service.get_cultivate_skland_progression(script_id, user_id)
        for user_id in user_ids
    ]
    clock = SimpleNamespace(now=time.time())
    monkeypatch.setattr(skland.time, "time", lambda: clock.now)

    async def slow_credential(account_uid):
        clock.now += 61
        return await host.load_credential(account_uid)

    monkeypatch.setattr(
        api_service,
        "_cultivate_skland_callbacks",
        lambda: (slow_credential, host.save_credential),
    )
    host.state.failed = True
    response = await host.client.post(
        "/maa/cultivate/refresh", json={"scriptId": script_id}
    )
    assert response.json()["code"] == 200, response.json()
    assert [
        await api_service.get_cultivate_skland_progression(script_id, user_id)
        for user_id in user_ids
    ] == previous


@pytest.mark.asyncio
async def test_catalog_waiter_cancellation_does_not_cancel_other_waiter(
    tmp_path, snapshot, monkeypatch
):
    entered, release = asyncio.Event(), asyncio.Event()
    requests = []
    client_type = HTTPX_CLIENT

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
    client_type = HTTPX_CLIENT
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
