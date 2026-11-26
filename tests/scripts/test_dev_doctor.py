"""Worktree 的 VS Code 配置与诊断不得回退到错误的环境。"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts/dev_doctor.py"
SPEC = importlib.util.spec_from_file_location("dev_doctor", MODULE_PATH)
assert SPEC and SPEC.loader
dev_doctor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dev_doctor)


def test_vscode_reuses_verified_shared_interpreter(tmp_path, monkeypatch):
    repo = tmp_path / "worktree"
    repo.mkdir()
    python = tmp_path / "shared" / "python"
    monkeypatch.setattr(dev_doctor, "REPO_ROOT", repo)
    monkeypatch.setattr(dev_doctor, "verified_shared_python", lambda: python)

    assert dev_doctor.main(["--init-vscode", "--port", "36165"]) == 0

    launch = json.loads((repo / ".vscode/launch.json").read_text(encoding="utf-8"))
    (debugger,) = launch["configurations"]
    assert debugger["python"] == str(python)
    assert debugger["type"] == "debugpy"
    assert debugger["env"]["AUTO_MAS_HTTP_PORT"] == "36165"
    assert not (repo / ".venv").exists()


def test_uninherited_windows_pool_does_not_overwrite_launch(tmp_path, monkeypatch):
    monkeypatch.setattr(dev_doctor, "REPO_ROOT", tmp_path)
    monkeypatch.delenv("AUTO_MAS_DEV_ENV_ROOT", raising=False)
    monkeypatch.setattr(dev_doctor, "registered_windows_pool", lambda: True)
    launch = tmp_path / ".vscode/launch.json"
    launch.parent.mkdir()
    launch.write_text('{"name":"existing"}', encoding="utf-8")

    assert dev_doctor.main(["--init-vscode", "--force", "--port", "36165"]) == 1

    assert json.loads(launch.read_text(encoding="utf-8")) == {"name": "existing"}
    assert not (tmp_path / ".venv").exists()


def test_worktree_doctor_checks_development_ports_only(tmp_path, monkeypatch):
    monkeypatch.setattr(dev_doctor, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(dev_doctor, "FRONTEND_DIR", tmp_path / "frontend")
    monkeypatch.setattr(
        dev_doctor, "verified_shared_python", lambda: tmp_path / "shared/python"
    )
    monkeypatch.setattr(dev_doctor, "find_repo_dev_backends", lambda: [])

    def dev_port_only(port: int) -> bool:
        assert port in {36165, dev_doctor.DEFAULT_VITE_PORT}
        return False

    monkeypatch.setattr(dev_doctor, "is_port_open", dev_port_only)
    dev_doctor.main(["--port", "36165"])


def test_vscode_keeps_preflight_diagnostic_with_mixed_console_encoding(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(dev_doctor, "REPO_ROOT", tmp_path)
    monkeypatch.setenv("AUTO_MAS_DEV_ENV_ROOT", str(tmp_path / "共享池"))
    monkeypatch.setattr(dev_doctor.shutil, "which", lambda _: "pwsh")
    run = subprocess.run
    diagnostic = "与当前锁文件不兼容：demo==1.0（实际：未安装）"
    # Git or another native command can emit additional local-code-page output.
    stderr = "控制台提示\n".encode("cp936") + diagnostic.encode("utf-8")

    def run_preflight(_, **kwargs):
        return run(
            [
                sys.executable,
                "-c",
                f"import sys; sys.stderr.buffer.write({stderr!r}); sys.exit(1)",
            ],
            **kwargs,
        )

    monkeypatch.setattr(dev_doctor.subprocess, "run", run_preflight)

    assert dev_doctor.main(["--init-vscode", "--port", "36165"]) == 1
    assert diagnostic in capsys.readouterr().err
    assert not (tmp_path / ".vscode/launch.json").exists()


def test_vscode_rejects_invalid_utf8_interpreter_path(tmp_path, monkeypatch, capsys):
    python = tmp_path / "共享�" / "python"
    python.parent.mkdir()
    python.touch()
    monkeypatch.setattr(dev_doctor, "REPO_ROOT", tmp_path)
    monkeypatch.setenv("AUTO_MAS_DEV_ENV_ROOT", str(python.parent))
    monkeypatch.setattr(dev_doctor.shutil, "which", lambda _: "pwsh")
    run = subprocess.run
    stdout = str(python).encode("utf-8").replace("�".encode("utf-8"), b"\xff") + b"\n"

    def run_preflight(_, **kwargs):
        return run(
            [sys.executable, "-c", f"import sys; sys.stdout.buffer.write({stdout!r})"],
            **kwargs,
        )

    monkeypatch.setattr(dev_doctor.subprocess, "run", run_preflight)

    assert dev_doctor.main(["--init-vscode", "--port", "36165"]) == 1
    assert "UTF-8" in capsys.readouterr().err
    assert not (tmp_path / ".vscode/launch.json").exists()
