"""Real pip regression with synthetic packages; no external index or live install."""

import asyncio
import base64
import hashlib
import importlib.metadata
import importlib.util
import inspect
import io
import os
import sys
import tarfile
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from packaging.version import Version

from app.task.Whimbox.tools import update
from app.utils.common.process.runner import ProcessRunner
from app.utils.common.proxy_env import proxy_environment

PIP_BOOTSTRAP = (
    "import runpy,sys; sys.path.insert(0,sys.argv.pop(1)); "
    "runpy.run_module('pip',run_name='__main__')"
)


def write_wheel(directory, name, version, requirements=()):
    filename = f"{name}-{version}-py3-none-any.whl"
    info = f"{name}-{version}.dist-info"
    metadata = f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
    metadata += "".join(f"Requires-Dist: {value}\n" for value in requirements)
    with zipfile.ZipFile(directory / filename, "w") as bundle:
        bundle.writestr(f"{name}/__init__.py", "")
        bundle.writestr(f"{info}/METADATA", metadata)
        bundle.writestr(
            f"{info}/WHEEL",
            "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        bundle.writestr(f"{info}/RECORD", "")
    return filename


@pytest.fixture
def pip_runtime(tmp_path):
    # Use Python's bundled pip offline, even when uv's test venv has no pip.
    spec = importlib.util.find_spec("pip")
    if spec is not None and spec.origin is not None:
        return Path(spec.origin).parent.parent
    directory = tmp_path / "pip-runtime"
    bundle = next(
        entry
        for entry in files("ensurepip").joinpath("_bundled").iterdir()
        if entry.name.startswith("pip-") and entry.name.endswith(".whl")
    )
    with zipfile.ZipFile(io.BytesIO(bundle.read_bytes())) as archive:
        archive.extractall(directory)
    return directory


@pytest.fixture
def real_update(tmp_path, monkeypatch, pip_runtime):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "Whimbox"
    (root / "python-embedded").mkdir(parents=True)
    (root / update.APP_EXE_NAME).touch()
    (root / update.REL_PYTHON_EXE).touch()
    sentinel = root / "existing-backend"
    sentinel.write_text("old-backend", encoding="utf-8")
    index = tmp_path / "index"
    index.mkdir()
    main = write_wheel(index, "whimbox", "3.1.1", ("mas-test-dependency==1.0",))
    builder = index / write_wheel(index, "mas_test_builder", "1.0")
    # Build-only dependencies are not copied by pip download; pip wheel instead
    # completes the source build before entering the live installation stage.
    build = (
        "[build-system]\nrequires = ['mas-test-builder==1.0']\n"
        "build-backend = 'backend'\nbackend-path = ['.']\n"
    )
    backend = (
        "import zipfile\nfrom pathlib import Path\n"
        + inspect.getsource(write_wheel)
        + "\ndef build_wheel(wheel_directory, config_settings=None, "
        "metadata_directory=None):\n"
        "    return write_wheel(Path(wheel_directory), 'mas_test_dependency', '1.0')\n"
    )
    source = index / "mas_test_dependency-1.0.tar.gz"
    with tarfile.open(source, "w:gz") as archive:
        for name, content in {"pyproject.toml": build, "backend.py": backend}.items():
            data = content.encode()
            entry = tarfile.TarInfo(f"mas_test_dependency-1.0/{name}")
            entry.size = len(data)
            archive.addfile(entry, io.BytesIO(data))
    target = tmp_path / "installed"
    wheel = (index / main).read_bytes()
    monkeypatch.setattr(update, "find_upstream_pids", lambda root: [])
    monkeypatch.setattr(
        update,
        "Config",
        SimpleNamespace(
            proxy=None,
            setting=SimpleNamespace(Update=SimpleNamespace(FluxdownTakeoverAll=False)),
        ),
    )
    monkeypatch.setattr(
        update,
        "request_release",
        AsyncMock(
            return_value={
                "tag_name": "3.1.1",
                "assets": [
                    {
                        "name": main,
                        "digest": "sha256:" + hashlib.sha256(wheel).hexdigest(),
                    }
                ],
            }
        ),
    )

    async def download(url, path, **kwargs):
        path.write_bytes(wheel)

    monkeypatch.setattr(update, "download_file", download)
    monkeypatch.setattr(
        update,
        "installed_version",
        AsyncMock(side_effect=[Version("3.1.0"), Version("3.1.1")]),
    )
    phases = []

    async def run(root, *args, timeout=30, env=None):
        if "check" in args or "-c" in args:
            return ""
        command = list(args[2:])
        phase = next(
            value for value in command if value in {"wheel", "download", "install"}
        )
        phases.append((phase, update.pending_marker(root).exists()))
        if "--index-url" in command:
            position = command.index("--index-url")
            assert command[position + 1] == "https://pypi.org/simple/"
            command[position : position + 2] = [
                "--no-index",
                "--find-links",
                str(index),
            ]
        if phase == "install":
            command += ["--target", str(target)]
        result = await ProcessRunner.run_process(
            sys.executable,
            "-I",
            "-c",
            PIP_BOOTSTRAP,
            str(pip_runtime),
            "--no-cache-dir",
            *command,
            cwd=root,
            timeout=30,
            env=env,
            kill_tree_on_cancel=True,
        )
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        return result.stdout

    monkeypatch.setattr(update, "run_python", run)
    return SimpleNamespace(
        root=root, target=target, builder=builder, sentinel=sentinel, phases=phases
    )


@pytest.mark.asyncio
async def test_real_source_dependency_is_built_before_offline_install(real_update):
    await update.ensure_backend_updated(real_update.root)
    installed = {
        package.metadata["Name"]: package.version
        for package in importlib.metadata.distributions(path=[str(real_update.target)])
    }
    assert installed["whimbox"] == "3.1.1"
    assert installed["mas_test_dependency"] == "1.0"
    assert real_update.phases == [("wheel", False), ("install", True)]
    assert real_update.sentinel.read_text(encoding="utf-8") == "old-backend"
    assert not update.pending_marker(real_update.root).exists()


@pytest.mark.asyncio
async def test_real_build_failure_never_starts_installation(real_update):
    real_update.builder.unlink()
    with pytest.raises(RuntimeError):
        await update.ensure_backend_updated(real_update.root)
    assert real_update.phases == [("wheel", False)]
    assert not update.pending_marker(real_update.root).exists()
    assert not real_update.target.exists()
    assert real_update.sentinel.read_text(encoding="utf-8") == "old-backend"


@pytest.mark.asyncio
async def test_real_isolated_pip_uses_authenticated_proxy(pip_runtime, tmp_path):
    seen = []

    class Proxy(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append((self.path, self.headers.get("Proxy-Authorization")))
            self.send_response(407)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Proxy)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    auth = ("mas-test-user", "private-test-password")
    proxy = httpx.Proxy(f"http://127.0.0.1:{server.server_port}", auth=auth)
    original = dict(os.environ)
    try:
        result = await ProcessRunner.run_process(
            sys.executable,
            "-I",
            "-c",
            PIP_BOOTSTRAP,
            str(pip_runtime),
            "--isolated",
            "--no-cache-dir",
            "download",
            "--no-deps",
            "--no-input",
            "--disable-pip-version-check",
            "--retries",
            "0",
            "--timeout",
            "2",
            "--trusted-host",
            "mas-pip-test.invalid",
            "--index-url",
            "http://mas-pip-test.invalid/simple/",
            "--dest",
            str(tmp_path / "downloads"),
            "mas-nonexistent-test-package",
            timeout=15,
            env=proxy_environment(proxy),
            kill_tree_on_cancel=True,
        )
    finally:
        await asyncio.to_thread(server.shutdown)
        server.server_close()
        thread.join(timeout=2)
    assert seen
    assert all("mas-pip-test.invalid/simple/" in path for path, _ in seen)
    expected = "Basic " + base64.b64encode(":".join(auth).encode()).decode()
    assert all(header == expected for _, header in seen)
    assert result.returncode != 0  # Deliberate proxy rejection, not download success.
    assert auth[1] not in result.stdout + result.stderr
    assert os.environ == original
