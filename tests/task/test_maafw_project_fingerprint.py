"""项目指纹只回答「还是我们装下去的那份吗」：运行期产物一个都不能算进去。"""

from pathlib import Path

from app.task.MaaFW.tools.core.automas_maafw_project_update.contracts import (
    project_fingerprint,
)
from app.task.MaaFW.tools.core.automas_maafw_runtime_pool.host_environment import (
    PROJECT_PYCACHE_DIR_NAME,
)


def _write(path: Path, data: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def test_runtime_artifacts_do_not_change_the_fingerprint(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write(project / "interface.json", b'{"name": "demo"}')
    _write(project / "agent" / "main.py", b"print(1)")
    before = project_fingerprint(project)

    _write(project / "debug" / "maafw.log", b"log")
    _write(project / "agent" / "__pycache__" / "main.cpython-313.pyc", b"pyc")
    # PYTHONPYCACHEPREFIX 的镜像树里没有 __pycache__ 这一层，要按目录名单独放行。
    _write(
        project
        / PROJECT_PYCACHE_DIR_NAME
        / "D"
        / "x"
        / "agent"
        / "main.cpython-313.pyc",
        b"pyc",
    )
    _write(project / "config" / "maa_option.json", b"{}")

    assert project_fingerprint(project) == before

    _write(project / "agent" / "main.py", b"print(2)")
    assert project_fingerprint(project) != before
