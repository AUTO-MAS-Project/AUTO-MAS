"""市场刷新使用官方元数据，网络故障不能覆盖已有目录。"""

import json
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import httpx
import pytest
import pytest_asyncio

from app.config import ConfigCollection, config_manager
from app.models.config import (
    GlobalConfig,
    PluginMeta,
    PluginRecord,
    PluginRegistryCollection,
)
from app.plugin.runtime import market
from app.plugin.runtime.catalog_protocol import content_revision


def published_catalog(*, empty=False):
    """加载与独立生成仓库共用的旧日期线协议样例，确保目录不会因长期未变而失效。"""
    return json.loads(
        (
            Path(__file__).parents[1]
            / "fixtures"
            / ("plugin_catalog_empty_v2.json" if empty else "plugin_catalog_v2.json")
        ).read_text(encoding="utf-8")
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("empty", [False, True])
async def test_data_station_success_never_scans_package_indexes(
    catalog, monkeypatch, empty
):
    """有效数据站目录直接完成刷新，包括明确空目录；重复读取保持已有条目身份。"""
    document = published_catalog(empty=empty)
    # 命中的完整目录可以覆盖本地更高版本，也可以明确清空，均不进行跨源新旧比较。
    previous = market.parse_to_plugin_meta(project(version="99.0"))
    assert previous is not None
    catalog.add(PluginMeta, payload={"info": previous.info.model_dump()})
    await catalog.commit()
    monkeypatch.setenv("AUTO_MAS_PLUGIN_INDEX_URL", "https://catalog.test/plugins.json")
    requests = []

    def handler(request):
        """只允许读取完整目录，任何 PyPI 或镜像请求均表示快路径失效。"""
        requests.append(str(request.url))
        assert request.url.host == "catalog.test"
        return httpx.Response(200, json=document)

    serve(monkeypatch, handler)
    await market.refresh()
    first = list(catalog.keys())
    assert [
        {key: getattr(item.info, key) for key in market.ENTRY_FIELDS}
        for item in catalog.values()
    ] == document["plugins"]
    await market.refresh()
    assert list(catalog.keys()) == first
    assert requests == ["https://catalog.test/plugins.json"] * 2


@pytest.mark.asyncio
async def test_data_station_conditional_request_reuses_valid_document(
    catalog, monkeypatch
):
    """304 只复用经过校验的完整缓存，不读取任何发行源并保持配置身份。"""
    monkeypatch.setenv("AUTO_MAS_PLUGIN_INDEX_URL", "https://catalog.test/plugins.json")
    document = published_catalog()

    def handler(request):
        """首次返回实体与 ETag，后续根据条件头返回 304。"""
        assert request.url.host == "catalog.test"
        if request.headers.get("If-None-Match") == '"catalog-v1"':
            return httpx.Response(304)
        return httpx.Response(200, json=document, headers={"ETag": '"catalog-v1"'})

    serve(monkeypatch, handler)
    await market.refresh()
    first = list(catalog.keys())
    await market.refresh()
    assert list(catalog.keys()) == first
    assert len(catalog) == 1


@pytest.mark.asyncio
async def test_refresh_preserves_install_target_when_catalog_changes(
    catalog, monkeypatch
):
    """新插件和文案变更不会使等待重启的安装丢失入口，版本变更仍使用新入口。"""
    monkeypatch.setenv("AUTO_MAS_PLUGIN_INDEX_URL", "https://catalog.test/plugins.json")
    document = published_catalog()
    serve(monkeypatch, lambda _: httpx.Response(200, json=document))

    await market.refresh()
    (pending_uid,) = catalog.keys()

    entry = document["plugins"][0]
    entry["display_name_i18n"]["en"] = "Updated Demo Adapter"
    new_entry = deepcopy(entry)
    new_entry.update(package_name="auto-mas-another", plugin_name="another_adapter")
    document["plugins"] = [new_entry, entry]
    document["revision"] = content_revision(document["plugins"])
    await market.refresh()

    assert [meta.info.package_name for meta in catalog.values()] == [
        "auto-mas-another",
        "auto-mas-demo",
    ]
    assert catalog[pending_uid].info.display_name_i18n["en"] == "Updated Demo Adapter"

    entry["version"] = "0.2.0"
    document["revision"] = content_revision(document["plugins"])
    await market.refresh()

    assert pending_uid not in catalog
    assert [
        meta.info.version
        for meta in catalog.values()
        if meta.info.plugin_name == "demo_adapter"
    ] == ["0.2.0"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", ["network", "revision", "schema", "identity", "cache"]
)
async def test_invalid_data_station_catalog_uses_existing_fallback(
    catalog, monkeypatch, failure
):
    """网络、协议、摘要、身份或无缓存 304 失败时进入现有 PyPI 检索，不发布损坏目录。"""
    monkeypatch.setenv("AUTO_MAS_PLUGIN_INDEX_URL", "https://catalog.test/plugins.json")
    document = deepcopy(published_catalog())
    if failure == "revision":
        document["plugins"][0]["version"] = "99.0"
    elif failure == "schema":
        document["schema_version"] = 1
    elif failure == "identity":
        document["plugins"].append(deepcopy(document["plugins"][0]))
    hosts = []

    def handler(request):
        """隔离两类 HTTP 源，完整执行回退枚举、元数据解析及配置提交。"""
        hosts.append(request.url.host)
        if request.url.host == "catalog.test":
            if failure == "network":
                raise httpx.ConnectError("offline", request=request)
            return (
                httpx.Response(304)
                if failure == "cache"
                else httpx.Response(200, json=document)
            )
        if request.url.path.endswith("/simple/"):
            return httpx.Response(
                200, text='<a href="auto-mas-demo/">auto-mas-demo</a>'
            )
        return httpx.Response(200, json=project())

    serve(monkeypatch, handler)
    await market.refresh()
    assert hosts[0] == "catalog.test"
    assert "pypi.org" in hosts
    assert [item.info.version for item in catalog.values()] == ["0.1.1"]


@pytest.mark.asyncio
async def test_both_directory_sources_failing_preserves_catalog(catalog, monkeypatch):
    """数据站及发行源均失败时，真实目录与持久化文件保持原样并报告失败。"""
    monkeypatch.setenv("AUTO_MAS_PLUGIN_INDEX_URL", "https://catalog.test/plugins.json")
    draft = market.parse_to_plugin_meta(project())
    assert draft is not None
    catalog.add(PluginMeta, payload={"info": draft.info.model_dump()})
    await catalog.commit()
    await config_manager.flush()
    previous = catalog.model_dump()
    path = market.Config.config_path / "catalog.yaml"
    saved = path.read_bytes()

    def handler(request):
        """在两类源的真实 HTTP 边界注入故障，保留原刷新与事务逻辑。"""
        raise httpx.ConnectError("offline", request=request)

    serve(monkeypatch, handler)
    with pytest.raises(RuntimeError):
        await market.refresh()
    await config_manager.flush()
    assert catalog.model_dump() == previous
    assert path.read_bytes() == saved


def project(name="auto-mas-demo", version="0.1.1"):
    """按 PyPI JSON 契约构造带完整市场声明的发行包。"""
    display = {
        "display_name_i18n": {"en": "Demo Adapter", "zh_CN": "示例专项"},
        "description_i18n": {"en": "Demo script adapter"},
        "tags_i18n": {"en": ["Adapter"]},
    }
    return {
        "info": {
            "name": name,
            "version": version,
            "summary": "Demo script adapter",
            "description": "<!-- auto-mas:i18n\n"
            + json.dumps(display, ensure_ascii=False)
            + "\n-->",
            "keywords": "auto-mas-plugin,auto-mas-id:demo_adapter",
            "project_urls": {
                "Documentation": "https://example.org/docs",
                "Homepage": "https://example.org/demo",
                "Repository": "https://example.org/source",
            },
            "author": "Demo Team",
            "license_expression": "AGPL-3.0-or-later",
            "requires_dist": ["auto-mas-core>=5.8,<5.9"],
        }
    }


@pytest_asyncio.fixture
async def catalog(isolated_app_paths, monkeypatch):
    """激活真实配置集合并隔离网络，避免刷新测试读写用户目录。"""
    config = isolated_app_paths
    monkeypatch.setenv("AUTO_MAS_PLUGIN_INDEX_URL", "")
    col = ConfigCollection[PluginMeta].build(
        [PluginMeta], file=config.config_path / "catalog.yaml"
    )
    registry = PluginRegistryCollection.build()
    setting = GlobalConfig.build()
    await col.activate()
    await registry.activate()
    registry.add(
        PluginRecord,
        payload={
            "info": {
                "plugin_name": "auto_mas_core",
                "package_name": "auto-mas-core",
                "is_core": True,
            }
        },
    )
    await registry.commit()
    monkeypatch.setattr(config, "plugin_catalog", col)
    monkeypatch.setattr(config, "plugin_registry", registry)
    monkeypatch.setattr(config, "setting", setting)
    return col


def serve(monkeypatch, handler):
    """只替换 HTTP 传输，保留刷新、解析、配置提交与持久化的真实实现。"""
    client_class = httpx.AsyncClient
    sync_client_class = httpx.Client
    monkeypatch.setattr(
        market.httpx,
        "AsyncClient",
        lambda **kwargs: client_class(transport=httpx.MockTransport(handler), **kwargs),
    )
    monkeypatch.setattr(
        market.httpx,
        "Client",
        lambda **kwargs: sync_client_class(
            transport=httpx.MockTransport(handler), **kwargs
        ),
    )


@pytest.mark.asyncio
async def test_refresh_discovers_pypi_plugin_independently_of_install_mirror(
    catalog, monkeypatch
):
    """安装镜像没有新包或 JSON API 时，首次刷新仍能发现官方发布的插件。"""
    preferred = market.Config.setting.uv.preferred_mirror

    def handler(request):
        if request.url.host != "pypi.org":
            return httpx.Response(200, text="<html></html>")
        if request.url.path == "/simple/":
            return httpx.Response(
                200, text='<a href="/simple/auto-mas-demo/">auto-mas-demo</a>'
            )
        return httpx.Response(200, json=project())

    serve(monkeypatch, handler)
    await market.refresh()
    assert [
        (item.info.package_name, item.info.version) for item in catalog.values()
    ] == [("auto-mas-demo", "0.1.1")]
    assert market.Config.setting.uv.preferred_mirror == preferred


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["index", "metadata", "partial"])
async def test_failed_refresh_preserves_previous_catalog(catalog, monkeypatch, failure):
    """索引或部分包的网络读取失败必须报错，旧目录的身份、版本和文件保持不变。"""
    draft = market.parse_to_plugin_meta(project(version="0.1.0"))
    assert draft is not None
    catalog.add(PluginMeta, payload={"info": draft.info.model_dump()})
    if failure == "partial":
        other = market.parse_to_plugin_meta(project("auto-mas-other", "0.1.0"))
        assert other is not None
        catalog.add(PluginMeta, payload={"info": other.info.model_dump()})
    await catalog.commit()
    await config_manager.flush()
    previous = catalog.model_dump()
    path = market.Config.config_path / "catalog.yaml"
    previous_file = path.read_bytes()

    def handler(request):
        if request.url.path.endswith("/simple/"):
            if failure == "index":
                raise httpx.ConnectError("TLS connection interrupted", request=request)
            names = ["auto-mas-demo"]
            if failure == "partial":
                names.append("auto-mas-other")
            return httpx.Response(
                200, text="\n".join(f'<a href="{name}/">{name}</a>' for name in names)
            )
        if failure != "partial" or "auto-mas-other" in request.url.path:
            raise httpx.ConnectError("TLS connection interrupted", request=request)
        return httpx.Response(200, json=project())

    serve(monkeypatch, handler)
    with pytest.raises(RuntimeError):
        await market.refresh()
    await config_manager.flush()
    assert catalog.model_dump() == previous
    assert path.read_bytes() == previous_file


