"""真实通用脚本通过 MAS 原生采集同时提供过程节点和旧报告。"""

import asyncio
import json
import shlex
import shutil
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.api import dispatch
from app.core import Notify
from app.models.config import GeneralConfig
from app.models.task import TaskMode
from app.task.general.manager import GeneralManager
from tests.support.scheduler import scheduler as scheduler


@pytest.mark.asyncio
async def test_general_observation_reuses_the_task_log(
    scheduler, isolated_app_paths, monkeypatch, tmp_path
):
    manager, scripts, _, script_id = scheduler
    app_root = tmp_path / "mas"
    app_root.mkdir()
    monkeypatch.chdir(app_root)
    monkeypatch.setattr(dispatch, "TaskManager", manager)
    monkeypatch.setattr(manager, "manager_factories", {GeneralConfig: GeneralManager})
    push_report = AsyncMock()
    monkeypatch.setattr(Notify, "push_proxy_result", push_report)
    monkeypatch.setattr(Notify, "send_statistics", AsyncMock())
    script = scripts[script_id]
    user_id, user = next(script.UserData.items())
    user.Info.Base = "native"
    await user.commit()
    isolated_app_paths.work_path = app_root
    isolated_app_paths.install_path = isolated_app_paths.work_path
    external = tmp_path / "external"
    external.mkdir()
    log = external / "script.log"
    entry = external / "run.py"
    entry.write_text(
        "from datetime import datetime\n"
        "from pathlib import Path\n"
        "import time\n"
        "time.sleep(1.1)\n"
        "p = Path(__file__).with_name('script.log')\n"
        "p.write_text(f'{datetime.now():%Y-%m-%d %H:%M:%S} STEP collected\\n'"
        ' + \'@@LOGBOX@@{"op":"push","type":"普通","text":"reported"}\\n\', encoding=\'utf-8\')\n'
        "time.sleep(3)\n"
        "with p.open('a', encoding='utf-8') as f:\n"
        "    f.write(f'{datetime.now():%Y-%m-%d %H:%M:%S} FINISHED\\n')\n"
        "time.sleep(3)\n",
        encoding="utf-8",
    )
    (external / "config.json").write_text("{}", encoding="utf-8")
    python = Path(sys._base_executable)
    if sys.platform == "win32":
        executable = external / python.name
        shutil.copy2(python, executable)
        for dll in python.parent.glob("*.dll"):
            shutil.copy2(dll, external)
        monkeypatch.setenv("PYTHONHOME", sys.base_prefix)
    else:
        executable = external / "run-script"
        executable.write_text(
            f'#!/bin/sh\nexec {shlex.quote(sys.executable)} "$@"\n', encoding="utf-8"
        )
        executable.chmod(0o755)
    script.Script.ScriptPath = executable
    script.Script.Arguments = f'"{entry.as_posix()}"'
    script.Script.ConfigPath = external / "config.json"
    script.Script.LogPath = log
    script.Script.LogPathFormat = ""
    script.Script.LogTimeEnd = 19
    script.Script.PushLogEnabled = True
    script.Script.PushLogPatterns = json.dumps(
        [{"type": "regex", "match": "STEP", "extract": "$(STEP (.*))"}]
    )
    script.Script.SuccessLog = "FINISHED"
    script.Game.Enabled = False
    await script.commit()

    task_id = await manager.start(
        TaskMode.AUTO_PROXY,
        {
            0: {
                "uid": "-",
                "children": {
                    0: {"uid": str(script_id), "children": {0: {"uid": str(user_id)}}}
                },
            }
        },
    )
    run = manager.task_handler[task_id]
    script_run = next(run.task_info.scripts.values())
    app = FastAPI()
    app.include_router(dispatch.router)
    path = f"/api/dispatch/task/{task_id}/runs/{script_run.uid}/log-nodes"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        async with asyncio.timeout(12):
            while True:
                user_run = next(script_run.users.values())
                page = (
                    await client.get(path, params={"userRunId": str(user_run.uid)})
                ).json()
                if len(page["nodes"]) >= 2 or run.accomplish.is_set():
                    break
                await asyncio.sleep(0.1)
        assert [(node["text"], node["source"]) for node in page["nodes"]] == [
            ("collected", "mas"),
            ("reported", "mas"),
        ]
        assert page["closeReason"] is None
        await asyncio.wait_for(run.accomplish.wait(), 25)
        assert manager.get_task_status(str(task_id)).status == "success"
        page = (await client.get(path, params={"userRunId": str(user_run.uid)})).json()
        assert page["closeReason"] == "complete"
        push_report.assert_awaited_once()
        assert "collected" in push_report.call_args.kwargs["report"].result
        assert "reported" in push_report.call_args.kwargs["report"].result
