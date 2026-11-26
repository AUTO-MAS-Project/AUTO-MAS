"""插件安装的目标校验、镜像精确版本与实际发行身份验证。"""

import importlib.metadata
import sys
from contextlib import AsyncExitStack
from email.message import Message
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio

from app.core.plugin.manager import _PluginManager
from app.models.config import PluginMeta, PluginRecord, PluginRegistryCollection
from app.plugin import uv
from app.plugin.errors import PluginPrecheckError
from app.plugin.runtime import loader
from app.plugin.uv import environment, precheck
from app.utils.common.log_flow.contracts import (
    FunctionRef,
    PipelineSpec,
    WorkerPluginPackage,
)
from app.utils.common.log_flow.observation import ReportEntry
from app.utils.common.log_flow.session import LogFlowSession


def metadata(*, identity="install_probe", version="1.0", sdk=True):
    """构造标准发行元数据，供镜像响应及真实 dist-info 使用。"""
    result = Message()
    result["Name"] = "auto-mas-install-probe"
    result["Version"] = version
    result["Keywords"] = f"auto-mas-plugin, auto-mas-id:{identity}"
    if sdk:
        result["Requires-Dist"] = "auto-mas-core>=5,<6"
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize("dependency_version", ["1.0", "2.0"])
async def test_install_preserves_packages_read_by_logflow_worker(
    isolated_app_paths, tmp_path, monkeypatch, dependency_version
):
    """装包求解期间启动的 worker 仍能从共享环境读到它原来使用的依赖。"""
    registry = PluginRegistryCollection.build([PluginRecord])
    await registry.activate()
    monkeypatch.setattr(isolated_app_paths, "plugin_registry", registry)
    monkeypatch.setattr(sys, "path", sys.path.copy())
    monkeypatch.setattr(precheck, "host_constraints", lambda: [])
    monkeypatch.setattr(precheck, "host_dependencies", lambda: [])
    site = uv.site_dir(activate=False)
    dependency = "logflow_worker_dep"

    def write_distribution(root, name, version, implementation):
        package = root / name
        package.mkdir(parents=True)
        (package / "__init__.py").write_text(implementation, encoding="utf-8")
        info = root / f"{name}-{version}.dist-info"
        info.mkdir()
        payload = metadata(identity=name, version=version)
        payload.replace_header("Name", name.replace("_", "-"))
        (info / "METADATA").write_text(str(payload), encoding="utf-8")
        (info / "RECORD").write_text(
            f"{name}/__init__.py,,\n{info.name}/METADATA,,\n{info.name}/RECORD,,\n",
            encoding="utf-8",
        )

    def report_code(version):
        return (
            "from app.utils.common.log_flow.observation import ReportEntry\n"
            f"def report(_): return [ReportEntry(node_type='info', text={version!r})]\n"
        )

    write_distribution(site, dependency, "1.0", report_code("1.0"))
    async with AsyncExitStack() as stack:
        session = None

        async def resolve_environment(*, destination, **_kwargs):
            nonlocal session
            session = await LogFlowSession.open(
                PipelineSpec(
                    accept_push=True,
                    plugin_package=WorkerPluginPackage(
                        name="probe",
                        import_root=str(tmp_path),
                        dependency_root=str(site),
                        sdk_root=str(tmp_path),
                    ),
                    postprocess=FunctionRef(
                        name="probe:report", module=dependency, attribute="report"
                    ),
                ),
            )
            stack.push_async_callback(session.close_on_exit)
            write_distribution(
                destination,
                dependency,
                dependency_version,
                report_code(dependency_version),
            )
            write_distribution(destination, "install_probe", "1.0", "")
            return SimpleNamespace(ok=True)

        monkeypatch.setattr(precheck, "resolve_environment", resolve_environment)
        assert not LogFlowSession.has_shared_environment_readers()
        expects_restart = dependency_version != "1.0"
        result = await uv.install(
            "install-probe",
            plugin_name="install_probe",
            has_shared_environment_readers=LogFlowSession.has_shared_environment_readers,
        )
        assert dependency not in sys.modules
        assert result is expects_restart
        assert (site / dependency / "__init__.py").read_text(
            encoding="utf-8"
        ) == report_code("1.0")
        assert (site / "install_probe").exists() is not expects_restart
        assert site.with_suffix(".pending").exists() is expects_restart
        assert environment.read_installation().progress.state == (
            "waiting_restart" if expects_restart else "applying"
        )
        assert session is not None
        summary = await session.close()
        assert summary.complete and summary.report_entries == (
            ReportEntry(node_type="info", text="1.0"),
        )
    assert not LogFlowSession.has_shared_environment_readers()


