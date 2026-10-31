"""证明根入口参数与后端契约的错误确实会被开发工具拒绝。"""

import subprocess
import sys
from pathlib import Path


def test_checker_rejects_bad_call_bad_return_and_missing_method(tmp_path):
    source = tmp_path / "invalid_platform_consumer.py"
    source.write_text(
        """
from pathlib import Path
from app import utils
from app.services.contracts.custom_script import ScriptCommandAPI

utils.window.get_window_handles("invalid PID")

class WrongReturn:
    def build(self, script_path: Path) -> int:
        return 1

class MissingMethod:
    pass

wrong: ScriptCommandAPI = WrongReturn()
missing: ScriptCommandAPI = MissingMethod()
""",
        encoding="utf-8",
    )
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--config-file",
            str(root / "mypy-platform.ini"),
            "--platform",
            "linux",
            "--no-error-summary",
            str(source),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.count("[arg-type]") == 1, result.stdout
    assert result.stdout.count("[assignment]") == 2, result.stdout
