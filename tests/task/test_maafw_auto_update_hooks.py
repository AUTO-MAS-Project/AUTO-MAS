"""MaaFW 项目自动更新接入运行流程（embedded_manager）的最小回归。

核心更新包 ``update_maafw_project_if_needed`` 与 interface 缓存都被 mock 掉，
只验证 manager 这一层：时机（Off / BeforeRun / AfterRun）、凭据合并、结果翻译、
失败不阻断、受管目录跳过、配置迁移。
"""

from __future__ import annotations

import asyncio
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from loguru import logger as loguru_logger

import app.core  # noqa: F401  # 初始化宿主配置
import app.task.MaaFW.tools.core.automas_maafw_interface as interface_pkg
import app.task.MaaFW.tools.core.automas_maafw_project_update as project_update_pkg
from app.core.task_manager import TaskInfo
from app.models.config import MaaFWConfig, MaaFWUserConfig
from app.models.ConfigBase import MultipleConfig
from app.models.schema import MaaFWConfig_Update
from app.models.task import ScriptItem
from app.task.MaaFW import embedded_manager
from app.task.MaaFW.embedded_manager import (
    MaaFWEmbeddedManager,
    describe_update_result,
)
from app.task.MaaFW.tools.embedded.update_credentials import (
    describe_cdk,
    resolve_auto_update_mode,
    resolve_update_credentials,
)

SCRIPT_CDK = "1111bf520b5a763d3e61f460"
GLOBAL_CDK = "2222bf520b5a763d3e61f460"


# ---------------------------------------------------------------------------
# 测试替身
# ---------------------------------------------------------------------------


class FakeGlobalConfig:
    def __init__(self, cdk: str = "", channel: str = "stable") -> None:
        self._values = {
            ("Update", "MirrorChyanCDK"): cdk,
            ("Update", "Channel"): channel,
        }

    def get(self, group: str, name: str) -> Any:
        return self._values[(group, name)]


class FakePublisher:
    def __init__(self) -> None:
        self.notices: list[tuple[str, str]] = []

    async def send(self, *, id: str, type: str, data: Any) -> bool:  # noqa: A002
        self.notices.append((data.level, data.message))
        return True


class Harness:
    """把 manager、事件流和各替身收在一起，测试里只看 ``events``。"""

    def __init__(self) -> None:
        self.events: list[str] = []
        self.update_calls: list[dict[str, Any]] = []
        self.interface_calls: list[dict[str, Any]] = []
        self.inner_tasks: list[Any] = []
        self.publisher = FakePublisher()
        self.manager: MaaFWEmbeddedManager | None = None
        self.update_result: Any = SimpleNamespace(
            updated=False,
            previous_version="v1.0.0",
            version_name="v1.0.0",
            source=None,
            cdk_status="absent",
            cdk_message="",
            cdk_expired_time=None,
            message="MaaFW project is up to date: v1.0.0",
            skipped_reason=None,
        )
        self.update_error: BaseException | None = None
        self.core_accepts_interface_model = True


def _make_inner_task_class(harness: Harness):
    class FakeInnerTask:
        def __init__(
            self,
            script_info,
            script_config,
            user_config,
            emulator_manager,
            project_update_logs=None,
        ) -> None:
            self.script_info = script_info
            self.project_update_logs = list(project_update_logs or [])
            self.cur_user_item = script_info.user_list[script_info.current_index]
            harness.inner_tasks.append(self)

        async def main_task(self) -> None:
            harness.events.append(f"user:{self.script_info.current_index}")
            self.cur_user_item.status = "完成"

        async def final_task(self) -> None:
            pass

        async def on_crash(self, exc: Exception) -> None:
            harness.events.append(f"crash:{exc}")

    return FakeInnerTask


