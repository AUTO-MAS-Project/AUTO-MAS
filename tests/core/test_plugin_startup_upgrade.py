"""冷启动联合升级的真实离线求解、安装与同进程启用契约。"""

import importlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from zipfile import ZipFile

import pytest
import tomli_w

from app.core.plugin.manager import _PluginManager
from app.models.config import PluginMeta, PluginRecord, PluginRegistryCollection
from app.plugin.errors import PluginError
from app.plugin.uv import ops, precheck


@pytest.fixture(autouse=True)
def isolated_installed_plugins():
    """联合环境用例只发现其临时发行包，专项测试依赖继续由专项夹具装配。"""
    test_plugins = Path(__file__).resolve().parents[2] / ".test-plugins"
    # 让用例自己的路径调整先撤销，再恢复专项测试的发行包路径。
    with pytest.MonkeyPatch.context() as isolated:
        isolated.setattr(
            sys, "path", [item for item in sys.path if item != str(test_plugins)]
        )
        yield


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [True, False])
async def test_installation_confirmation_preserves_backup_on_pre_enable_failure(
    isolated_app_paths, monkeypatch, enabled
):
    """需要启用的插件预检查失败时不能确认安装或删除原件；用户停用的插件仍可确认。"""
    from uuid import uuid4

    from app.models.schema import PluginInstallation
    from app.plugin.uv import environment

    config = isolated_app_paths
    registry = PluginRegistryCollection.build([PluginRecord])
    await registry.activate()
    monkeypatch.setattr(config, "plugin_registry", registry)
    source = config.plugins_path / "enable_probe"
    source.mkdir(parents=True)
    (source / "__init__.py").write_text(
        "from app.plugin.base import BasePlugin\n"
        "class Plugin(BasePlugin):\n"
        "    async def pre_enable(self):\n"
        "        raise RuntimeError('pre-enable rejected')\n"
        "PLUGIN = Plugin\n",
        encoding="utf-8",
    )
    uid = registry.add(
        PluginRecord,
        payload={
            "info": {
                "plugin_name": "enable_probe",
                "import_name": "enable_probe",
                "enabled": enabled,
            }
        },
    )
    await registry.commit()
    record = registry[uid]
    record._project_dir = config.plugins_path
    manager = _PluginManager()
    await manager.load(record)
    if enabled:
        with pytest.raises(RuntimeError, match="pre-enable rejected"):
            await manager.enable(record)
    assert record.info.state == "disabled"
    installation_id = uuid4()
    previous = ops.site_dir(activate=False).with_suffix(".previous")
    backup = previous.parent / f".publish-{installation_id}"
    previous.mkdir()
    backup.mkdir()
    environment.write_installation(
        environment.InstallationRecord(
            progress=PluginInstallation(
                installationId=installation_id,
                metaId=uuid4(),
                packageName="enable-probe",
                pluginName="enable_probe",
                version="1.0",
                state="applying",
            ),
            core_version="5.9.0b1",
            host_constraints=[],
            baseline={},
        )
    )
    if enabled:
        with pytest.raises(PluginError):
            environment.finish_installation()
        assert environment.read_installation().progress.state == "failed"
        assert previous.is_dir() and backup.is_dir()
    else:
        environment.finish_installation()
        assert environment.read_installation().progress.state == "succeeded"
        assert not previous.exists() and not backup.exists()
    await manager.unload(record)


