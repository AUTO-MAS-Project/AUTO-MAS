from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest import TestCase


class TestWebSocketImportBoundaries(TestCase):
    def test_utility_websocket_does_not_import_application_core(self) -> None:
        repository_root = Path(__file__).resolve().parents[2]
        probe = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; "
                    "import app.utils.websocket; "
                    "assert 'app.core' not in sys.modules, "
                    "'utility websocket imported app.core'"
                ),
            ],
            cwd=repository_root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        self.assertEqual(
            probe.returncode,
            0,
            msg=f"stdout={probe.stdout!r}\nstderr={probe.stderr!r}",
        )