async def _build_harness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    mode: str,
    script_cdk: str = "",
    channel: str = "",
    users: int = 2,
    global_config: FakeGlobalConfig | None = None,
    managed: bool = False,
) -> Harness:
    harness = Harness()

    project = tmp_path / "MaaEnd-win-x86_64-v1.0.0"
    project.mkdir()
    (project / "interface.json").write_text("{}", encoding="utf-8")
    if managed:
        (project / ".auto_mas_maafw_project.json").write_text("{}", encoding="utf-8")

    script_config = MaaFWConfig()
    await script_config.update(
        {
            "Info": {"Name": "测试 MFW", "Path": str(project)},
            "Update": {
                "AutoUpdateMode": mode,
                "MirrorChyanCDK": script_cdk,
                "Channel": channel,
            },
        }
    )
    for index in range(users):
        _, user_cfg = await script_config.UserData.add(MaaFWUserConfig)
        await user_cfg.update(
            {"Info": {"Name": f"user-{index}", "Status": True, "RemainedDay": -1}}
        )

    script_uid = uuid.uuid4()
    task_info = TaskInfo(
        mode="AutoProxy",
        task_id="task-id",
        queue_id=None,
        script_id=str(script_uid),
        user_id=None,
    )
    script_item = ScriptItem(script_id=str(script_uid), name="测试 MFW", status="运行")
    task_info.script_list = [script_item]

    manager = MaaFWEmbeddedManager(script_item)
    # 绕过 check()：它要真实模拟器、运行池与 Config.ScriptConfig，不是这里的被测边界。
    manager.script_config = script_config
    user_config: MultipleConfig[MaaFWUserConfig] = MultipleConfig([MaaFWUserConfig])
    await user_config.load(await script_config.UserData.toDict())
    manager.user_config = user_config
    manager.runnable_user_uids = list(user_config.data)

    async def fake_check() -> str:
        return "Pass"

    monkeypatch.setattr(manager, "check", fake_check)
    monkeypatch.setattr(
        manager,
        "_resolve_runtime_pool_route",
        lambda: SimpleNamespace(root=tmp_path, pool_id="pool"),
    )
    monkeypatch.setitem(
        sys.modules,
        "app.task.MaaFW.tools.embedded.runner_task",
        SimpleNamespace(MaaFWPluginAutoProxyTask=_make_inner_task_class(harness)),
    )
    monkeypatch.setattr(
        embedded_manager, "Config", global_config or FakeGlobalConfig()
    )
    monkeypatch.setattr(embedded_manager, "Publisher", harness.publisher)

    async def fake_push_notification(**kwargs):
        return None

    monkeypatch.setattr(embedded_manager, "push_notification", fake_push_notification)
    monkeypatch.setattr(
        embedded_manager, "finalize_task_game_sign_notification", lambda *a, **k: None
    )
    monkeypatch.setattr(
        embedded_manager, "append_task_game_sign_summary", lambda _t, result: result
    )

    async def fake_update_with_interface(
        project_path, interface_model=None, *, mirror_cdk, channel, send_log,
        project_lock_already_held,
    ):
        harness.events.append("update")
        harness.update_calls.append(
            {
                "project_path": Path(project_path),
                "interface_model": interface_model,
                "mirror_cdk": mirror_cdk,
                "channel": channel,
                "project_lock_already_held": project_lock_already_held,
                "inner_task_during_update": manager.inner_task,
            }
        )
        send_log("core: checking")
        if harness.update_error is not None:
            raise harness.update_error
        return harness.update_result

    async def fake_update_without_interface(
        project_path, *, mirror_cdk, channel, send_log, project_lock_already_held
    ):
        return await fake_update_with_interface(
            project_path,
            mirror_cdk=mirror_cdk,
            channel=channel,
            send_log=send_log,
            project_lock_already_held=project_lock_already_held,
        )

    def install_core() -> None:
        monkeypatch.setattr(
            project_update_pkg,
            "update_maafw_project_if_needed",
            fake_update_with_interface
            if harness.core_accepts_interface_model
            else fake_update_without_interface,
        )

    harness.install_core = install_core  # type: ignore[attr-defined]
    install_core()

    def fake_load_interface(base_dir, *, force_reload: bool = False):
        harness.interface_calls.append(
            {"base_dir": Path(base_dir), "force_reload": force_reload}
        )
        return SimpleNamespace(version="v1.0.0" if not force_reload else "v1.1.0")

    monkeypatch.setattr(interface_pkg, "load_interface_model_cached", fake_load_interface)

    harness.manager = manager
    return harness


