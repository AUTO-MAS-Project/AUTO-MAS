"""MaaFW 任务失败截图：worker 侧落盘回传，宿主侧挑选并塞进统计通知。"""

import asyncio
import base64
import io
from pathlib import Path
from typing import Any

import pytest

from app.task import notify_core
from app.task.MaaFW.tools.core.automas_maafw_runner import runner as runner_module
from app.task.MaaFW.tools.core.automas_maafw_runner.models import (
    MaaFWDeviceConfig,
    MaaFWResourceBundlePlan,
    MaaFWRunPlan,
    MaaFWTaskRunPlan,
)
from app.task.MaaFW.tools.core.automas_maafw_runner.runner import MaaFWRunner
from app.task.MaaFW.tools.embedded.runner_task import MaaFWPluginAutoProxyTask
from app.task.MaaFW.tools.notify import report as report_module
from app.task.MaaFW.tools.notify.report import (
    NOTIFY_SCREENSHOT_LIMIT,
    load_screenshot_images,
    screenshot_entries,
)

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

    images = load_screenshot_images(
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


class _UserItem:
    name = "小明"


def _host_task(run_complete: bool, reports: list[dict[str, Any]]) -> Any:
    task = MaaFWPluginAutoProxyTask.__new__(MaaFWPluginAutoProxyTask)
    task.run_complete = run_complete
    task._attempt_reports = reports
    task.cur_user_item = _UserItem()
    return task


def test_collect_failure_screenshots_labels_attempts_in_order() -> None:
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
    task = _host_task(False, reports)
    shots = task._collect_failure_screenshots()
    assert [label for label, _ in shots] == [
        "第 1 次尝试 · 登录",
        "第 1 次尝试 · 日常",
        "第 2 次尝试 · 登录",
        "第 3 次尝试 · 登录",
        "第 3 次尝试 · 日常",
    ]
    # 上限由消费方裁：统计通知与脚本级报告都取最后 NOTIFY_SCREENSHOT_LIMIT 张。
    assert NOTIFY_SCREENSHOT_LIMIT == 4
    assert [p.name for _, p in shots[-NOTIFY_SCREENSHOT_LIMIT:]] == [
        "2.png",
        "3.png",
        "4.png",
        "5.png",
    ]
    # 脚本级报告是多用户合并的，标签要带用户名。
    assert task.report_screenshots()[0][0] == "小明 · 第 1 次尝试 · 登录"


def test_collect_failure_screenshots_empty_when_run_completed() -> None:
    reports = [{"attempt": 1, "screenshots": [("登录", Path("1.png"))]}]
    task = _host_task(True, reports)
    assert task._collect_failure_screenshots() == []
    assert task.report_screenshots() == []


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


def test_proxy_result_payload_carries_images(monkeypatch: pytest.MonkeyPatch) -> None:
    """脚本级「代理结果」（仅失败时真正会发的那封）同样内嵌截图。"""

    captured: dict[str, Any] = {}

    async def fake_dispatch_task_report(
        payload: Any, targets: Any, task_info: Any, **kw: Any
    ) -> Any:
        captured["payload"] = payload
        return notify_core.DispatchResult()

    monkeypatch.setattr(notify_core, "dispatch_task_report", fake_dispatch_task_report)
    monkeypatch.setattr(notify_core, "should_send_result", lambda *a, **k: True)
    monkeypatch.setattr(notify_core, "global_target", lambda **k: None)
    images = [report_module.MailInlineImage("maafw-failure-1", b"one", "jpeg")]
    message = {
        "title": "自动代理任务报告",
        "script_name": "MFW",
        "start_time": "s",
        "end_time": "e",
        "completed_count": 0,
        "uncompleted_count": 1,
        "result": "小明: 登录失败",
        "screenshots": screenshot_entries([("小明 · 第 1 次尝试 · 登录", images[0])]),
    }
    asyncio.run(
        report_module.push_notification(
            mode="代理结果", title="T", message=message, images=images
        )
    )
    payload = captured["payload"]
    assert payload.mail_images == tuple(images)
    assert payload.webhook_image_base64 == base64.b64encode(b"one").decode("ascii")
    assert 'src="cid:maafw-failure-1"' in payload.html
    assert "小明 · 第 1 次尝试 · 登录" in payload.html


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


def test_manager_accumulates_screenshots_across_users() -> None:
    """管理器在每位用户收尾时攒下截图，最后一起随「代理结果」发出。"""

    from app.task.MaaFW.embedded_manager import MaaFWEmbeddedManager

    class _Inner:
        def __init__(self, shots: list[tuple[str, Path]]) -> None:
            self.shots = shots
            self.finalized = False

        async def final_task(self) -> None:
            self.finalized = True

        def report_screenshots(self) -> list[tuple[str, Path]]:
            return self.shots

    manager = MaaFWEmbeddedManager.__new__(MaaFWEmbeddedManager)
    manager._failure_screenshots = []
    for shots in (
        [("小明 · 第 1 次尝试 · 登录", Path("a.png"))],
        [],
        [("小红 · 第 2 次尝试 · 日常", Path("b.png"))],
    ):
        manager.inner_task = _Inner(shots)  # type: ignore[assignment]
        manager._inner_finalized = False
        asyncio.run(manager._finalize_inner_task())
        assert manager.inner_task.finalized

    assert [label for label, _ in manager._failure_screenshots] == [
        "小明 · 第 1 次尝试 · 登录",
        "小红 · 第 2 次尝试 · 日常",
    ]
