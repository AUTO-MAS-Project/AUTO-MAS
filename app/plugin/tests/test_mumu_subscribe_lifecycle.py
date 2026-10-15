"""MuMu 实例订阅生命周期：备份 / 稳定模式写入 / 整份还原 / 凭据校验。

在 ``MuMuControl._run`` 这一层打桩 —— 那是唯一的 CLI 出口，断言到达它的
参数即断言真实会下发给 ``MuMuManager.exe`` 的内容。不碰真机。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from app.config import ConfigCollection, LockTicket, UiVisibility
from app.core.game_manager import _GameRuntime
from app.models.config.game import TRIGGER_TICKET
from app.plugin.base.emulator import EmulatorExpect
from app.plugin.base.game import DeviceSubscribeError
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

# ``-aw`` 的完整可写面（MuMu 12 为 44 键）。这里取真实键名的代表子集 +
# 填充键凑满 44：断言"整份往返"要的是键数与值的原样性，不是键名清单本身。
# **值故意混类型**：官方吐的是 JSON，布尔与数字都可能出现，备份不该把它们
# 归一成字符串 —— 往返断言因此同时守住"类型也原样"。
_AW_REAL: dict[str, Any] = {
    "app_keptlive": True,  # 稳定模式项（bool 而非 "true"）
    "dynamic_adjust_frame_rate": "true",  # 同上，字符串形态
    "vertical_sync": False,
    "show_frame_rate": "false",
    "window_auto_rotate": True,
    "renderer_strategy": "dis",  # MAA 点名不可用的那一档
    "resolution_mode": "phone",
    "resolution_width.custom": 1080,  # int
    "resolution_height.custom": 1920,
    "resolution_dpi.custom": 480,
    "performance_mode": "middle",
    "performance_cpu.custom": 4,
    "performance_mem.custom": 4,
    "max_frame_rate": 60,
    "player_name": "我的实例",
    "root_permission": False,
}
_AW_FULL: dict[str, Any] = dict(_AW_REAL) | {
    f"filler_key_{i}": f"v{i}" for i in range(44 - len(_AW_REAL))
}
assert len(_AW_FULL) == 44

# 分辨率必写的三键（宽高 + 模式门）。稳定项不在这里：任务不提就不写。
_RES_FIX = {
    "resolution_width.custom": "1280",
    "resolution_height.custom": "720",
    "resolution_mode": "custom",
}


class _FakeRun:
    """替掉 ``MuMuControl._run``：记录每次调用，按需给出脚本化 stdout。"""

    def __init__(
        self,
        indexes: tuple[str, ...] = ("0",),
        aw: dict[str, Any] | None = None,
        aw_empty: bool = False,
        restore_fails: bool = False,
    ) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.restore_payloads: list[dict[str, Any]] = []
        self._indexes = indexes
        # 每台实例一份独立的当前配置，写入就地生效 —— 才能验往返
        self._state: dict[str, dict[str, Any]] = {
            i: dict(aw or _AW_FULL) for i in indexes
        }
        self._aw_empty = aw_empty
        self._restore_fails = restore_fails

    def state(self, idx: str) -> dict[str, Any]:
        return self._state[idx]

    def setting_writes(self) -> list[dict[str, str]]:
        """所有 -k/-val 写入调用，解析成 {key: value}。"""
        out: list[dict[str, str]] = []
        for call in self.calls:
            if call[0] != "setting" or "-k" not in call:
                continue
            out.append(self._parse_pairs(call))
        return out

    @staticmethod
    def _parse_pairs(call: tuple[str, ...]) -> dict[str, str]:
        pairs: dict[str, str] = {}
        rest = list(call)
        while "-k" in rest:
            ki = rest.index("-k")
            pairs[rest[ki + 1]] = rest[ki + 3]
            rest = rest[ki + 4 :]
        return pairs

    async def __call__(self, *args: str | int, timeout: float | None = None) -> Any:
        call = tuple(str(a) for a in args)
        self.calls.append(call)

        if call[0] == "info":
            rows = {
                i: {"index": i, "name": f"MuMu-{i}", "is_process_started": False}
                for i in self._indexes
            }
            return ProcessResult(stdout=json.dumps(rows), stderr="", returncode=0)

        if call[0] == "setting":
            idx = call[2]
            if "-aw" in call:
                if self._aw_empty:
                    return ProcessResult(stdout="{}", stderr="", returncode=0)
                return ProcessResult(
                    stdout=json.dumps(self._state[idx]), stderr="", returncode=0
                )
            if "-p" in call:
                payload = json.loads(
                    Path(call[call.index("-p") + 1]).read_text(encoding="utf-8")
                )
                self.restore_payloads.append(payload)
                if self._restore_fails:
                    return ProcessResult(stdout="boom", stderr="", returncode=1)
                self._state[idx] = dict(payload)
                return ProcessResult(stdout="", stderr="", returncode=0)
            # -k/-val：就地生效
            self._state[idx].update(self._parse_pairs(call))
            return ProcessResult(stdout="", stderr="", returncode=0)

        return ProcessResult(stdout="", stderr="", returncode=0)


def _ticket() -> LockTicket:
    return LockTicket(mode="s", token=uuid4(), issuer=uuid4(), cascade=False)


async def _make(
    fake: _FakeRun, *, devices: tuple[str, ...] = ("0",)
) -> tuple[MuMuGame, MuMuControl]:
    """造一个已激活的 MuMuGame + 打好桩的 Control。"""
    games: ConfigCollection[MuMuGame] = ConfigCollection(
        [MuMuGame], name=f"games_{uuid4().hex}"
    )
    await games.activate()
    uid = games.add(MuMuGame)
    await games.commit()
    entry = games[uid]
    # path 只做 _run 的前置检查用；_run 已打桩，不真的执行
    entry.info.path = Path("MuMuManager.exe")

    ctrl = MuMuControl(config=entry)
    ctrl.bind_runtime(_GameRuntime())
    entry._game_control = ctrl
    ctrl._run = fake  # type: ignore[method-assign]
    for idx in devices:
        entry.devices.add(MuMuDevice, payload={"info": {"index": idx}})
        await entry.devices.commit()
    return entry, ctrl


async def _sub(
    ctrl: MuMuControl,
    ticket: LockTicket,
    idx: str,
    usage: str,
    expect: EmulatorExpect | None = None,
) -> Any:
    """按多开序号订阅：index → uid 从 devices 反查，订阅走基类。"""
    uid = next(u for u, d in ctrl.config.devices.items() if d.info.index == idx)
    return await ctrl.subscribe_device(ticket, uid, usage, expect)


def _dev(entry: MuMuGame, idx: str) -> MuMuDevice:
    dev = next(d for d in entry.devices.values() if d.info.index == idx)
    assert isinstance(dev, MuMuDevice)
    return dev


# ── 1. 订阅：备份全存 + 写入集精确 ──


def test_subscribe_backs_up_all_and_writes_expected() -> None:
    fake = _FakeRun()

    async def run() -> None:
        entry, ctrl = await _make(fake)
        await _sub(ctrl, 
            _ticket(),
            "0",
            "明日方舟 - 账号A 日常",
            EmulatorExpect(width=1280, height=720),
        )
        assert _dev(entry, "0").session.backup == _AW_FULL, "备份须是 -aw 原样全量"

        writes = fake.setting_writes()
        assert len(writes) == 1, "写入应合成一次 setting 调用"
        # 稳定项全 None（不做要求）→ 一个都不写，显存策略也不例外
        assert writes[0] == _RES_FIX
        # 没提要求的稳定项不碰；cpu/内存/帧率不碰；dpi 未给则不动
        for untouched in (
            "renderer_strategy",
            "app_keptlive",
            "dynamic_adjust_frame_rate",
            "vertical_sync",
            "show_frame_rate",
            "window_auto_rotate",
            "performance_mode",
            "performance_cpu.custom",
            "performance_mem.custom",
            "max_frame_rate",
            "resolution_dpi.custom",
        ):
            assert untouched not in writes[0]

    asyncio.run(run())


def test_subscribe_writes_dpi_when_given() -> None:
    fake = _FakeRun()

    async def run() -> None:
        _, ctrl = await _make(fake)
        await _sub(ctrl, 
            _ticket(),
            "0",
            "任务",
            EmulatorExpect(width=1280, height=720, dpi=240),
        )
        assert fake.setting_writes()[0]["resolution_dpi.custom"] == "240"

    asyncio.run(run())


def test_subscribe_without_expect_writes_nothing() -> None:
    """``expect=None``：任务没提期望，就没有该改的键。只备份与还原。"""
    fake = _FakeRun()

    async def run() -> None:
        entry, ctrl = await _make(fake)
        await _sub(ctrl, _ticket(), "0", "任务")
        assert fake.setting_writes() == [], "不提期望时一个键都不该写"
        assert _dev(entry, "0").session.backup == _AW_FULL, "但备份照做"

    asyncio.run(run())


def test_stable_items_are_tri_state() -> None:
    """稳定项三态：``None`` 不碰该键；给了值就按值覆写，不看当前是什么。"""
    fake = _FakeRun()

    async def run() -> None:
        _, ctrl = await _make(fake)
        await _sub(
            ctrl,
            _ticket(),
            "0",
            "任务",
            EmulatorExpect(
                width=1280,
                height=720,
                keep_alive=False,  # 当前 True → 覆写
                vertical_sync=False,  # 当前已是 False → 照样按要求写
                display_fps=True,  # 反向要求也照写，品牌不判断
                # high_frame_rate / auto_rotate 留 None
            ),
        )
        written = fake.setting_writes()[0]
        assert written["app_keptlive"] == "false"
        assert written["vertical_sync"] == "false"
        assert written["show_frame_rate"] == "true"
        # None 的两项一个字都不碰，留用户原值
        assert "dynamic_adjust_frame_rate" not in written
        assert "window_auto_rotate" not in written
        assert fake.state("0")["window_auto_rotate"] is True

    asyncio.run(run())


def test_enum_stable_item_uses_allowed_values() -> None:
    """枚举项按容许值表判：表内不动，越界写表首；不给表则该键不碰。"""

    async def run() -> None:
        # 当前 dis 越界 → 写表首 auto
        fake = _FakeRun()
        _, ctrl = await _make(fake)
        await _sub(
            ctrl,
            _ticket(),
            "0",
            "任务",
            EmulatorExpect(width=1280, height=720, vram_strategy=("auto", "perf")),
        )
        assert fake.setting_writes()[0]["renderer_strategy"] == "auto"

        # 当前 perf 在表内 → 一个字都不碰，留用户的性能偏好
        fake2 = _FakeRun(aw=dict(_AW_FULL) | {"renderer_strategy": "perf"})
        _, ctrl2 = await _make(fake2)
        await _sub(
            ctrl2,
            _ticket(),
            "0",
            "任务",
            EmulatorExpect(width=1280, height=720, vram_strategy=("auto", "perf")),
        )
        assert "renderer_strategy" not in fake2.setting_writes()[0]
        assert fake2.state("0")["renderer_strategy"] == "perf"

    asyncio.run(run())


def test_backup_preserves_vendor_value_types() -> None:
    """备份原样搬运厂商值：布尔仍是布尔、数字仍是数字，不归一成字符串。"""
    fake = _FakeRun()

    async def run() -> None:
        entry, ctrl = await _make(fake)
        await _sub(
            ctrl, _ticket(), "0", "任务", EmulatorExpect(width=1280, height=720)
        )
        backup = _dev(entry, "0").session.backup
        assert backup["app_keptlive"] is True
        assert backup["root_permission"] is False
        assert backup["performance_cpu.custom"] == 4
        assert not isinstance(backup["max_frame_rate"], str)

    asyncio.run(run())


# ── 2. -aw 读空 → 拒绝订阅，不写、不留半份备份 ──


def test_subscribe_refuses_when_aw_empty() -> None:
    fake = _FakeRun(aw_empty=True)

    async def run() -> None:
        entry, ctrl = await _make(fake)
        with pytest.raises(RuntimeError, match="设置读不出"):
            await _sub(ctrl, _ticket(), "0", "任务")
        assert _dev(entry, "0").session.backup == {}
        assert fake.setting_writes() == []
        assert ctrl._subs == {}, "失败须撤销登记，否则实例永久被占"

    asyncio.run(run())


# ── 3. 异票订阅同台 → 报错并带出占用者 intent ──


def test_second_ticket_rejected_with_occupant_intent() -> None:
    fake = _FakeRun()

    async def run() -> None:
        _, ctrl = await _make(fake)
        # 首个订阅带期望，产生 1 次写入 —— 后面才好断言被拒的那次没再加
        await _sub(
            ctrl,
            _ticket(),
            "0",
            "明日方舟 - 账号A 日常",
            EmulatorExpect(width=1280, height=720),
        )
        with pytest.raises(DeviceSubscribeError) as ei:
            await _sub(
                ctrl,
                _ticket(),
                "0",
                "另一个任务",
                EmulatorExpect(width=1920, height=1080),
            )
        assert ei.value.usage is not None
        assert ei.value.usage == "明日方舟 - 账号A 日常"
        assert "明日方舟 - 账号A 日常" in str(ei.value)
        assert len(fake.setting_writes()) == 1, "被拒的订阅不应产生写入"

    asyncio.run(run())


# ── 4. 同游戏不同实例 → 各自独立备份 ──


def test_two_instances_backup_independently() -> None:
    fake = _FakeRun(indexes=("0", "1"))
    fake.state("1")["player_name"] = "第二台"

    async def run() -> None:
        entry, ctrl = await _make(fake, devices=("0", "1"))
        await _sub(ctrl, _ticket(), "0", "任务A")
        await _sub(ctrl, _ticket(), "1", "任务B")
        assert _dev(entry, "0").session.backup["player_name"] == "我的实例"
        assert _dev(entry, "1").session.backup["player_name"] == "第二台"
        assert len(ctrl._subs) == 2

    asyncio.run(run())


# ── 5. 释放：整份写回，往返每键回到原值 ──


def test_unsubscribe_restores_full_dump_and_clears_backup() -> None:
    fake = _FakeRun()

    async def run() -> None:
        entry, ctrl = await _make(fake)
        handle = await _sub(ctrl, 
            _ticket(),
            "0",
            "任务",
            EmulatorExpect(width=1280, height=720),
        )
        # 订阅确实改了当台状态
        assert fake.state("0")["resolution_width.custom"] == "1280"
        assert fake.state("0")["resolution_mode"] == "custom"

        await handle.release()
        assert fake.restore_payloads == [_AW_FULL], "整份 44 键写回"
        assert fake.state("0") == _AW_FULL, "往返后每个键回到原值"
        assert _dev(entry, "0").session.backup == {}
        assert ctrl._subs == {}

    asyncio.run(run())


# ── 6. 还原失败 → 备份保留 ──


def test_unsubscribe_failure_keeps_backup() -> None:
    fake = _FakeRun(restore_fails=True)

    async def run() -> None:
        entry, ctrl = await _make(fake)
        handle = await _sub(ctrl, _ticket(), "0", "任务")
        with pytest.raises(RuntimeError):
            await handle.release()
        assert _dev(entry, "0").session.backup == _AW_FULL, "原值唯一记录须留住"
        assert handle.device_uid in ctrl._subs, "还原完成前须保留原票"
        assert not handle._released
        fake._restore_fails = False
        await handle.release()
        assert _dev(entry, "0").session.backup == {}
        assert ctrl._subs == {}

    asyncio.run(run())


# ── 7. 同票重复订阅 → 引用计数，只备份一次、末次才还原 ──


def test_same_ticket_refcounts() -> None:
    fake = _FakeRun()

    async def run() -> None:
        entry, ctrl = await _make(fake)
        ticket = _ticket()
        h1 = await _sub(ctrl, 
            ticket, "0", "任务", EmulatorExpect(width=1280, height=720)
        )
        h2 = await _sub(ctrl, ticket, "0", "任务 第二段")
        assert len(fake.setting_writes()) == 1, "第二次订阅不重复写入"
        assert ctrl._subs[h1.device_uid].count == 2

        await h2.release()
        assert fake.restore_payloads == [], "非末个引用不还原"
        assert _dev(entry, "0").session.backup == _AW_FULL

        await h1.release()
        assert fake.restore_payloads == [_AW_FULL]
        assert _dev(entry, "0").session.backup == {}

    asyncio.run(run())


# ── 8. unsubscribe → 该票名下全部实例被退订 ──


def test_unsubscribe_releases_all_devices_of_ticket() -> None:
    from app.core import Config
    from app.core.game_manager import GameManager

    fake = _FakeRun(indexes=("0", "1"))

    async def run() -> None:
        entry, ctrl = await _make(fake, devices=("0", "1"))

        class _Games:
            def get(self, uid: object) -> MuMuGame | None:
                return entry if uid == entry.uid else None

        previous = Config.GameConfig
        Config.GameConfig = _Games()  # type: ignore[assignment]
        try:
            got_ctrl, ticket = await GameManager.subscribe(entry.uid)
            assert got_ctrl is ctrl
            await _sub(ctrl, ticket, "0", "任务 台0")
            await _sub(ctrl, ticket, "1", "任务 台1")
            assert len(ctrl._subs) == 2

            await GameManager.unsubscribe(ticket)
            assert ctrl._subs == {}, "退订须连带退订该票名下全部实例"
            assert len(fake.restore_payloads) == 2
            assert _dev(entry, "0").session.backup == {}
            assert _dev(entry, "1").session.backup == {}
            assert not entry.is_locked
        finally:
            Config.GameConfig = previous

    asyncio.run(run())


# ── 9. 触发器路径：开关不产生任何 setting 写入 ──


def test_trigger_close_writes_no_settings() -> None:
    fake = _FakeRun()

    async def run() -> None:
        entry, ctrl = await _make(fake)
        # 实例未在线，_close 早退；这里只关心有无配置写入
        await ctrl.close(_dev(entry, "0").uid, ticket=TRIGGER_TICKET)
        assert [c for c in fake.calls if c[0] == "setting"] == []

    asyncio.run(run())


def test_trigger_ticket_skips_subscribe_check_even_when_claimed() -> None:
    fake = _FakeRun()

    async def run() -> None:
        entry, ctrl = await _make(fake)
        await _sub(ctrl, _ticket(), "0", "别人的任务")
        # 用户权限最高：被别的任务订阅时触发器票仍直通，不报错
        ctrl.check_subscription(_dev(entry, "0").uid, TRIGGER_TICKET)

    asyncio.run(run())


# ── 10. 启动清扫 ──


def test_sweep_backups_restores_leftover() -> None:
    fake = _FakeRun()

    async def run() -> None:
        entry, ctrl = await _make(fake)
        dev = _dev(entry, "0")
        # 伪造「上次进程没走完退订路径」：备份在盘上，内存登记随进程消失
        dev.session.backup = dict(_AW_FULL)
        await dev.commit()
        fake.state("0")["resolution_mode"] = "custom"  # 上次订阅留下的改动

        await ctrl.sweep_backups()
        assert fake.restore_payloads == [_AW_FULL]
        assert fake.state("0") == _AW_FULL
        assert _dev(entry, "0").session.backup == {}

    asyncio.run(run())


# ── 11. 旧配置载入：已删字段的旧键不炸 ──


def test_legacy_payload_activates() -> None:
    async def run() -> None:
        games: ConfigCollection[MuMuGame] = ConfigCollection(
            [MuMuGame], name=f"games_{uuid4().hex}"
        )
        await games.activate()
        dev_uid = str(uuid4())
        uid = games.add(
            MuMuGame,
            payload={
                # 本次删掉的两个开关 + 改名前的设备组名
                "info": {"name": "MuMu", "stable_mode": True, "config_guard": True},
                "devices": {
                    "order": [{"uid": dev_uid, "type": "MuMuDevice"}],
                    "data": {
                        dev_uid: {
                            "info": {"index": "0"},
                            # 旧的守卫基准组，已改名为 session
                            "settings": {"resolution_mode": "phone"},
                        }
                    },
                },
            },
        )
        await games.commit()  # 旧键不抛错即达标
        entry = games[uid]
        assert _dev(entry, "0").session.backup == {}, "旧基准不复活成会话备份"

    asyncio.run(run())


# ── 12. 绕过 handle 直接调裸方法 → 仍被挡 ──


def test_bypassing_handle_is_still_checked() -> None:
    fake = _FakeRun()

    async def run() -> None:
        entry, ctrl = await _make(fake)
        dev_uid = _dev(entry, "0").uid
        stranger = _ticket()
        with pytest.raises(DeviceSubscribeError, match="未订阅"):
            await ctrl.open(dev_uid, ticket=stranger)

        # 已被他票订阅时，报错带出占用者
        await _sub(ctrl, _ticket(), "0", "占用中的任务")
        with pytest.raises(DeviceSubscribeError) as ei:
            await ctrl.close(dev_uid, ticket=stranger)
        assert ei.value.usage is not None
        assert ei.value.usage == "占用中的任务"

    asyncio.run(run())


# ── 13. 被订阅时触发器 UI 仍可用 ──


def test_trigger_ui_stays_show_when_subscribed() -> None:
    from app.models.config.game import DeviceStatus

    fake = _FakeRun()

    async def run() -> None:
        entry, ctrl = await _make(fake)
        dev = _dev(entry, "0")
        await _sub(ctrl, _ticket(), "0", "任务")
        dev._raw = {
            "index": "0",
            "is_process_started": True,
            "is_android_started": True,
            "main_wnd": "0x1",
        }
        assert dev.info.status == DeviceStatus.ONLINE
        assert dev.busy is False
        assert dev._vis_close() is UiVisibility.SHOW, "订阅不得拦用户按钮"
        assert dev._vis_open() is UiVisibility.HIDE  # 在线本就隐藏启动

    asyncio.run(run())


# ── 14. 忙标记只在控制器一处：配置读它，不自己存 ──


def test_busy_reads_controller_only() -> None:
    fake = _FakeRun()

    async def run() -> None:
        entry, ctrl = await _make(fake)
        dev = _dev(entry, "0")
        dev._raw = {
            "index": "0",
            "is_process_started": True,
            "is_android_started": True,
            "main_wnd": "0x1",
        }
        assert dev.busy is False

        # 占住控制器的唯一执行器：设备侧 busy 随之为真，UI 转 DISABLE
        gate: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        job = asyncio.ensure_future(ctrl.execute(gate))
        await asyncio.sleep(0)
        assert ctrl.busy is True
        assert dev.busy is True, "设备 busy 须直读控制器，不存第二份"
        assert dev._vis_close() is UiVisibility.DISABLE
        gate.set_result(None)
        await job
        assert dev.busy is False

        # 配置上不该再有自己的忙标记
        assert "_busy" not in type(dev).__private_attributes__

    asyncio.run(run())