def _run_script(harness: Harness) -> None:
    async def go() -> None:
        assert harness.manager is not None
        await harness.manager.main_task()
        await harness.manager.final_task()

    asyncio.run(go())


def _first_user_logs(harness: Harness) -> str:
    return "".join(harness.inner_tasks[0].project_update_logs)


# ---------------------------------------------------------------------------
# 时机
# ---------------------------------------------------------------------------


def test_off_never_calls_core(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def go() -> Harness:
        return await _build_harness(tmp_path, monkeypatch, mode="Off")

    harness = asyncio.run(go())
    _run_script(harness)

    assert harness.update_calls == []
    assert harness.events == ["user:0", "user:1"]
    assert harness.interface_calls == []


def test_before_run_calls_core_exactly_once_before_first_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def go() -> Harness:
        return await _build_harness(
            tmp_path,
            monkeypatch,
            mode="BeforeRun",
            script_cdk=SCRIPT_CDK,
            channel="beta",
            global_config=FakeGlobalConfig(cdk=GLOBAL_CDK, channel="stable"),
        )

    harness = asyncio.run(go())
    _run_script(harness)

    assert harness.events == ["update", "user:0", "user:1"]
    assert len(harness.update_calls) == 1
    call = harness.update_calls[0]
    assert call["mirror_cdk"] == SCRIPT_CDK
    assert call["channel"] == "beta"
    assert call["project_lock_already_held"] is False
    assert call["project_path"] == (tmp_path / "MaaEnd-win-x86_64-v1.0.0").resolve()
    # 更新在用户任务之外：调用时还没建任何 inner task，RunTimeLimit（套在
    # runner_task._run_maafw 上的 wait_for）自然不覆盖这段时间。
    assert call["inner_task_during_update"] is None
    # 更新日志并入第一位用户，且只并入第一位。
    assert "core: checking" in _first_user_logs(harness)
    assert harness.inner_tasks[1].project_update_logs == []
    # CDK 打码：只说有无与来自哪一级，一个字符都不露。
    assert "已配置（脚本级）" in _first_user_logs(harness)
    assert SCRIPT_CDK not in _first_user_logs(harness)
    assert SCRIPT_CDK[:4] not in _first_user_logs(harness)


def test_after_run_calls_core_exactly_once_after_all_users(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def go() -> Harness:
        return await _build_harness(tmp_path, monkeypatch, mode="AfterRun")

    harness = asyncio.run(go())
    _run_script(harness)

    assert harness.events == ["user:0", "user:1", "update"]
    assert len(harness.update_calls) == 1
    # 运行后更新时用户任务都已收尾，不会并入任何用户日志。
    assert all(task.project_update_logs == [] for task in harness.inner_tasks)


def test_after_run_skipped_when_main_task_did_not_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """取消/崩溃路径只走 final_task，不该在这时候去下载更新。"""

    async def go() -> Harness:
        harness = await _build_harness(tmp_path, monkeypatch, mode="AfterRun")
        assert harness.manager is not None
        harness.manager.check_result = "Pass"
        harness.manager._auto_update_mode = "AfterRun"
        await harness.manager.final_task()
        return harness

    harness = asyncio.run(go())
    assert harness.update_calls == []


# ---------------------------------------------------------------------------
# 凭据合并
# ---------------------------------------------------------------------------


def test_blank_script_cdk_falls_back_to_global(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def go() -> Harness:
        return await _build_harness(
            tmp_path,
            monkeypatch,
            mode="BeforeRun",
            script_cdk="",
            channel="",
            global_config=FakeGlobalConfig(cdk=GLOBAL_CDK, channel="beta"),
        )

    harness = asyncio.run(go())
    _run_script(harness)

    assert harness.update_calls[0]["mirror_cdk"] == GLOBAL_CDK
    assert harness.update_calls[0]["channel"] == "beta"
    assert "已配置（全局）" in _first_user_logs(harness)
    assert GLOBAL_CDK not in _first_user_logs(harness)
    assert GLOBAL_CDK[:4] not in _first_user_logs(harness)


def test_both_cdk_blank_passes_empty_and_logs_unconfigured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def go() -> Harness:
        return await _build_harness(
            tmp_path,
            monkeypatch,
            mode="BeforeRun",
            global_config=FakeGlobalConfig(cdk="", channel=""),
        )

    harness = asyncio.run(go())
    _run_script(harness)

    assert harness.update_calls[0]["mirror_cdk"] == ""
    assert harness.update_calls[0]["channel"] == "stable"
    assert "未配置" in _first_user_logs(harness)


def test_resolve_update_credentials_pure() -> None:
    script = FakeGlobalConfig(cdk=SCRIPT_CDK, channel="beta")
    global_cfg = FakeGlobalConfig(cdk=GLOBAL_CDK, channel="stable")

    merged = resolve_update_credentials(script, global_cfg)
    assert (merged.cdk, merged.channel, merged.cdk_origin) == (
        SCRIPT_CDK,
        "beta",
        "script",
    )

    merged = resolve_update_credentials(FakeGlobalConfig(), global_cfg)
    assert (merged.cdk, merged.channel, merged.cdk_origin) == (
        GLOBAL_CDK,
        "stable",
        "global",
    )

    merged = resolve_update_credentials(FakeGlobalConfig(), FakeGlobalConfig(channel=""))
    assert (merged.cdk, merged.channel, merged.cdk_origin) == ("", "stable", "none")
    assert describe_cdk(merged) == "未配置"

    # 配置对象缺项时按空处理，不抛
    merged = resolve_update_credentials(object(), object())
    assert merged.cdk == "" and merged.channel == "stable"


# ---------------------------------------------------------------------------
# 结果处理
# ---------------------------------------------------------------------------


def test_successful_update_invalidates_interface_cache_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def go() -> Harness:
        harness = await _build_harness(tmp_path, monkeypatch, mode="BeforeRun")
        harness.update_result = SimpleNamespace(
            updated=True,
            previous_version="v1.0.0",
            version_name="v1.1.0",
            source="mirrorchyan",
            cdk_status="ok",
            cdk_message="",
            cdk_expired_time=None,
            message="updated",
            skipped_reason=None,
        )
        return harness

    harness = asyncio.run(go())
    _run_script(harness)

    forced = [call for call in harness.interface_calls if call["force_reload"]]
    assert len(forced) == 1
    assert forced[0]["base_dir"] == (tmp_path / "MaaEnd-win-x86_64-v1.0.0").resolve()
    assert harness.events == ["update", "user:0", "user:1"]
    logs = _first_user_logs(harness)
    assert "已更新 v1.0.0 → v1.1.0（来源：Mirror 酱）" in logs
    assert "interface 缓存已刷新" in logs
    assert ("info", "MFW 项目已更新 v1.0.0 → v1.1.0（来源：Mirror 酱）") in (
        harness.publisher.notices
    )


def test_core_exception_does_not_block_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    warnings: list[str] = []
    sink_id = loguru_logger.add(
        lambda message: warnings.append(str(message)), level="WARNING"
    )
    try:

        async def go() -> Harness:
            harness = await _build_harness(tmp_path, monkeypatch, mode="BeforeRun")
            harness.update_error = RuntimeError("mirror down cdk=secret-value")
            return harness

        harness = asyncio.run(go())
        _run_script(harness)  # 不得抛出
    finally:
        loguru_logger.remove(sink_id)

    assert harness.events == ["update", "user:0", "user:1"]
    assert any("更新失败" in line and "任务继续" in line for line in warnings)
    assert harness.publisher.notices and harness.publisher.notices[0][0] == "error"
    # 异常文本里的 cdk=... 也要打码
    assert "secret-value" not in harness.publisher.notices[0][1]
    assert "secret-value" not in _first_user_logs(harness)
    assert harness.interface_calls == [] or not any(
        call["force_reload"] for call in harness.interface_calls
    )
    assert harness.manager is not None
    assert harness.manager.script_info.status == "完成"


def test_managed_project_skips_in_place_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def go() -> Harness:
        return await _build_harness(tmp_path, monkeypatch, mode="BeforeRun", managed=True)

    harness = asyncio.run(go())
    _run_script(harness)

    assert harness.update_calls == []
    assert harness.events == ["user:0", "user:1"]
    assert "受管项目由 Store 管理版本，跳过原地更新" in _first_user_logs(harness)


def test_cdk_expiring_within_seven_days_warns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expires_at = int(time.time()) + 3 * 86400

    async def go() -> Harness:
        harness = await _build_harness(tmp_path, monkeypatch, mode="BeforeRun")
        harness.update_result = SimpleNamespace(
            updated=False,
            previous_version="v1.0.0",
            version_name="v1.0.0",
            source=None,
            cdk_status="ok",
            cdk_message="",
            cdk_expired_time=expires_at,
            message="MaaFW project is up to date: v1.0.0",
            skipped_reason=None,
        )
        return harness

    harness = asyncio.run(go())
    _run_script(harness)

    assert "到期" in _first_user_logs(harness)
    assert any(
        level == "warning" and "CDK 将于" in message
        for level, message in harness.publisher.notices
    )


def test_describe_update_result_translations() -> None:
    now = 1_800_000_000.0

    # 过期 CDK：核心包原文优先
    lines = describe_update_result(
        {
            "updated": False,
            "cdk_status": "expired",
            "cdk_message": "Mirror 酱 CDK 已过期",
            "skipped_reason": None,
            "message": "MaaFW project is up to date: v1",
        },
        now=now,
    )
    assert ("warning", "Mirror 酱 CDK 已过期") in lines
    assert ("info", "MFW 项目更新：MaaFW project is up to date: v1") in lines

    # 没给原文时用兜底文案
    lines = describe_update_result(SimpleNamespace(cdk_status="quota"), now=now)
    assert lines == [("warning", "Mirror 酱 CDK 今日下载次数已用尽，本次改用 GitHub 下载")]

    # skipped_reason 原样记录
    lines = describe_update_result(SimpleNamespace(skipped_reason="锁被占用"), now=now)
    assert lines == [("info", "MFW 项目更新已跳过：锁被占用")]

    # 8 天后到期不提醒；已过期按已到期提示
    assert describe_update_result(
        SimpleNamespace(cdk_expired_time=now + 8 * 86400), now=now
    ) == []
    lines = describe_update_result(
        SimpleNamespace(cdk_expired_time=now - 86400), now=now
    )
    assert lines and lines[0][0] == "warning" and "已于" in lines[0][1]

    # 旧字段名兜底（A 还没补新字段前）
    lines = describe_update_result(
        SimpleNamespace(
            updated=True, current_version="v1", latest_version="v2", source="github"
        ),
        now=now,
    )
    assert lines == [("info", "MFW 项目已更新 v1 → v2（来源：GitHub）")]

    # 完全空对象不炸
    assert describe_update_result(object(), now=now) == []


def test_core_signature_without_interface_model_still_works(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def go() -> Harness:
        harness = await _build_harness(tmp_path, monkeypatch, mode="BeforeRun")
        harness.core_accepts_interface_model = False
        harness.install_core()  # type: ignore[attr-defined]
        return harness

    harness = asyncio.run(go())
    _run_script(harness)

    assert len(harness.update_calls) == 1
    assert harness.update_calls[0]["interface_model"] is None
    # 没更新就不刷新缓存
    assert not any(call["force_reload"] for call in harness.interface_calls)


# ---------------------------------------------------------------------------
# 配置迁移与 schema
# ---------------------------------------------------------------------------


def test_legacy_if_auto_update_false_migrates_to_off() -> None:
    async def go() -> tuple[str, str, str, str]:
        legacy_off = MaaFWConfig()
        await legacy_off.load({"Update": {"IfAutoUpdate": False}})

        legacy_on = MaaFWConfig()
        await legacy_on.load({"Update": {"IfAutoUpdate": True}})

        explicit = MaaFWConfig()
        await explicit.load(
            {"Update": {"IfAutoUpdate": False, "AutoUpdateMode": "AfterRun"}}
        )

        fresh = MaaFWConfig()
        await fresh.load({})
        return (
            legacy_off.get("Update", "AutoUpdateMode"),
            legacy_on.get("Update", "AutoUpdateMode"),
            explicit.get("Update", "AutoUpdateMode"),
            fresh.get("Update", "AutoUpdateMode"),
        )

    assert asyncio.run(go()) == ("Off", "BeforeRun", "AfterRun", "BeforeRun")


def test_resolve_auto_update_mode_defaults_on_garbage() -> None:
    assert resolve_auto_update_mode(FakeGlobalConfig()) == "BeforeRun"

    class Weird:
        def get(self, group: str, name: str) -> Any:
            return "Sometimes"

    assert resolve_auto_update_mode(Weird()) == "BeforeRun"


def test_update_schema_accepts_auto_update_mode() -> None:
    assert MaaFWConfig_Update(AutoUpdateMode="AfterRun").AutoUpdateMode == "AfterRun"
    assert MaaFWConfig_Update().AutoUpdateMode is None
    with pytest.raises(Exception):
        MaaFWConfig_Update(AutoUpdateMode="Always")


def test_update_channel_accepts_alpha_end_to_end() -> None:
    """脚本级更新通道必须接受 alpha，且 Pydantic 与 ConfigItem 两侧一致。

    编辑页给了「内测版」这一档，而后端 schema 与 ``OptionsValidator`` 原先只认
    ``""/stable/beta``——用户一选就 422，绕过校验也会被静默纠回空串。
    alpha 是 Mirror 酱实测支持的档位（``channel=alpha`` 返回预发布版本）。

    注意全局 ``Update.Channel`` 是 **MAS 自身**的发布通道（只有 stable/beta），
    故意不跟着加 alpha；两者语义不同。
    """

    for channel in ("", "stable", "beta", "alpha"):
        assert MaaFWConfig_Update(Channel=channel).Channel == channel
    with pytest.raises(Exception):
        MaaFWConfig_Update(Channel="nightly")

    script = MaaFWConfig()
    asyncio.run(script.update({"Update": {"Channel": "alpha"}}))
    assert script.get("Update", "Channel") == "alpha"
    asyncio.run(script.update({"Update": {"Channel": "nightly"}}))
    assert script.get("Update", "Channel") != "nightly"


def test_describe_cdk_never_leaks_any_character() -> None:
    """日志里的 CDK 描述一个字符都不能露，只说有无与来自哪一级。

    Mirror 酱 CDK 前缀高度重复（实测样例全是 0001bf52 开头），露前几位帮不上
    排查，还与核心包「只记有无」的口径不一致。
    """

    from app.task.MaaFW.tools.embedded.update_credentials import (
        MaaFWUpdateCredentials,
        describe_cdk,
    )

    secret = "0001bf520b5a763d3e61f460"
    described = describe_cdk(
        MaaFWUpdateCredentials(cdk=secret, channel="alpha", cdk_origin="script")
    )
    assert "脚本级" in described
    for length in (4, 6, 8):
        assert secret[:length] not in described
    assert describe_cdk(
        MaaFWUpdateCredentials(cdk="", channel="stable", cdk_origin="none")
    ) == "未配置"
