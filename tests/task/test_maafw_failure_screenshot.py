"""MaaFW 任务失败截图：worker 侧落盘回传，宿主侧挑选并塞进统计通知。"""

import asyncio
import base64
import io
from pathlib import Path
from typing import Any

import pytest

from app.task.MaaFW.tools.core.automas_maafw_runner import runner as runner_module
from app.task.MaaFW.tools.core.automas_maafw_runner.models import (
    MaaFWDeviceConfig,
    MaaFWResourceBundlePlan,
    MaaFWRunPlan,
    MaaFWTaskRunPlan,
)
from app.task.MaaFW.tools.core.automas_maafw_runner.runner import MaaFWRunner
from app.task.MaaFW.tools.embedded import runner_task as runner_task_module
from app.task.MaaFW.tools.embedded.runner_task import (
    MaaFWPluginAutoProxyTask,
    _load_notify_screenshots,
)
from app.task.MaaFW.tools.notify import report as report_module

# ---------------------------------------------------------------- worker 侧


class _Job:
    job_id = 1

    def __init__(self, failed: bool) -> None:
        self.failed = failed

    def wait(self) -> "_Job":
        return self


class _Tasker:
    stopping = False

    def __init__(self, failures: set[str]) -> None:
        self.failures = failures
        self.posted: list[str] = []

    def post_task(self, entry: str, override: Any = None) -> _Job:
        self.posted.append(entry)
        return _Job(failed=entry in self.failures)


def _plan(*names: str) -> MaaFWRunPlan:
    return MaaFWRunPlan(
        path="C:/proj",
        projectName="proj",
        controllerName="adb",
        controllerType="Adb",
        resourceName="res",
        resource=MaaFWResourceBundlePlan(name="res"),
        tasks=[MaaFWTaskRunPlan(name=n, entry=n) for n in names],
    )


def _runner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    failures: set[str],
    encode: Any = None,
) -> tuple[MaaFWRunner, list[str]]:
    logs: list[str] = []
    runner = MaaFWRunner(
        _plan("登录 Login", "日常"),
        send_log=logs.append,
        failure_screenshot_dir=tmp_path / "shots",
        failure_screenshot_prefix="10-00-00",
    )
    tasker = _Tasker(failures)

    def fake_init(self: MaaFWRunner, _device: MaaFWDeviceConfig) -> None:
        self.tasker = tasker  # type: ignore[assignment]
        self.controller = object()

    monkeypatch.setattr(MaaFWRunner, "_ensure_initialized", fake_init)
    monkeypatch.setattr(
        runner_module,
        "_encode_current_screen_png",
        encode or (lambda _controller: b"\x89PNG-fake"),
    )
    monkeypatch.setattr(runner_module.time, "sleep", lambda _s: None)
    return runner, logs