@pytest_asyncio.fixture
async def installation(isolated_app_paths, monkeypatch, tmp_path):
    """隔离发行索引及安装进程，保留真实元数据发现和插件加载，结束时清除临时模块。"""
    config = isolated_app_paths
    registry = PluginRegistryCollection.build([PluginRecord])
    await registry.activate()
    monkeypatch.setattr(config, "plugin_registry", registry)
    source = tmp_path / "source"
    (source / "plugins").mkdir(parents=True)
    monkeypatch.setattr(config, "source_path", source)
    site = uv.site_dir(activate=False)
    monkeypatch.syspath_prepend(str(site))
    state = SimpleNamespace(
        registry=registry, calls=[], package=metadata(), remote=metadata(), sdist=False
    )
    monkeypatch.setattr(
        uv,
        "candidates",
        lambda: ["https://first.test/simple", "https://second.test/simple"],
    )

    def response(request):
        """首镜像未同步，次镜像同时包含新旧版本，安装必须取得目录指定的旧版本。"""
        if request.url.host == "first.test":
            return httpx.Response(404)
        if request.url.host == "pypi.org":
            return httpx.Response(
                200,
                json={
                    "info": {
                        "name": state.remote["Name"],
                        "version": state.remote["Version"],
                        "keywords": state.remote["Keywords"],
                        "requires_dist": state.remote.get_all("Requires-Dist") or [],
                    }
                },
            )
        if state.sdist:
            return httpx.Response(200, text="<html></html>")
        if request.url.path.endswith(".metadata"):
            assert request.url.path.endswith("-1.0-py3-none-any.whl.metadata")
            return httpx.Response(200, text=str(state.remote))
        return httpx.Response(
            200,
            text="".join(
                f'<a href="https://second.test/auto_mas_install_probe-{version}-py3-none-any.whl" data-core-metadata="true">wheel</a>'
                for version in ("1.0", "2.0")
            ),
        )

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(response)),
    )

    async def install(package, *, plugin_name, meta_id, has_shared_environment_readers):
        """在进程边界落地测试发行包，后续读取、发现和加载均使用实际文件。"""
        state.calls.append(package)
        assert not has_shared_environment_readers()
        info = site / "auto_mas_install_probe-1.0.dist-info"
        info.mkdir()
        (info / "METADATA").write_text(str(state.package), encoding="utf-8")
        (info / "RECORD").write_text("install_probe/__init__.py,,\n", encoding="utf-8")
        module = site / "install_probe"
        module.mkdir()
        (module / "__init__.py").write_text(
            "from app.plugin.base import BasePlugin\nclass Adapter(BasePlugin): pass\nPLUGIN = Adapter\n",
            encoding="utf-8",
        )

    monkeypatch.setattr(uv, "install", install)
    distributions = importlib.metadata.distributions
    monkeypatch.setattr(
        importlib.metadata, "distributions", lambda: distributions(path=[str(site)])
    )
    yield state
    for record in registry.values():
        loader.clear(record)
    sys.modules.pop("install_probe", None)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["market", "internal", "sdist"])
async def test_install_checks_real_distribution_before_loading(installation, mode):
    """市场固定版本且允许镜像回退；内部自动升级可以求解版本，二者均核对实际发行身份。"""
    state = installation
    automatic = mode == "internal"
    state.sdist = mode == "sdist"
    meta = PluginMeta.build(
        info={
            "package_name": "auto-mas-install-probe",
            "plugin_name": "install_probe",
            "version": "" if automatic else "1.0",
        }
    )
    await _PluginManager().install(meta)
    record = state.registry.by_name("install_probe")
    assert record is not None and record._plugin_cls is not None
    assert record.info.version == "1.0" and record.info.source == "installed"
    assert state.calls == [
        "auto-mas-install-probe" if automatic else "auto-mas-install-probe==1.0"
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stage",
    [
        "index_identity",
        "index_sdk",
        "installed_identity",
        "installed_version",
        "installed_sdk",
    ],
)
async def test_mismatching_plugin_is_never_loaded(installation, stage):
    """索引身份错误时不装包；安装产物身份、版本或 SDK 声明不符时不导入插件。"""
    state = installation
    if stage == "index_identity":
        state.remote = metadata(identity="different")
    elif stage == "index_sdk":
        state.remote = metadata(sdk=False)
    else:
        state.package = metadata(
            identity="different" if stage == "installed_identity" else "install_probe",
            version="2.0" if stage == "installed_version" else "1.0",
            sdk=stage != "installed_sdk",
        )
    meta = PluginMeta.build(
        info={
            "package_name": "auto-mas-install-probe",
            "plugin_name": "install_probe",
            "version": "1.0",
        }
    )
    with pytest.raises(PluginPrecheckError):
        await _PluginManager().install(meta)
    assert "install_probe" not in sys.modules
    assert not list(state.registry.values())
    assert bool(state.calls) is (not stage.startswith("index_"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "package",
    ["demo @ https://example.test/demo.whl", "../demo", "demo>=1", "auto-mas-core"],
)
async def test_install_rejects_non_distribution_targets(installation, package):
    """依赖表达式、路径和保留的 core 包不能作为市场安装目标，也不能进入安装进程。"""
    meta = PluginMeta.build(
        info={"package_name": package, "plugin_name": "install_probe", "version": "1.0"}
    )
    with pytest.raises(PluginPrecheckError):
        await _PluginManager().install(meta)
    assert not installation.calls
