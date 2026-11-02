"""任务状态模型可在没有宿主运行时的环境中使用。"""

import os
import subprocess
import sys


def test_task_models_do_not_initialize_core():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import app.models.task; "
            "assert not any(n == 'app.core' or n.startswith('app.core.') "
            "for n in sys.modules)",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert result.returncode == 0, result.stderr
