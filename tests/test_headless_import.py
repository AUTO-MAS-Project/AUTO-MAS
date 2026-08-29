import subprocess
import sys
from pathlib import Path


def test_core_imports_without_desktop_dependencies() -> None:
    probe = """
import sys
class BlockDesktopDeps:
    def find_spec(self, name, path=None, target=None):
        if name.split('.')[0] in {'pyautogui', 'mouseinfo', 'pyscreeze', 'Xlib'}:
            raise ImportError(name)
sys.meta_path.insert(0, BlockDesktopDeps())
from app.core import Config, MainTimer, TaskManager
assert 'pyautogui' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