@pytest.mark.asyncio
async def test_refresh_recovers_from_transient_connection_failure(catalog, monkeypatch):
    """短暂 TLS 中断后在同次刷新内恢复，真实 404 包不会阻止有效插件入库。"""
    failed = set()

    def handler(request):
        if request.url.path not in failed:
            failed.add(request.url.path)
            raise httpx.ConnectError("TLS connection interrupted", request=request)
        if request.url.path == "/simple/":
            return httpx.Response(
                200,
                text='<a href="auto-mas-demo/">auto-mas-demo</a>\n'
                '<a href="auto-mas-removed/">auto-mas-removed</a>',
            )
        if "auto-mas-removed" in request.url.path:
            return httpx.Response(404)
        return httpx.Response(200, json=project())

    serve(monkeypatch, handler)
    await market.refresh()
    assert [item.info.package_name for item in catalog.values()] == ["auto-mas-demo"]


@pytest.mark.asyncio
@pytest.mark.parametrize("format", ["sidecar", "range", "whole"])
async def test_refresh_reads_mirror_metadata_when_pypi_is_unreachable(
    catalog, monkeypatch, format
):
    """官方来源不可用时读取单个镜像的完整元数据，不执行候选代码。"""
    info = project()["info"]
    metadata = (
        "Metadata-Version: 2.3\nName: auto-mas-demo\nVersion: 0.1.1\n"
        f"Summary: {info['summary']}\nKeywords: {info['keywords']}\n"
        "Project-URL: Documentation, https://example.org/docs\n"
        "Project-URL: Homepage, https://example.org/demo\n"
        "Project-URL: Repository, https://example.org/source\n"
        "Author: Demo Team\nLicense-Expression: AGPL-3.0-or-later\n"
        "Requires-Dist: auto-mas-core>=5.8,<5.9\n\n" + info["description"]
    ).encode()
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("auto_mas_demo-0.1.1.dist-info/METADATA", metadata)
        archive.writestr(
            "demo_adapter/__init__.py", 'raise RuntimeError("Do not import")'
        )
        archive.writestr("demo_adapter/data.bin", b"x" * 100_000)
    wheel = buffer.getvalue()
    transferred = 0

    def handler(request):
        nonlocal transferred
        if request.url.host == "pypi.org":
            raise httpx.ConnectError("TLS connection interrupted", request=request)
        if request.url.path.endswith("/simple/"):
            return httpx.Response(
                200,
                text='<a href="auto-mas-demo/">auto-mas-demo</a>\n'
                '<a href="auto-mas-unidentified/">auto-mas-unidentified</a>',
            )
        if request.url.path.endswith("/auto-mas-unidentified/"):
            return httpx.Response(404)
        if request.url.path.endswith("/auto-mas-demo/"):
            attribute = 'data-core-metadata="true"' if format == "sidecar" else ""
            return httpx.Response(
                200,
                text=f'<a href="../../files/auto_mas_demo-0.1.1-py3-none-any.whl" {attribute}>wheel</a>'
                '<a href="../../files/auto_mas_demo-0.2.0-py3-none-any.whl" data-yanked="bad release">wheel</a>',
            )
        if request.url.path.endswith(".metadata"):
            return httpx.Response(200, content=metadata)
        assert request.url.path.endswith("auto_mas_demo-0.1.1-py3-none-any.whl")
        if format == "whole":
            return httpx.Response(200, content=wheel)
        interval = request.headers["Range"].removeprefix("bytes=")
        first, last = interval.split("-")
        start = int(first) if first else max(0, len(wheel) - int(last))
        end = min(int(last) if first else len(wheel) - 1, len(wheel) - 1)
        content = wheel[start : end + 1]
        transferred += len(content)
        return httpx.Response(
            206,
            content=content,
            headers={"Content-Range": f"bytes {start}-{end}/{len(wheel)}"},
        )

    preferred = market.Config.setting.uv.preferred_mirror
    serve(monkeypatch, handler)
    await market.refresh()
    assert [
        (item.info.package_name, item.info.version) for item in catalog.values()
    ] == [("auto-mas-demo", "0.1.1")]
    assert market.Config.setting.uv.preferred_mirror == preferred
    if format == "range":
        assert transferred < len(wheel)
    assert next(iter(catalog.values())).info.display_name_i18n["zh_CN"] == "示例专项"
    saved = next(iter(catalog.values())).info
    assert saved.docs_url == "https://example.org/docs"
    assert saved.homepage == "https://example.org/demo"
    assert saved.repository == "https://example.org/source"
    assert saved.author == "Demo Team"
    assert saved.license == "AGPL-3.0-or-later"
    assert saved.requires_dist == ["auto-mas-core>=5.8,<5.9"]


