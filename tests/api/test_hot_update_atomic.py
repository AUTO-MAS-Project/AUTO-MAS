"""测试空闲时应用后端热更新原子操作。"""

import asyncio
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.task_manager import TaskManager


@pytest.mark.asyncio
async def test_apply_when_idle_success():
    """测试空闲时立即应用。"""
    with (
        patch.object(TaskManager, '_hot_update_block_reason', return_value=None),
        patch('app.core.timer.MainTimer.check_upcoming_scheduled', return_value=None),
        patch('app.core.timer.MainTimer.begin_hot_update'),
        patch('pathlib.Path.cwd') as mock_cwd,
        patch('pathlib.Path.glob') as mock_glob,
        patch('zipfile.ZipFile') as mock_zip,
    ):
        # Mock 文件系统
        fake_path = MagicMock()
        mock_cwd.return_value = fake_path

        # Mock 找到更新包
        fake_zip_path = MagicMock()
        fake_zip_path.name = "UpdatePack_1.0.0.zip"
        fake_zip_path.stem = "UpdatePack_1.0.0"
        fake_path.glob.return_value = [fake_zip_path]

        # Mock zipfile 解压
        mock_zip.return_value.__enter__.return_value.extractall = MagicMock()

        result = await TaskManager.apply_hot_update_atomic('abc123', avoid_minutes=5)

        assert result['applied'] is True


@pytest.mark.asyncio
async def test_apply_deferred_running_task():
    """测试有运行中任务时延期。"""
    with patch.object(TaskManager, '_hot_update_block_reason', return_value='busy'):
        result = await TaskManager.apply_hot_update_atomic('abc123', avoid_minutes=5)

        assert result['applied'] is False
        assert result['reason'] == 'busy'


@pytest.mark.asyncio
async def test_apply_deferred_scheduled_soon():
    """测试定时任务临近时延期。"""
    from datetime import datetime, timedelta, timezone

    next_time = datetime.now(timezone.utc) + timedelta(minutes=3)

    with (
        patch.object(TaskManager, '_hot_update_block_reason', return_value=None),
        patch('app.core.timer.MainTimer.check_upcoming_scheduled', return_value=next_time),
    ):
        result = await TaskManager.apply_hot_update_atomic('abc123', avoid_minutes=5)

        assert result['applied'] is False
        assert result['reason'] == 'scheduledSoon'
        assert result['nextScheduledTime'] == next_time.astimezone(timezone.utc).isoformat()


@pytest.mark.asyncio
async def test_apply_no_package():
    """测试未找到更新包时报错。"""
    with (
        patch.object(TaskManager, '_hot_update_block_reason', return_value=None),
        patch('app.core.timer.MainTimer.check_upcoming_scheduled', return_value=None),
        patch('pathlib.Path.cwd') as mock_cwd,
    ):
        # Mock 没有更新包
        fake_path = MagicMock()
        mock_cwd.return_value = fake_path
        fake_path.glob.return_value = []

        result = await TaskManager.apply_hot_update_atomic('abc123', avoid_minutes=5)

        assert result['applied'] is False
        assert result['reason'] == 'packageNotFound'

