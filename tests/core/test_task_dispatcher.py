from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from app.core.task_dispatcher import TaskDispatcher
from app.models.task import TaskMode
from app.task import ExpandError


def test_start_rejects_missing_script_before_registering_task() -> None:
    async def run() -> None:
        dispatcher = type(TaskDispatcher)()
        missing_script_id = str(uuid4())

        with pytest.raises(ExpandError, match="脚本不存在"):
            await dispatcher.start(
                mode=TaskMode.SCRIPT_CONFIG,
                queue_id=None,
                script_id=missing_script_id,
                user_id=None,
            )

        assert list(dispatcher.running_items()) == []

    asyncio.run(run())