def wheel(
    directory, *, name, version, requires=(), module="", content="", plugin_id=None
):
    """生成标准离线 wheel，供真实 uv 求解与安装，不替换依赖算法。"""
    safe = name.replace("-", "_")
    info = f"{safe}-{version}.dist-info"
    path = directory / f"{safe}-{version}-py3-none-any.whl"
    with ZipFile(path, "w") as archive:
        archive.writestr(
            f"{info}/METADATA",
            "\n".join(
                [
                    "Metadata-Version: 2.1",
                    f"Name: {name}",
                    f"Version: {version}",
                    f"Keywords: auto-mas-plugin, auto-mas-id:{plugin_id or 'startup_probe'}"
                    if plugin_id is not None or module == "startup_probe"
                    else "",
                    *(f"Requires-Dist: {item}" for item in requires),
                    "",
                    "",
                ]
            ),
        )
        archive.writestr(
            f"{info}/WHEEL",
            "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        files = []
        if module:
            file = f"{module}/__init__.py"
            archive.writestr(file, content)
            files.append(file)
        archive.writestr(
            f"{info}/RECORD",
            "\n".join(
                f"{file},,"
                for file in [
                    *files,
                    f"{info}/METADATA",
                    f"{info}/WHEEL",
                    f"{info}/RECORD",
                ]
            ),
        )
    return path


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode",
    ["hot", "hot_reload", "hot_recover", "restart", "failed_start", "hot_io_failure"],
)
async def test_runtime_install_keeps_loaded_dependencies_until_new_process(
    isolated_app_paths, monkeypatch, tmp_path, mode
):
    """真实 uv 安装验证热导入、新进程换版及启动失败后的原环境恢复。"""
    config = isolated_app_paths
    source = tmp_path / "source"
    source.mkdir()
    (source / "pyproject.toml").write_text(
        '[project]\nname="auto-mas"\nversion="5.9.0b1"\ndependencies=[]\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "source_path", source)
    registry = PluginRegistryCollection.build([PluginRecord])
    await registry.activate()
    monkeypatch.setattr(config, "plugin_registry", registry)
    target = ops.site_dir(activate=False)
    monkeypatch.syspath_prepend(str(target))
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    shared = wheel(
        wheels,
        name="probe-shared",
        version="1.0",
        module="probe_shared",
        content='VERSION="1.0"\n',
    )
    existing = wheel(
        wheels,
        name="startup-probe",
        version="1.0",
        module="startup_probe",
        requires=["auto-mas-core>=5,<6", "probe-shared>=1,<3"],
        content=(
            'raise ImportError("old host interface unavailable")\n'
            if mode == "hot_recover"
            else "from app.plugin.base import BasePlugin\nclass Plugin(BasePlugin): pass\nPLUGIN=Plugin\n"
        ),
    )
    for path in (shared, existing):
        with ZipFile(path) as archive:
            archive.extractall(target)
    uid = registry.add(
        PluginRecord,
        payload={
            "info": {
                "plugin_name": "startup_probe",
                "package_name": "startup-probe",
                "version": "1.0",
                "source": "installed",
                "state": "disabled",
                "enabled": mode == "hot_recover",
            }
        },
    )
    await registry.commit()
    registry[uid]._project_dir = target
    wheel(
        wheels,
        name="probe-shared",
        version="2.0",
        module="probe_shared",
        content='VERSION="2.0"\nADDED="new API"\n',
    )
    candidate = wheel(
        wheels,
        name="install-probe",
        version="1.0",
        module="install_probe",
        plugin_id="install_probe",
        requires=["auto-mas-core>=5,<6", "probe-shared>=2,<3"],
        content="from probe_shared import ADDED\nfrom app.plugin.base import BasePlugin\nclass Plugin(BasePlugin): pass\nPLUGIN=Plugin\n",
    )
    if mode in {"hot_reload", "hot_recover"}:
        candidate = wheel(
            wheels,
            name="startup-probe",
            version="2.0",
            module="startup_probe",
            requires=["auto-mas-core>=5,<6", "probe-shared>=2,<3"],
            content="from probe_shared import ADDED\nfrom app.plugin.base import BasePlugin\nclass Plugin(BasePlugin): MARKER=ADDED\nPLUGIN=Plugin\n",
        )
    monkeypatch.setattr(precheck, "candidates", lambda: ["https://offline.test/simple"])
    execute = precheck.ProcessRunner.run_process

    async def offline(*args, **kwargs):
        """只替换包索引边界，保留生产 uv 求解、完整安装及结果校验。"""
        args = list(args)
        index = args.index("--index-url")
        args[index : index + 2] = ["--no-index", "--find-links", str(wheels)]
        return await execute(*args, **kwargs)

    monkeypatch.setattr(precheck.ProcessRunner, "run_process", offline)
    from email.parser import Parser

    from app.core.i18n import I18n
    from app.plugin.runtime import market_index

    previous_sources = dict(I18n._plugin_sources)
    with ZipFile(candidate) as archive:
        declaration = Parser().parsestr(
            archive.read(
                next(
                    path
                    for path in archive.namelist()
                    if path.endswith(".dist-info/METADATA")
                )
            ).decode()
        )

    async def fetch_metadata(*args, **kwargs):
        """以真实 wheel 声明替代远端索引，保留安装入口的身份校验。"""
        return declaration

    monkeypatch.setattr(market_index, "fetch_metadata", fetch_metadata)
    old = (
        importlib.import_module("probe_shared")
        if mode in {"restart", "failed_start"}
        else None
    )
    try:
        meta = PluginMeta.build(
            info={
                "package_name": "install-probe",
                "plugin_name": "install_probe",
                "version": "1.0",
            }
        )
        manager = _PluginManager()
        previous_class = None
        if mode in {"hot_reload", "hot_recover"}:
            if mode == "hot_recover":
                from app.plugin.errors import PluginPrecheckError

                registry[uid].info.import_name = "startup_probe"
                with pytest.raises(PluginPrecheckError, match="startup_probe"):
                    await manager.load(registry[uid])
                assert registry[uid].info.state == "fault_load"
            else:
                await manager.load(registry[uid])
            previous_class = registry[uid]._plugin_cls
            meta = PluginMeta.build(
                info={
                    "package_name": "startup-probe",
                    "plugin_name": "startup_probe",
                    "version": "2.0",
                }
            )
        if mode == "hot_io_failure":
            replace, copy = Path.replace, shutil.copy2

            def fail_publish(path, destination):
                """在新版依赖已发布后模拟后续元数据文件替换失败。"""
                if Path(destination) == target / "probe_shared-2.0.dist-info/RECORD":
                    raise OSError("publication failed")
                return replace(path, destination)

            def fail_restore(source, destination, *args, **kwargs):
                """模拟即时恢复仍受磁盘故障影响，验证恢复原件不会被回收。"""
                if (
                    "original" in Path(source).parts
                    and Path(destination) == target / "probe_shared/__init__.py"
                ):
                    raise OSError("restore failed")
                return copy(source, destination, *args, **kwargs)

            with monkeypatch.context() as failure:
                failure.setattr(Path, "replace", fail_publish)
                failure.setattr(shutil, "copy2", fail_restore)
                with pytest.raises(OSError, match="restore failed"):
                    await manager.install(meta)
            assert list(target.parent.glob(".publish-*/files.json"))
        else:
            result = await manager.install(meta)
            assert bool(result.get("restart_required")) is (
                mode in {"restart", "failed_start"}
            )
        if mode in {"hot", "hot_reload", "hot_recover"}:
            installed = importlib.import_module(
                "install_probe" if mode == "hot" else "startup_probe"
            )
            assert installed.ADDED == "new API"
            assert importlib.metadata.version("probe-shared") == "2.0"
            if mode in {"hot_reload", "hot_recover"}:
                assert registry.by_name("startup_probe") is registry[uid]
                assert registry[uid]._plugin_cls is not previous_class
                assert registry[uid]._plugin_cls.MARKER == "new API"
            if mode == "hot_recover":
                assert registry[uid].info.state == "enabled"
            from app.plugin.uv.environment import read_installation

            assert read_installation().progress.state == "succeeded"
            return
        if old is not None:
            assert sys.modules["probe_shared"] is old
            assert old.VERSION == "1.0"
            assert not (target / "install_probe").exists()
            assert importlib.metadata.version("probe-shared") == "1.0"
        child = tmp_path / "verify_new_process.py"
        child.write_text(
            textwrap.dedent("""
            import asyncio, importlib, sys
            from pathlib import Path
            from app.core import Config
            from app.models.config import PluginRecord, PluginRegistryCollection
            from app.plugin.uv import ops, environment
            Config.source_path = Path(sys.argv[1])
            Config.plugins_path = Path(sys.argv[2])
            async def verify():
                registry = PluginRegistryCollection.build([PluginRecord])
                await registry.activate()
                Config.plugin_registry = registry
                if sys.argv[3].startswith("rollback"):
                    if sys.argv[3] == "rollback_loaded":
                        registry.add(PluginRecord, payload={"info": {
                            "plugin_name": "install_probe", "package_name": "install-probe",
                            "source": "installed", "version": "1.0", "state": "fault_load",
                        }})
                        await registry.commit()
                    assert not await environment.apply_pending()
                    ops.site_dir()
                    assert importlib.import_module("probe_shared").VERSION == "1.0"
                    assert not (ops.site_dir() / "install_probe/__init__.py").exists()
                    try:
                        importlib.metadata.distribution("install-probe")
                    except importlib.metadata.PackageNotFoundError:
                        pass
                    else:
                        raise AssertionError("failed installation retained distribution metadata")
                    assert environment.read_installation().progress.state == "failed"
                    assert registry.by_name("install_probe") is None
                    return
                await ops.prepare_environment()
                ops.site_dir()
                plugin = importlib.import_module("install_probe")
                assert plugin.ADDED == "new API"
                uid = registry.add(PluginRecord, payload={"info": {
                    "plugin_name": "install_probe", "version": "1.0",
                    "state": "fault_load" if sys.argv[3] == "failed_start" else "disabled",
                }})
                await registry.commit()
                environment.finish_installation()
                assert environment.read_installation().progress.state == "succeeded"
                assert not ops.site_dir().with_suffix(".previous").exists()
            asyncio.run(verify())
        """),
            encoding="utf-8",
        )
        env = dict(
            os.environ,
            PYTHONPATH=str(Path(__file__).resolve().parents[2]),
            AUTO_MAS_ENV="development",
        )
        args = [
            sys.executable,
            "-X",
            "utf8",
            str(child),
            str(source),
            str(config.plugins_path),
        ]
        result = subprocess.run(
            [*args, "rollback" if mode == "hot_io_failure" else mode],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        assert (result.returncode != 0) is (mode == "failed_start"), (
            result.stdout + result.stderr
        )
        if mode == "failed_start":
            assert "新插件环境加载失败" in result.stderr
            result = subprocess.run(
                [*args, "rollback_loaded"],
                cwd=tmp_path,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
            )
            assert result.returncode == 0, result.stdout + result.stderr
        if old is not None:
            assert old.VERSION == "1.0"
    finally:
        I18n.set_plugin_sources(previous_sources)
        for name in ("probe_shared", "startup_probe", "install_probe"):
            sys.modules.pop(name, None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "enabled, compatible, local",
    [
        (True, True, False),
        (False, True, False),
        (True, False, False),
        (True, True, True),
    ],
)
async def test_cold_upgrade_preserves_host_and_config_and_enables_without_restart(
    isolated_app_paths, monkeypatch, tmp_path, enabled, compatible, local
):
    """旧代码不导入；成功后原进程可启用，宿主冲突时保留原安装和全部配置。"""
    config = isolated_app_paths
    source = tmp_path / "source"
    (source / "plugins").mkdir(parents=True)
    (source / "pyproject.toml").write_text(
        '[project]\nname="auto-mas"\nversion="6.0.0"\ndependencies=["probe-host==1.0"]\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "source_path", source)
    monkeypatch.setattr(config, "VERSION", "v6.0.0")
    registry = PluginRegistryCollection.build([PluginRecord])
    await registry.activate()
    monkeypatch.setattr(config, "plugin_registry", registry)
    target = ops.site_dir(activate=False)
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    host = tmp_path / "host"
    host.mkdir()
    host_wheel = wheel(
        wheels,
        name="probe-host",
        version="1.0",
        module="probe_host",
        content='VERSION="1.0"\n',
    )
    with ZipFile(host_wheel) as archive:
        archive.extractall(host)
    old = wheel(
        wheels,
        name="startup-probe",
        version="1.0",
        module="startup_probe",
        requires=["auto-mas-core>=5,<6", "probe-host==1.0"],
        content='raise RuntimeError("old plugin imported")\n',
    )
    with ZipFile(old) as archive:
        archive.extractall(target)
    wheel(wheels, name="probe-host", version="2.0")
    wheel(
        wheels,
        name="startup-probe",
        version="2.0",
        module="startup_probe",
        requires=[
            "auto-mas-core>=6,<7",
            f"probe-host=={'1.0' if compatible else '2.0'}",
        ],
        content='from app.plugin.base import BasePlugin\nimport probe_host\nclass Plugin(BasePlugin):\n    async def on_enable(self):\n        self.result = ("2.0", probe_host.VERSION)\nPLUGIN=Plugin\n',
    )
    uid = registry.add(
        PluginRecord,
        payload={
            "info": {
                "plugin_name": "startup_probe",
                "package_name": "startup-probe",
                "import_name": "startup_probe",
                "version": "1.0",
                "source": "installed",
                "enabled": enabled,
            }
        },
    )
    await registry.commit()
    registry[uid]._project_dir = target
    if local:
        project = source / "plugins/local"
        module = project / "src/startup_probe"
        module.mkdir(parents=True)
        (project / "pyproject.toml").write_text(
            tomli_w.dumps(
                {
                    "project": {
                        "name": "startup-probe",
                        "version": "3.0",
                        "requires-python": ">=3.12",
                        "keywords": ["auto-mas-plugin", "auto-mas-id:startup_probe"],
                        "dependencies": ["auto-mas-core>=6,<7", "probe-host==1.0"],
                    }
                }
            ),
            encoding="utf-8",
        )
        (module / "__init__.py").write_text(
            'from app.plugin.base import BasePlugin\nimport probe_host\nclass Plugin(BasePlugin):\n    async def on_enable(self):\n        self.result = ("3.0", probe_host.VERSION)\nPLUGIN=Plugin\n',
            encoding="utf-8",
        )
        registry[uid].info.source = "local"
        registry[uid].info.version = "3.0"
        await registry[uid].commit()
        registry[uid]._project_dir = project / "src"
    saved = config.config_path / "upgrade-probe.yaml"
    saved.parent.mkdir(parents=True, exist_ok=True)
    saved.write_bytes(b"account: keep\n")
    monkeypatch.syspath_prepend(str(host))
    monkeypatch.syspath_prepend(str(target))
    monkeypatch.setattr(precheck.site, "getsitepackages", lambda: [str(host)])
    monkeypatch.setattr(precheck, "candidates", lambda: ["https://offline.test/simple"])
    execute = precheck.ProcessRunner.run_process

    async def offline(*args, **kwargs):
        """仅将外部 PyPI 替换为本地 wheel 集合，仍执行真实 uv 解析和安装。"""
        args = list(args)
        index = args.index("--index-url")
        args[index : index + 2] = ["--no-index", "--find-links", str(wheels)]
        return await execute(*args, **kwargs)

    monkeypatch.setattr(precheck.ProcessRunner, "run_process", offline)
    host_module = importlib.import_module("probe_host")
    from app.core.i18n import I18n

    previous_sources = dict(I18n._plugin_sources)
    before = (target / "startup_probe" / "__init__.py").read_bytes()
    try:
        conflicts = await precheck.precheck_core_bump(
            "v6.0.0",
            plugins=registry.values(),
            dependencies=["probe-host==1.0"],
            python_version=platform.python_version(),
        )
        assert bool(conflicts) is not compatible
        if not compatible:
            with pytest.raises(PluginError):
                await ops.prepare_environment()
            assert (target / "startup_probe" / "__init__.py").read_bytes() == before
        else:
            await ops.prepare_environment()
            assert "startup_probe" not in sys.modules
            assert not (target / "probe_host").exists()
            expected_version = "1.0" if local else "2.0"
            assert json.loads(
                (target.parent / "environment.json").read_text(encoding="utf-8")
            )["plugins"] == (
                [str(project.resolve())] if local else ["startup-probe==2.0"]
            )
            assert json.loads(
                (target.parent / "environment.json").read_text(encoding="utf-8")
            )["installed"] == {"startup-probe": expected_version}
            assert (
                importlib.metadata.Distribution.at(
                    target / f"startup_probe-{expected_version}.dist-info"
                ).version
                == expected_version
            )
            ops.site_dir()
            if local:
                from app.plugin.runtime import discover

                await discover.refresh(installed_path=target)
                assert registry.by_name("startup_probe") is registry[uid]
                assert registry[uid].info.source == "local"
                assert registry[uid].info.is_local
            if enabled:
                if local:
                    from app.plugin.runtime import loader

                    plugin = loader.load(registry[uid])()
                else:
                    plugin = importlib.import_module("startup_probe").PLUGIN()
                await plugin.on_enable()
                assert plugin.result == ("3.0" if local else "2.0", "1.0")
        assert sys.modules["probe_host"] is host_module
        assert registry[uid].info.enabled is enabled
        assert saved.read_bytes() == b"account: keep\n"
    finally:
        I18n.set_plugin_sources(previous_sources)
        sys.modules.pop("startup_probe", None)
        sys.modules.pop("probe_host", None)
