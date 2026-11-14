"""市场刷新使用官方元数据，网络故障不能覆盖已有目录。"""

import json
from io import BytesIO
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
    """官方断线时从镜像读取真实元数据，不执行代码；支持 sidecar、Range 和整包响应。"""
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
            return httpx.Response(403)
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
