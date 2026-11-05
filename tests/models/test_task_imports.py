"""任务模型导入即安装订阅，声明阶段不初始化宿主。"""

import os
import subprocess
import sys


def test_task_model_import_binds_updates_without_initializing_core():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import app.models.task; "
            "assert not any(n == 'app.core' or n.startswith('app.core.') "
            "for n in sys.modules); "
            "assert all(any(cls.signal.receivers_for(cls)) "
            "for cls in (app.models.task.TaskItem, app.models.task.TaskScriptItem, "
            "app.models.task.TaskUserItem, app.models.task.LogRecord))",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert result.returncode == 0, result.stderr
