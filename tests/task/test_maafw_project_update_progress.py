"""MFW 手动更新过程推给编辑页的进度事件。

两层各测各的：

- ``apply_package_transaction`` 在逐文件覆盖的循环里补发 ``applying`` 进度，
  首个（0/n）与最后一个（n/n）必发，既有的 staged → applying →
  post_validating → committed 顺序不变。
- ``MaaFWUpdateProgressTracker`` 把 updater / transport / apply 三种形状的裸事件
  翻成 ``WSMaaFWProjectUpdateProgressData``：速度按已发出采样点的时间差算、
  下载与覆盖按时间节流但收尾必发、``delta`` 对外叫 ``incremental``、
  文案全部过打码。
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from app.task.MaaFW.tools.core.automas_maafw_project_update.apply import (
    APPLY_PROGRESS_MAX_STEP_FILES,
    _apply_progress_step,
    apply_package_transaction,
)
from app.task.MaaFW.tools.embedded.update_progress import (
    MaaFWUpdateProgressTracker,
    normalize_package_kind,
)


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


# ---------------------------------------------------------------- tracker


def test_download_events_are_throttled_but_final_sample_always_emits() -> None:
    clock = _Clock()
    tracker = MaaFWUpdateProgressTracker(clock=clock, throttle_seconds=0.5)

    first = tracker.event(
        {"stage": "downloading", "downloaded_bytes": 0, "total_bytes": 1000}
    )
    assert first is not None
    assert first.stage == "downloading"
    assert first.percent == 0
    assert first.speedBytesPerSec is None, "首个采样点没有时间差，速度未知"

    clock.advance(0.1)
    assert (
        tracker.event(
            {"stage": "downloading", "downloaded_bytes": 100, "total_bytes": 1000}
        )
        is None
    ), "0.5s 内的采样被节流"

    clock.advance(0.9)  # 距首个已发出采样 1.0s
    second = tracker.event(
        {"stage": "downloading", "downloaded_bytes": 500, "total_bytes": 1000}
    )
    assert second is not None
    assert second.percent == 50
    assert second.downloadedBytes == 500
    assert second.totalBytes == 1000
    # 速度按「已发出」采样点算：(500-0)/1.0s，被吞掉的 100B 采样不参与
    assert second.speedBytesPerSec == 500

    clock.advance(0.1)
    final = tracker.event(
        {"stage": "downloading", "downloaded_bytes": 1000, "total_bytes": 1000}
    )
    assert final is not None, "下载完成的那一条不受节流"
    assert final.percent == 100


def test_cache_hit_downloaded_event_reports_full_percent() -> None:
    tracker = MaaFWUpdateProgressTracker(clock=_Clock())
    data = tracker.event(
        {"stage": "downloaded", "downloaded_bytes": 42, "total_bytes": 42}
    )
    assert data is not None
    assert data.stage == "downloaded"
    assert data.percent == 100
    assert data.status == "running"


def test_download_without_total_has_no_percent() -> None:
    tracker = MaaFWUpdateProgressTracker(clock=_Clock())
    data = tracker.event(
        {"stage": "downloading", "downloaded_bytes": 10, "total_bytes": None}
    )
    assert data is not None
    assert data.percent is None
    assert data.totalBytes is None


def test_package_kind_comes_from_version_discovered_and_plan_validated() -> None:
    tracker = MaaFWUpdateProgressTracker(clock=_Clock())
    discovered = tracker.event(
        {
            "stage": "checking",
            "status": "version_discovered",
            "version": "v1.2.3",
            "package_type": "delta",
        }
    )
    assert discovered is not None
    assert discovered.packageKind == "incremental"
    assert "v1.2.3" in discovered.message

    # 之后的下载事件继承包类型
    download = tracker.event(
        {"stage": "downloading", "downloaded_bytes": 0, "total_bytes": 10}
    )
    assert download is not None
    assert download.packageKind == "incremental"

    # apply 的 plan_validated 用 camelCase 再报一次，full 覆盖前值
    plan = tracker.event({"stage": "plan_validated", "packageType": "full"})
    assert plan is not None
    assert plan.packageKind == "full"


def test_normalize_package_kind() -> None:
    assert normalize_package_kind("full") == "full"
    assert normalize_package_kind("delta") == "incremental"
    assert normalize_package_kind("incremental") == "incremental"
    assert normalize_package_kind("") is None
    assert normalize_package_kind(None) is None
    assert normalize_package_kind("zip") is None


def test_applying_events_first_and_last_always_emit() -> None:
    clock = _Clock()
    tracker = MaaFWUpdateProgressTracker(clock=clock, throttle_seconds=0.5)

    start = tracker.event({"stage": "applying", "appliedFiles": 0, "totalFiles": 4})
    assert start is not None
    assert start.appliedFiles == 0
    assert start.totalFiles == 4
    assert start.percent == 0

    clock.advance(0.1)
    assert (
        tracker.event({"stage": "applying", "appliedFiles": 2, "totalFiles": 4}) is None
    )

    clock.advance(0.1)
    last = tracker.event({"stage": "applying", "appliedFiles": 4, "totalFiles": 4})
    assert last is not None
    assert last.percent == 100
    assert "4/4" in last.message


def test_final_events_map_to_success_and_failed() -> None:
    tracker = MaaFWUpdateProgressTracker(clock=_Clock())
    done = tracker.event(
        {
            "stage": "completed",
            "status": "updated",
            "message": "更新完成",
            "final": True,
        }
    )
    assert done is not None
    assert (done.stage, done.status, done.message) == (
        "completed",
        "success",
        "更新完成",
    )

    failed = tracker.event(
        {"stage": "failed", "status": "apply_failed", "message": "炸了", "final": True}
    )
    assert failed is not None
    assert (failed.stage, failed.status, failed.message) == ("failed", "failed", "炸了")

    manual = tracker.finished(success=False, message="MFW 更新检查失败: x")
    assert manual.stage == "failed"
    assert manual.status == "failed"


def test_log_and_message_never_leak_cdk() -> None:
    tracker = MaaFWUpdateProgressTracker(clock=_Clock())
    secret = "cdk=ABCDEF1234567890"
    log = tracker.log(f"请求下载地址 {secret}")
    assert log.stage == "log"
    assert log.log is not None
    assert "ABCDEF1234567890" not in log.log
    assert "ABCDEF1234567890" not in log.message

    failed = tracker.event({"stage": "failed", "message": f"下载失败 {secret}"})
    assert failed is not None
    assert "ABCDEF1234567890" not in failed.message


def test_apply_progress_step_is_two_percent_capped_at_fifty_files() -> None:
    assert _apply_progress_step(0) == 1
    assert _apply_progress_step(30) == 1
    assert _apply_progress_step(1000) == 20
    assert _apply_progress_step(100_000) == APPLY_PROGRESS_MAX_STEP_FILES


# ---------------------------------------------------------------- apply.py


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_package(tmp_path: Path, files: dict[str, str]) -> Path:
    package_path = tmp_path / "pkg.zip"
    with zipfile.ZipFile(package_path, "w") as archive:
        for relative, content in files.items():
            archive.writestr(relative, content)
    return package_path


def test_apply_reports_per_file_progress_without_reordering_stages(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _write(
        project / "interface.json",
        json.dumps({"name": "Demo", "version": "v1.0.0"}),
    )
    payload = {
        "interface.json": json.dumps({"name": "Demo", "version": "v1.1.0"}),
        **{f"resource/pipeline/{index}.json": "{}" for index in range(120)},
    }
    package = _make_package(tmp_path, payload)

    events: list[tuple[str, dict[str, Any]]] = []
    apply_package_transaction(
        project,
        package,
        operation_root=tmp_path / "operations",
        progress=lambda stage, data: events.append((stage, dict(data))),
    )

    stages = [stage for stage, _ in events]
    # 既有阶段顺序不变：applying 只是从一条变成多条
    collapsed = [s for i, s in enumerate(stages) if i == 0 or stages[i - 1] != s]
    assert collapsed == [
        "plan_validated",
        "staged",
        "applying",
        "post_validating",
        "committed",
    ]

    applying = [data for stage, data in events if stage == "applying"]
    total = len(payload)
    assert applying[0] == {
        "planId": applying[0]["planId"],
        "appliedFiles": 0,
        "totalFiles": total,
    }
    assert applying[-1]["appliedFiles"] == total
    assert applying[-1]["totalFiles"] == total
    counts = [data["appliedFiles"] for data in applying]
    assert counts == sorted(counts), "进度单调递增"
    # 121 个文件步长 2：中间有节流，不是每个文件都报
    assert 3 < len(applying) < total
