import httpx
import pytest
from fastapi import FastAPI

from app.api.setting import router
from app.core.config.upgrade_backup import UpgradeBackup


@pytest.mark.asyncio
async def test_only_local_desktop_can_move_upgrade_backups(tmp_path, monkeypatch):
    backup = UpgradeBackup(root=tmp_path, desktop_version="5.9.0")
    assert backup.prepare() is None
    assert backup.begin_migration()
    backup.finish()
    app = FastAPI()
    app.include_router(router)
    app.state.upgrade_backup = backup
    monkeypatch.setenv("AUTO_MAS_UPGRADE_BACKUP_TOKEN", "desktop-fixture")
    destination = tmp_path / "selected"
    path = "/api/setting/backup/directory"
    payload = {"directory": str(destination), "expected": str(tmp_path / "backup")}
    headers = {"X-Auto-Mas-Upgrade-Backup": "desktop-fixture"}

    transport = httpx.ASGITransport(app=app, client=("192.0.2.10", 50000))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as remote:
        assert (
            await remote.post(path, json=payload, headers=headers)
        ).status_code == 403
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 50000))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as local:
        assert (await local.post(path, json=payload)).status_code == 403
        assert not destination.exists()
        assert (await local.post(path, json=payload, headers=headers)).json()[
            "directory"
        ] == str(destination)
        assert (await local.get(path, headers=headers)).json()["directory"] == str(
            destination
        )