@pytest.mark.asyncio
async def test_known_package_query_survives_official_index_failure(
    catalog, monkeypatch
):
    """总索引不可用时仍查询全部已知包，单包查询成功后不降到缺包镜像。"""
    draft = market.parse_to_plugin_meta(project(version="0.1.0"))
    catalog.add(PluginMeta, payload={"info": draft.info.model_dump()})
    await catalog.commit()
    requests = []

    def handler(request):
        """仅官方总索引失败，官方单包接口仍提供完整的新元信息。"""
        requests.append(str(request.url))
        assert request.url.host == "pypi.org"
        if request.url.path == "/simple/":
            return httpx.Response(503)
        return httpx.Response(200, json=project())

    serve(monkeypatch, handler)
    await market.refresh()
    assert [item.info.version for item in catalog.values()] == ["0.1.1"]
    assert "https://pypi.org/pypi/auto-mas-demo/json" in requests


@pytest.mark.asyncio
async def test_complete_empty_official_result_does_not_consult_mirrors(
    catalog, monkeypatch
):
    """官方已完整确认候选均不存在时采用空结果，不再混入镜像残留版本。"""
    draft = market.parse_to_plugin_meta(project())
    catalog.add(PluginMeta, payload={"info": draft.info.model_dump()})
    await catalog.commit()

    def handler(request):
        """官方完整读取成功，禁止向较低优先级来源补充目录。"""
        assert request.url.host == "pypi.org"
        return (
            httpx.Response(200, text="<html></html>")
            if request.url.path == "/simple/"
            else httpx.Response(404)
        )

    serve(monkeypatch, handler)
    await market.refresh()
    assert len(catalog) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("second_complete", [True, False])
