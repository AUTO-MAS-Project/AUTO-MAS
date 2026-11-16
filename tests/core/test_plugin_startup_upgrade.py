"""冷启动联合升级的真实离线求解、安装与同进程启用契约。"""

import importlib
import importlib.metadata
import json
import platform
import sys
from zipfile import ZipFile

import pytest
import tomli_w

from app.models.config import PluginRecord, PluginRegistryCollection
from app.plugin.errors import PluginError
from app.plugin.uv import ops, precheck


def wheel(directory, *, name, version, requires=(), module="", content=""):
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
                    "Keywords: auto-mas-plugin, auto-mas-id:startup_probe"
                    if module == "startup_probe"
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
