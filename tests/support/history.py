"""History store fixture shared by history-facing tests."""

import pytest_asyncio

import app.core.history as history_module


@pytest_asyncio.fixture
async def store(isolated_app_paths):
    storage = history_module.HistoryStore()
    await storage.initialize(video_limit_bytes=1024 * 1024)
    try:
        yield storage
    finally:
        await storage.close()