async def test_incomplete_mirror_is_discarded_before_next_source(
    catalog, monkeypatch, second_complete
):
    """任一候选失败则放弃整级结果，全部不完整时旧目录保持不变。"""
    previous = market.parse_to_plugin_meta(project(version="0.1.0"))
    assert previous is not None
    catalog.add(PluginMeta, payload={"info": previous.info.model_dump()})
    await catalog.commit()
    before = catalog.model_dump()
    monkeypatch.setattr(
        market,
        "candidates",
        lambda: ["https://first.test/simple/", "https://second.test/simple/"],
    )
    requests = []

    def handler(request):
        """第一镜像只能完整读取一个包，第二镜像提供自洽的两个包。"""
        requests.append(str(request.url))
        if request.url.host == "pypi.org":
            return httpx.Response(503)
        if request.url.path == "/simple/":
            return httpx.Response(
                200,
                text='<a href="auto-mas-demo/">auto-mas-demo</a><a href="auto-mas-other/">auto-mas-other</a>',
            )
        name = "auto-mas-other" if "other" in request.url.path else "auto-mas-demo"
        if name == "auto-mas-other" and (
            request.url.host == "first.test" or not second_complete
        ):
            return httpx.Response(503)
        version = (
            "2.0.0"
            if request.url.host == "first.test"
            else "0.2.0"
            if name == "auto-mas-other"
            else "0.1.1"
        )
        if request.url.path.endswith("/"):
            filename = f"{name.replace('-', '_')}-{version}-py3-none-any.whl"
            return httpx.Response(
                200,
                text=f'<a href="/files/{filename}" data-core-metadata="true">wheel</a>',
            )
        assert request.url.path.endswith(".metadata")
        info = project(name, version)["info"]
        identity = name.removeprefix("auto-mas-") + "_adapter"
        metadata = (
            f"Metadata-Version: 2.3\nName: {name}\nVersion: {version}\n"
            f"Keywords: auto-mas-plugin,auto-mas-id:{identity}\n"
            "Requires-Dist: auto-mas-core>=5.8,<5.9\n\n" + info["description"]
        )
        return httpx.Response(200, text=metadata)

    serve(monkeypatch, handler)
    if second_complete:
        await market.refresh()
        assert {
            item.info.package_name: item.info.version for item in catalog.values()
        } == {
            "auto-mas-demo": "0.1.1",
            "auto-mas-other": "0.2.0",
        }
    else:
        with pytest.raises(RuntimeError):
            await market.refresh()
        assert catalog.model_dump() == before
    assert any("first.test" in url for url in requests)
    assert any("second.test" in url for url in requests)


