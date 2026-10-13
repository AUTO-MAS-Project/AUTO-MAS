"""MuMu 启动流程：未启动才做的前置 / 一次性副任务 / 刷新交给门控循环。

同样在 ``MuMuControl._run`` 打桩 —— 到达它的参数即真实会下发的 CLI 内容。
状态由桩自己推进（``is_process_started`` / ``is_android_started``），
故断言的是「操作函数靠轮询 devices 上的状态收敛」这条真实路径，不是假状态。
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from app.config import ConfigCollection
from app.models.config.game import TRIGGER_TICKET
from app.utils.platform.common.process_runner import ProcessResult

_PLUGINS = Path(__file__).resolve().parents[3] / "plugins"
for _p in (
    str(_PLUGINS / "auto_mas_core" / "src"),
    str(_PLUGINS / "mumu_adapter" / "src"),
):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from mumu_adapter.config import MuMuDevice, MuMuGame  # noqa: E402
from mumu_adapter.control import MuMuControl  # noqa: E402

# ``info.path`` 过 locate_mumu，文件不存在就被纠成 None，而 ``_sync_devices``
# 在 path 为 None 时整个跳过 —— 本文件断言的正是同步节奏，故须给一个真文件。
_FAKE_EXE = Path(tempfile.mkdtemp(prefix="mumu_open_flow_")) / "MuMuManager.exe"
_FAKE_EXE.touch()


class _FakeRun:
    """替掉 ``_run``：记录调用，并让 ``launch`` 后的第 N 笔 info 变成在线。

    ``online_after`` 是「launch 之后还要几笔 info 才报在线」——
    用来模拟启动有耗时，逼 ``_open`` 真的走轮询等待，而不是一读就成。
    ``online_after=None`` 表示永不在线（超时路径）。
    """

    def __init__(
        self,
        *,
        indexes: tuple[str, ...] = ("0",),
        online_from_start: bool = False,
        online_after: int | None = 2,
    ) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.info_calls = 0
        self._indexes = indexes
        self._online = online_from_start
        self._online_after = online_after
        self._info_since_launch: int | None = None

    def named(self, *head: str) -> list[tuple[str, ...]]:
        """取以 ``head`` 开头的调用（如 ``named("control")``）。"""
        return [c for c in self.calls if c[: len(head)] == head]

    async def __call__(self, *args: str | int, timeout: float | None = None) -> Any:
        call = tuple(str(a) for a in args)
        self.calls.append(call)

        if call[0] == "info":
            self.info_calls += 1
            if self._info_since_launch is not None:
                self._info_since_launch += 1
                if (
                    self._online_after is not None
                    and self._info_since_launch >= self._online_after
                ):
                    self._online = True
            rows = {
                i: {
                    "index": i,
                    "name": f"MuMu-{i}",
                    "is_process_started": self._online,
                    "is_android_started": self._online,
                }
                for i in self._indexes
            }
            return ProcessResult(stdout=json.dumps(rows), stderr="", returncode=0)

        if call[:1] == ("control",) and call[-1] == "launch":
            self._info_since_launch = 0
            return ProcessResult(stdout="", stderr="", returncode=0)

        if call[0] == "adb" and "dumpsys" in call:
            # ``_ensure_app`` 的前台判定：直接报已在前台，省掉补启动分支
            return ProcessResult(
                stdout="topResumedActivity=com.x/.Main", stderr="", returncode=0
            )

        return ProcessResult(stdout="", stderr="", returncode=0)


async def _make(fake: _FakeRun) -> tuple[MuMuGame, MuMuControl]:
    games: ConfigCollection[MuMuGame] = ConfigCollection(
        [MuMuGame], name=f"games_{uuid4().hex}"
    )
    await games.activate()
    uid = games.add(MuMuGame)
    await games.commit()
    entry = games[uid]
    entry.info.path = _FAKE_EXE
    # 启动等待与「起来后缓一口气」都按它算；测试里压到最小
    entry.info.max_wait_time = 5
    await entry.commit()
    assert entry.info.path is not None, "path 被纠成 None 则 sync 全程跳过"

    ctrl = MuMuControl(config=entry)
    entry._game_control = ctrl
    ctrl._run = fake  # type: ignore[method-assign]
    entry.devices.add(MuMuDevice, payload={"info": {"index": "0"}})
    await entry.devices.commit()
    return entry, ctrl


def _dev_uid(entry: MuMuGame) -> Any:
    return next(iter(entry.devices.keys()))


# ── 1. 已在线：不重复拉起，但收尾动作照做 ──


def test_open_when_online_skips_launch_but_keeps_common_tail() -> None:
    """已在线不是「直接 return」：去广告与拉应用两条路都要走。"""
    fake = _FakeRun(online_from_start=True)

    async def run() -> None:
        entry, ctrl = await _make(fake)
        from auto_mas_core import Config

        Config.setting.function.if_block_ad = True
        Config.setting.function.if_silence = True
        try:
            await ctrl.open(_dev_uid(entry), "com.x", ticket=TRIGGER_TICKET)
        finally:
            Config.setting.function.if_block_ad = False
            Config.setting.function.if_silence = False

        assert fake.named("control", "-v", "0", "launch") == [], "已在线不得再拉起"
        assert fake.named("control", "-v", "0", "hide_window") == [], "也不该藏窗"
        assert fake.named("adb", "-v", "0", "shell", "appops"), "去广告须照做"
        assert fake.named("adb", "-v", "0", "shell", "am", "force-stop")
        assert fake.named("adb", "-v", "0", "shell", "dumpsys"), "拉应用须照做"

    asyncio.run(run())


# ── 2. 未启动：拉起 + 一次性副任务 ──


def test_open_launches_and_hides_exactly_once() -> None:
    """静默隐藏是一次性任务：起来那一下藏一次，不在等待循环里反复藏。"""
    fake = _FakeRun()

    async def run() -> None:
        entry, ctrl = await _make(fake)
        from auto_mas_core import Config

        Config.setting.function.if_silence = True
        try:
            await ctrl.open(_dev_uid(entry), ticket=TRIGGER_TICKET)
        finally:
            Config.setting.function.if_silence = False

        assert len(fake.named("control", "-v", "0", "launch")) == 1
        hides = fake.named("control", "-v", "0", "hide_window")
        assert len(hides) == 1, f"藏窗应只触发一次，实到 {len(hides)} 次"

    asyncio.run(run())


def test_open_without_silence_never_hides() -> None:
    fake = _FakeRun()

    async def run() -> None:
        entry, ctrl = await _make(fake)
        await ctrl.open(_dev_uid(entry), ticket=TRIGGER_TICKET)
        assert fake.named("control", "-v", "0", "hide_window") == []

    asyncio.run(run())


def test_open_without_block_ad_issues_no_adb_ad_calls() -> None:
    fake = _FakeRun()

    async def run() -> None:
        entry, ctrl = await _make(fake)
        await ctrl.open(_dev_uid(entry), ticket=TRIGGER_TICKET)
        assert fake.named("adb", "-v", "0", "shell", "appops") == []
        assert fake.named("adb", "-v", "0", "shell", "am", "force-stop") == []

    asyncio.run(run())


def test_open_with_package_reuses_the_single_launch_implementation() -> None:
    """带包名启动复用 ``_launch_app`` 这唯一一份实现，不另走一遍公开面。

    ``_open`` 里那句包在 ``suppress`` 里，拉不起来不拦启动 —— 于是任何
    「根本没下发」都会静悄悄过去：启动看着成功，应用却没拉。故断言
    官方判态那笔真到了 CLI。
    """
    fake = _FakeRun()

    async def run() -> None:
        entry, ctrl = await _make(fake)
        await ctrl.open(_dev_uid(entry), "com.x", ticket=TRIGGER_TICKET)
        assert fake.named("control", "-v", "0", "app", "info", "-pkg", "com.x"), (
            "应用拉起根本没下发"
        )

    asyncio.run(run())


# ── 3. 最小化 / 最大化：走窗口句柄，不走官方 show/hide ──


def test_min_max_never_fall_back_to_official_show_hide() -> None:
    """最小化 / 最大化是窗口状态，官方 CLI 没这两档，故不得退化成它。

    没真窗口可断的只有失败面：报错而不是静默 hide_window。
    非 Windows 上先碰平台门、Windows 上碰句柄缺失（桩的 info 不带
    ``main_wnd``）—— 两边都是 RuntimeError，故本断言两个平台同一口径。
    """
    fake = _FakeRun()

    async def run() -> None:
        entry, ctrl = await _make(fake)
        for op in (ctrl.minimize, ctrl.maximize):
            with pytest.raises(RuntimeError):
                await op(_dev_uid(entry), ticket=TRIGGER_TICKET)
        assert fake.named("control", "-v", "0", "hide_window") == []
        assert fake.named("control", "-v", "0", "show_window") == []

    asyncio.run(run())


# ── 4. 刷新：操作函数不自己 sync，靠门控循环忙时提速 ──


def test_operations_do_not_sync_themselves_and_loop_speeds_up_when_busy() -> None:
    """闲时几乎不取数；一旦 busy，info 频次明显高于 1Hz。

    间隔具体多少不断言（那是常量的事），只断言「忙时比闲时密得多」这条意图。
    """
    fake = _FakeRun()

    async def run() -> None:
        entry, ctrl = await _make(fake)
        # 闲时且不在 refresh 窗口内：循环该一笔都不取
        await asyncio.sleep(0.8)
        assert fake.info_calls == 0, "窗口外闲置不该取数"

        started = time.monotonic()
        await ctrl.open(_dev_uid(entry), ticket=TRIGGER_TICKET)
        busy_elapsed = time.monotonic() - started
        # 启动后有固定的缓冲 sleep，期间仍 busy，故用整段耗时算频次
        rate = fake.info_calls / busy_elapsed
        assert rate > 1.5, f"busy 期间 info 频次仅 {rate:.2f}/s，未进加速档"

    asyncio.run(run())


def test_metronome_releases_only_after_a_completed_sync() -> None:
    """等一下节拍器即保证读到的是新数据：放行之前必已完成一轮同步。"""
    fake = _FakeRun()

    async def run() -> None:
        _entry, ctrl = await _make(fake)
        await ctrl.refresh()  # 不开窗则循环不同步，也就不放行
        assert not ctrl._synced.is_set(), "一轮都没同步过，节拍器该是阻塞的"
        await asyncio.wait_for(ctrl._synced.wait(), 3)
        assert fake.info_calls >= 1, "节拍器放行前必须已完成一轮同步"

    asyncio.run(run())


def test_refresh_opens_window_without_syncing_itself() -> None:
    """公开 ``refresh`` 只开窗口，取数仍由循环做。"""
    fake = _FakeRun()

    async def run() -> None:
        _entry, ctrl = await _make(fake)
        await ctrl.refresh()
        assert fake.info_calls == 0, "refresh 自己不取数"
        await asyncio.sleep(1.4)
        assert fake.info_calls >= 1, "开窗后循环该开始取数"

    asyncio.run(run())
