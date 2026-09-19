"""MFW 项目更新包缓存的回收口径：留给同项目其它副本命中的包，几天没人碰就删。"""

import json
import os
import threading
import time
from pathlib import Path

from app.task.MaaFW.tools.core.automas_maafw_project_update.state import artifact_lock
from app.task.MaaFW.tools.core.automas_maafw_project_update.transport import (
    CACHE_RETENTION_SECONDS,
    prune_update_cache,
)

OLD = time.time() - CACHE_RETENTION_SECONDS - 3600


def _artifact(root: Path, artifact_id: str, *, age: float | None = OLD) -> Path:
    directory = root / artifact_id
    directory.mkdir(parents=True)
    (directory / "payload.zip").write_bytes(b"z" * 4096)
    marker = directory / "artifact.json"
    marker.write_text(json.dumps({"artifactId": artifact_id}), encoding="utf-8")
    if age is not None:
        os.utime(marker, (age, age))
    return directory


class TestPruneUpdateCache:
    def test_stale_artifacts_go_and_fresh_ones_stay(self, tmp_path: Path) -> None:
        stale = _artifact(tmp_path, "a" * 24)
        fresh = _artifact(tmp_path, "b" * 24, age=None)
        (tmp_path / "not-an-artifact").mkdir()

        report = prune_update_cache(tmp_path)

        assert report.removed_artifacts == 1
        assert report.removed_bytes == 4096 + len(json.dumps({"artifactId": "a" * 24}))
        assert not (stale / "payload.zip").exists()
        assert (fresh / "payload.zip").is_file()
        assert (tmp_path / "not-an-artifact").is_dir()

    def test_busy_artifact_is_skipped(self, tmp_path: Path) -> None:
        """下载在事件循环线程里持锁，回收在工作线程里跑：锁对同线程可重入，所以要跨线程。"""

        busy = _artifact(tmp_path, "c" * 24)
        acquired = threading.Event()
        release = threading.Event()

        def hold() -> None:
            with artifact_lock(tmp_path, "c" * 24):
                acquired.set()
                release.wait(5)

        holder = threading.Thread(target=hold)
        holder.start()
        try:
            assert acquired.wait(5)
            report = prune_update_cache(tmp_path)
        finally:
            release.set()
            holder.join(5)

        assert report.removed_artifacts == 0
        assert report.skipped_busy == 1
        assert (busy / "payload.zip").is_file()

    def test_missing_root_is_a_no_op(self, tmp_path: Path) -> None:
        report = prune_update_cache(tmp_path / "nowhere")
        assert (report.removed_artifacts, report.skipped_busy) == (0, 0)