@pytest.mark.asyncio
async def test_changelog_range_and_fallback_on_same_install_target(
    catalog, monkeypatch
):
    """已装版本使用 PEP 440 筛选跨版说明，发行源回退清空同一条目内的数据站日志。"""
    monkeypatch.setenv("AUTO_MAS_PLUGIN_INDEX_URL", "https://catalog.test/plugins.json")
    document = published_catalog()
    entry = document["plugins"][0]
    entry["version"] = "1.10"
    entry["changelog"] = [
        {"version": version, "body": f"Notes {version}"}
        for version in ("1.10", "1.3", "1.2")
    ]
    document["revision"] = content_revision(document["plugins"])
    registry = market.Config.plugin_registry
    registry.add(
        PluginRecord,
        payload={
            "info": {
                "plugin_name": entry["plugin_name"],
                "package_name": entry["package_name"],
                "source": "installed",
                "version": "1.2.0",
            }
        },
    )
    await registry.commit()
    online = True

    def handler(request):
        if request.url.host == "catalog.test":
            return httpx.Response(200, json=document) if online else httpx.Response(503)
        if request.url.path == "/simple/":
            return httpx.Response(
                200, text='<a href="/simple/auto-mas-demo/">auto-mas-demo</a>'
            )
        return httpx.Response(200, json=project(version="1.10"))

    serve(monkeypatch, handler)
    await market.refresh()
    (uid,) = catalog.keys()
    from app.api.plugin import PluginCatalogGetIn, get_plugin_catalog

    result = await get_plugin_catalog(PluginCatalogGetIn(metaId=str(uid)))
    assert result.code == 200
    info = result.data[str(uid)].model_dump()["info"]
    assert info["changelog_versions"] == {
        "installed": "1.2",
        "target": "1.10",
        "updates": ["1.10", "1.3"],
    }
    assert info["changelog"] == entry["changelog"]

    online = False
    await market.refresh()
    result = await get_plugin_catalog(PluginCatalogGetIn(metaId=str(uid)))
    assert result.data[str(uid)].model_dump()["info"]["changelog"] == []
