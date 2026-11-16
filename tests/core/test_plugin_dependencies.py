"""联合解析保留禁用插件，并将目标宿主真实依赖写入 SDK 发行元数据。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from zipfile import ZipFile

import pytest

from app.plugin.uv import precheck


@pytest.mark.asyncio
async def test_target_lock_uses_future_python_markers_and_rejects_stale_declarations():
    """读取锁文件不依赖目标解释器已安装，且不能混用其他依赖声明的锁文件。"""
    project = """[project]
name="auto-mas"
version="6.0.0"
requires-python=">=3.12"
dependencies=["marker-old; python_version < '3.13'", "marker-new; python_version >= '3.13'"]
"""
    lockfile = """version=1
revision=3
requires-python=">=3.12"
[[package]]
name="auto-mas"
version="6.0.0"
source={virtual="."}
dependencies=[{name="marker-old",marker="python_version < '3.13'"},{name="marker-new",marker="python_version >= '3.13'"}]
[package.metadata]
requires-dist=[{name="marker-old",marker="python_version < '3.13'"},{name="marker-new",marker="python_version >= '3.13'"}]
[[package]]
name="marker-old"
version="1.0"
source={registry="https://pypi.org/simple"}
[[package]]
name="marker-new"
version="2.0"
source={registry="https://pypi.org/simple"}
"""
    assert await precheck.locked_dependencies(
        project=project, lockfile=lockfile, python_version="3.13.2"
    ) == ["marker-new==2.0"]
    with pytest.raises(ValueError, match="依赖声明"):
        await precheck.locked_dependencies(
            project=project.replace("marker-new;", "other-package;"),
            lockfile=lockfile,
            python_version="3.13.2",
        )


@pytest.mark.asyncio
async def test_joint_solver_uses_one_environment_for_all_plugins(monkeypatch):
    """验证依赖预检在同一次解析中联合考虑全部插件与目标 core，防止逐包检查漏掉交叉冲突。"""
    invocations = []

    async def execute(*args, **kwargs):
        """核对临时 core 元数据和两个插件共同进入解析命令，再返回共享依赖冲突结果。"""
        invocations.append(args)
        links = precheck.Path(args[args.index("--find-links") + 1])
        wheel = next(links.glob("*.whl"))
        with ZipFile(wheel) as archive:
            metadata = archive.read(
                next(name for name in archive.namelist() if name.endswith("/METADATA"))
            ).decode()
        assert "Requires-Dist: shared-lib==2" in metadata
        inputs = precheck.Path(args[3]).read_text(encoding="utf-8")
        assert "plugin-a==1" in inputs and "plugin-b==2" in inputs
        return SimpleNamespace(
            returncode=1, stderr="No solution found: conflicting shared-lib", stdout=""
        )

    monkeypatch.setattr(precheck.ProcessRunner, "run_process", execute)
    monkeypatch.setattr(precheck, "ensure", lambda: "uv")
    monkeypatch.setattr(
        precheck,
        "candidates",
        lambda: ["https://first.test/simple", "https://second.test/simple"],
    )
    result = await precheck.resolve_environment(
        targets=["plugin-a==1", "plugin-b==2"],
        core_version="v5.8.0",
        dependencies=["shared-lib==2"],
    )
    assert not result.ok
    assert len(invocations) == 2
    assert result.detail
    assert "No solution found" not in result.detail


@pytest.mark.asyncio
async def test_solver_tries_next_source_when_release_is_not_mirrored(monkeypatch):
    """首源尚未收录已发布版本时继续解析，不能把缺包误判为永久依赖冲突。"""
    mirrors = ["https://mirror.test/simple", "https://official.test/simple"]
    attempted = []

    async def execute(*args, **kwargs):
        """模拟镜像缺包和官方源已有包，并确认切源不放宽宿主及插件版本。"""
        mirror = args[args.index("--index-url") + 1]
        attempted.append(mirror)
        inputs = precheck.Path(args[3]).read_text(encoding="utf-8")
        assert "auto_mas_core-5.9.0b1-py3-none-any.whl" in inputs
        assert "plugin-a==1.0" in inputs
        return SimpleNamespace(
            returncode=1 if mirror == mirrors[0] else 0,
            stderr="No solution found: there is no version of plugin-a==1.0"
            if mirror == mirrors[0]
            else "",
            stdout="",
        )

    mark_ok = AsyncMock()
    monkeypatch.setattr(precheck.ProcessRunner, "run_process", execute)
    monkeypatch.setattr(precheck, "ensure", lambda: "uv")
    monkeypatch.setattr(precheck, "candidates", lambda: mirrors)
    monkeypatch.setattr(precheck, "mark_ok", mark_ok)
    result = await precheck.resolve_environment(
        targets=["plugin-a==1.0"],
        core_version="v5.9.0-beta.1",
        dependencies=["shared-lib==2"],
    )
    assert result.ok
    assert attempted == mirrors
    mark_ok.assert_awaited_once_with(mirrors[1])


@pytest.mark.asyncio
async def test_removed_local_plugin_stays_visible_without_becoming_remote_dependency(
    isolated_app_paths, monkeypatch, tmp_path
):
    """本地工程删除后保留插件中心记录，但不再向 PyPI 请求未发布的包。"""
    from app.models.config import PluginRecord, PluginRegistryCollection
    from app.plugin.runtime import discover
    from app.plugin.types import PluginCodeDrift, SourceChange

    registry = PluginRegistryCollection.build([PluginRecord])
    await registry.activate()
    monkeypatch.setattr(isolated_app_paths, "plugin_registry", registry)
    source = tmp_path / "source"
    (source / "plugins").mkdir(parents=True)
    monkeypatch.setattr(isolated_app_paths, "source_path", source)
    monkeypatch.setattr(
        discover.importlib_metadata, "distributions", lambda **kwargs: []
    )
    uid = registry.add(
        PluginRecord,
        payload={
            "info": {
                "plugin_name": "unpublished-local",
                "package_name": "unpublished-local",
                "version": "1.0",
                "source": "local",
                "enabled": False,
            }
        },
    )
    await registry.commit()
    project = isolated_app_paths.plugins_path / "unpublished-local"
    registry[uid]._project_dir = project / "src"
    # 磁盘上工程已被删除，由真实发现流程将旧登记转换为仅展示的移除记录。
    await discover.refresh(
        scope=discover.RefreshScope(changes=(SourceChange(str(project)),))
    )
    record = registry[uid]
    assert record.info.code_drift == PluginCodeDrift.PACKAGE_REMOVED
    assert record._project_dir is None
    assert precheck.plugin_targets(registry.values()) == []
    assert registry.by_name("unpublished-local") is record