def test_failed_task_screenshot_is_saved_and_reported(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runner, logs = _runner(monkeypatch, tmp_path, failures={"登录 Login"})
    result = runner.run(MaaFWDeviceConfig(type="Adb"))

    assert result.success is False
    assert result.completedTasks == ["日常"]
    assert [shot.task for shot in result.failureScreenshots] == ["登录 Login"]
    path = Path(result.failureScreenshots[0].path)
    assert path.parent == tmp_path / "shots"
    assert path.name.startswith("10-00-00.failed-")
    assert path.name.endswith("-登录_Login.png")
    assert path.read_bytes() == b"\x89PNG-fake"
    assert any("任务失败截图已保存" in line for line in logs)


def test_screenshot_failure_does_not_change_task_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def boom(_controller: Any) -> bytes:
        raise RuntimeError("controller 截图失败")

    runner, logs = _runner(monkeypatch, tmp_path, failures={"日常"}, encode=boom)
    result = runner.run(MaaFWDeviceConfig(type="Adb"))

    assert result.success is False
    assert result.failedTask == "日常"
    assert result.failureScreenshots == []
    assert any("任务失败截图未能保存" in line for line in logs)


def test_no_screenshot_when_all_tasks_succeed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runner, _ = _runner(monkeypatch, tmp_path, failures=set())
    result = runner.run(MaaFWDeviceConfig(type="Adb"))
    assert result.success is True
    assert result.failureScreenshots == []
    assert not (tmp_path / "shots").exists()


def test_no_screenshot_without_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runner, _ = _runner(monkeypatch, tmp_path, failures={"日常"})
    runner._failure_screenshot_dir = None
    result = runner.run(MaaFWDeviceConfig(type="Adb"))
    assert result.success is False
    assert result.failureScreenshots == []


# ---------------------------------------------------------------- 宿主侧


def _png_bytes() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (32, 16), (200, 30, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_load_notify_screenshots_converts_to_jpeg_and_skips_missing(
    tmp_path: Path,
) -> None:
    good = tmp_path / "a.png"
    good.write_bytes(_png_bytes())
    junk = tmp_path / "b.png"
    junk.write_bytes(b"not an image")

    images = _load_notify_screenshots(
        [("第 1 次尝试 · 登录", good), ("缺失", tmp_path / "x.png"), ("坏图", junk)]
    )

    assert [label for label, _ in images] == ["第 1 次尝试 · 登录", "坏图"]
    first = images[0][1]
    assert first.subtype == "jpeg"
    assert first.data.startswith(b"\xff\xd8")
    assert first.cid == "maafw-failure-1"
    # 读不出来的原样带上，别因为一张图丢掉整份通知。
    assert images[1][1].subtype == "png"
    assert images[1][1].data == b"not an image"


def _host_task(run_complete: bool, reports: list[dict[str, Any]]) -> Any:
    task = MaaFWPluginAutoProxyTask.__new__(MaaFWPluginAutoProxyTask)
    task.run_complete = run_complete
    task._attempt_reports = reports
    return task


def test_collect_failure_screenshots_labels_attempts_and_caps() -> None:
    reports = [
        {
            "attempt": 1,
            "screenshots": [("登录", Path("1.png")), ("日常", Path("2.png"))],
        },
        {"attempt": 2, "screenshots": [("登录", Path("3.png"))]},
        {
            "attempt": 3,
            "screenshots": [("登录", Path("4.png")), ("日常", Path("5.png"))],
        },
    ]
    shots = _host_task(False, reports)._collect_failure_screenshots()
    assert [label for label, _ in shots] == [
        "第 1 次尝试 · 日常",
        "第 2 次尝试 · 登录",
        "第 3 次尝试 · 登录",
        "第 3 次尝试 · 日常",
    ]
    assert [path.name for _, path in shots] == ["2.png", "3.png", "4.png", "5.png"]


def test_collect_failure_screenshots_empty_when_run_completed() -> None:
    reports = [{"attempt": 1, "screenshots": [("登录", Path("1.png"))]}]
    assert _host_task(True, reports)._collect_failure_screenshots() == []


def test_statistics_payload_carries_mail_images_and_webhook_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_dispatch(payload: Any, targets: Any) -> Any:
        captured["payload"] = payload
        return report_module.DispatchResult()

    monkeypatch.setattr(report_module, "dispatch", fake_dispatch)
    monkeypatch.setattr(report_module, "statistic_targets", lambda _user: [])
    images = [
        report_module.MailInlineImage("maafw-failure-1", b"one", "jpeg"),
        report_module.MailInlineImage("maafw-failure-2", b"two", "jpeg"),
    ]
    message = {
        "start_time": "s",
        "end_time": "e",
        "user_info": "u",
        "user_result": "代理任务失败",
        "task_details": "未完成: 登录",
        "screenshots": [
            {"cid": "maafw-failure-1", "label": "第 1 次尝试 · 登录"},
            {"cid": "maafw-failure-2", "label": "第 2 次尝试 · 登录"},
        ],
    }
    asyncio.run(
        report_module.push_notification(
            mode="统计信息", title="T", message=message, images=images
        )
    )

    payload = captured["payload"]
    assert payload.mail_images == tuple(images)
    assert payload.webhook_image_base64 == base64.b64encode(b"two").decode("ascii")
    assert 'src="cid:maafw-failure-1"' in payload.html
    assert 'src="cid:maafw-failure-2"' in payload.html
    assert "第 2 次尝试 · 登录" in payload.html


def test_statistics_payload_without_images_has_no_screenshot_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_dispatch(payload: Any, targets: Any) -> Any:
        captured["payload"] = payload
        return report_module.DispatchResult()

    monkeypatch.setattr(report_module, "dispatch", fake_dispatch)
    monkeypatch.setattr(report_module, "statistic_targets", lambda _user: [])
    message = {
        "start_time": "s",
        "end_time": "e",
        "user_info": "u",
        "user_result": "代理任务全部完成",
        "task_details": "",
        "screenshots": [],
    }
    asyncio.run(
        report_module.push_notification(mode="统计信息", title="T", message=message)
    )
    payload = captured["payload"]
    assert payload.mail_images == ()
    assert payload.webhook_image_base64 is None
    assert "失败截图" not in payload.html
    assert runner_task_module._NOTIFY_SCREENSHOT_LIMIT == 4


def test_host_side_result_model_keeps_screenshots() -> None:
    """宿主用 models.MaaFWRunResult 校验 worker 回传的 JSON；两边必须是同一个类，
    否则 pydantic 会把多出来的字段静默丢掉，截图永远到不了通知。"""

    from app.task.MaaFW.tools.core.automas_maafw_runner import models

    assert runner_module.MaaFWRunResult is models.MaaFWRunResult
    payload = {
        "success": False,
        "projectName": "p",
        "controllerName": "c",
        "resourceName": "r",
        "completedTasks": [],
        "failedTask": "登录",
        "errorMessage": "x",
        "failureScreenshots": [{"task": "登录", "path": "C:/h/1.png"}],
    }
    result = models.MaaFWRunResult.model_validate(payload)
    assert [(s.task, s.path) for s in result.failureScreenshots] == [
        ("登录", "C:/h/1.png")
    ]
