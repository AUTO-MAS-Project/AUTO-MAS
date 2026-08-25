"""各脚本 notify.push_notification 的行为基线（characterization test）。

这个测试不主张「现状是对的」，只锁定「现状是什么」：把 8 个脚本在若干配置组合下
对 Notify 各渠道的调用序列录下来，与 tests/data/notify_parity_baseline.json 比对。

用途是为 notify 去重重构兜底——重构前后录出来的序列必须逐字节一致。
基线由 tests/task/regen_notify_baseline.py 生成（重构前跑一次即可）。
"""

import asyncio
import contextlib
import importlib
import json
from pathlib import Path
from unittest.mock import patch

import app.core  # noqa: F401  先完成 app.core 初始化, 打断 app.task 的循环导入

BASELINE_PATH = Path(__file__).parent.parent / "data" / "notify_parity_baseline.json"

SCRIPTS = ["MAA", "MaaEnd", "M9A", "SRC", "general", "Okww", "OkNte", "HSR"]


class _FakeTemplate:
    """渲染结果里带上模板名与 message 键, 这样选错模板/传错数据都能被基线抓到。"""

    def __init__(self, name: str) -> None:
        self.name = name

    def render(self, message: dict) -> str:
        return f"<html:{self.name}|keys={','.join(sorted(message))}>"


class _FakeEnv:
    def get_template(self, name: str) -> _FakeTemplate:
        return _FakeTemplate(name)


class _FakeWebhooks:
    def __init__(self, names: list[str]) -> None:
        self._names = names

    def values(self):
        return list(self._names)


class _FakeConfig:
    """替代 app.core.Config, 只实现 notify 用到的那几个成员。"""

    def __init__(self, settings: dict, webhooks: list[str]) -> None:
        self._settings = settings
        self.notify_env = _FakeEnv()
        self.Notify_CustomWebhooks = _FakeWebhooks(webhooks)

    def get(self, group: str, key: str):
        return self._settings.get((group, key))


class _FakeUserConfig:
    def __init__(self, settings: dict, webhooks: list[str]) -> None:
        self._settings = settings
        self.Notify_CustomWebhooks = _FakeWebhooks(webhooks)

    def get(self, group: str, key: str):
        return self._settings.get((group, key))


class _RecordingNotify:
    """记录每个渠道被调用的顺序与实参, 全部为 async。"""

    def __init__(self) -> None:
        self.calls: list[list] = []

    async def send_mail(self, mode, title, content, to_address):
        self.calls.append(["send_mail", mode, title, to_address, content])

    async def ServerChanPush(self, title, message, key):
        self.calls.append(["ServerChanPush", title, key, message])

    async def WebhookPush(self, title, message, webhook):
        self.calls.append(["WebhookPush", title, webhook, message])

    async def send_koishi(self, message):
        self.calls.append(["send_koishi", message])

    async def push_plyer(self, *args, **kwargs):
        self.calls.append(["push_plyer", *[str(a) for a in args]])


class _FailingNotify(_RecordingNotify):
    """指定渠道抛异常, 用于锁定「单渠道失败是否影响后续渠道」这一行为。

    M9A 用 _safe_send_channel 吞掉异常继续发后续渠道; 其余 7 个脚本会让异常冒出去。
    这是去重时最容易被静默改掉的一处差异, 必须进基线。
    """

    def __init__(self, failing: str) -> None:
        super().__init__()
        self.failing = failing

    async def send_mail(self, mode, title, content, to_address):
        self.calls.append(["send_mail", mode, title, to_address, content])
        if self.failing == "send_mail":
            raise RuntimeError("邮件渠道故障")

    async def ServerChanPush(self, title, message, key):
        self.calls.append(["ServerChanPush", title, key, message])
        if self.failing == "ServerChanPush":
            raise RuntimeError("ServerChan 渠道故障")

    async def WebhookPush(self, title, message, webhook):
        self.calls.append(["WebhookPush", title, webhook, message])
        if self.failing == "WebhookPush":
            raise RuntimeError("Webhook 渠道故障")


def _g(**over) -> dict:
    """全局 Notify 设置, 默认全开、收件人齐全。"""
    base = {
        ("Notify", "SendTaskResultTime"): "任何时刻",
        ("Notify", "IfSendMail"): True,
        ("Notify", "ToAddress"): "global@example.com",
        ("Notify", "IfServerChan"): True,
        ("Notify", "ServerChanKey"): "GLOBAL_KEY",
        ("Notify", "IfKoishiSupport"): True,
        ("Notify", "IfSendStatistic"): True,
        ("Notify", "IfSendSixStar"): True,
    }
    base.update({("Notify", k): v for k, v in over.items()})
    return base


def _u(**over) -> dict:
    """用户 Notify 设置, 默认全开、收件人齐全。"""
    base = {
        ("Notify", "Enabled"): True,
        ("Notify", "IfSendStatistic"): True,
        ("Notify", "IfSendMail"): True,
        ("Notify", "ToAddress"): "user@example.com",
        ("Notify", "IfServerChan"): True,
        ("Notify", "ServerChanKey"): "USER_KEY",
        ("Notify", "IfSendSixStar"): True,
    }
    base.update({("Notify", k): v for k, v in over.items()})
    return base


# 覆盖已知的 5 处行为差异: 签名换行/失败隔离/统计是否推全局/全局收件人校验/额外模式
SCENARIOS: dict[str, tuple[dict, dict]] = {
    "all_on": (_g(), _u()),
    "global_recipients_empty": (_g(ToAddress="", ServerChanKey=""), _u()),
    "global_stat_off": (_g(IfSendStatistic=False), _u()),
    "user_recipients_empty": (_g(), _u(ToAddress="", ServerChanKey="")),
    "user_disabled": (_g(), _u(Enabled=False)),
    "user_stat_off": (_g(), _u(IfSendStatistic=False)),
    "result_never": (_g(SendTaskResultTime="从不"), _u()),
    "result_fail_only": (_g(SendTaskResultTime="仅失败时"), _u()),
    "koishi_off": (_g(IfKoishiSupport=False), _u()),
    "all_channels_off": (
        _g(IfSendMail=False, IfServerChan=False, IfKoishiSupport=False),
        _u(IfSendMail=False, IfServerChan=False),
    ),
}

# 各 mode 的 message 夹具。键取所有脚本的并集, 保证任一脚本都不会 KeyError。
MSG_RESULT = {
    "start_time": "2026-01-01 00:00:00",
    "end_time": "2026-01-01 01:00:00",
    "completed_count": 2,
    "uncompleted_count": 0,
    "result": "全部完成",
    "game_sign_summary": False,
}
MSG_RESULT_FAILED = {**MSG_RESULT, "uncompleted_count": 1, "result": "有失败"}

# 统计信息-完整: 命中 MAA/MaaEnd/M9A 的各类统计分支
MSG_STAT_FULL = {
    "start_time": "2026-01-01 00:00:00",
    "end_time": "2026-01-01 01:00:00",
    "user_info": "用户A",
    "user_result": "代理任务全部完成",
    "maa_result": "全部完成",
    "sanity": "120",
    "sanity_full_at": "2026-01-01 06:00:00",
    "drop_statistics": {"1-7": {"固源岩": 3}},
    "recruit_statistics": {"3星": 2, "6星": 1},
    "matrix_statistics": {"技能1": "武器A"},
    "pull_count_statistics": {
        "current_pool_total": 10,
        "next_pool_total": 20,
        "resource_pulls": 5,
        "carry_over_pulls": 2,
    },
    "task_details": "任务明细",
}

# 统计信息-最简: 只留必需键, 命中「无统计数据」的空分支
MSG_STAT_MIN = {
    "start_time": "2026-01-01 00:00:00",
    "end_time": "2026-01-01 01:00:00",
    "user_info": "用户A",
    "user_result": "代理任务全部完成",
    "maa_result": "全部完成",
}

MSG_SIX_STAR = {"user_name": "用户A", "star": "6星"}

MODES: dict[str, tuple[str, dict]] = {
    "result_ok": ("代理结果", MSG_RESULT),
    "result_failed": ("代理结果", MSG_RESULT_FAILED),
    "stat_full": ("统计信息", MSG_STAT_FULL),
    "stat_min": ("统计信息", MSG_STAT_MIN),
    "six_star": ("公招六星", MSG_SIX_STAR),
}


def _load_module(script: str):
    return importlib.import_module(f"app.task.{script}.tools.notify")


@contextlib.contextmanager
def _patched(mod, fake_cfg, notify):
    """把 Config/Notify 替换掉——脚本模块和公共渠道模块都要打。

    去重后 fan-out 发生在 app.tools.notify_channels 里, 那里有自己的 Config/Notify
    引用; 只打脚本模块的话假对象会被绕过, 测试会静默失效(甚至真去连 SMTP)。
    公共模块尚不存在时(重构前)自动跳过, 保证基线在重构前后都能录。
    """
    try:
        channels = importlib.import_module("app.tools.notify_channels")
    except ModuleNotFoundError:
        channels = None

    with contextlib.ExitStack() as stack:
        # 迁移后脚本模块不再直接引用 Notify(fan-out 移到公共模块), 故按实际存在的属性打桩
        for target in (mod, channels):
            if target is None:
                continue
            for attr, value in (("Config", fake_cfg), ("Notify", notify)):
                if hasattr(target, attr):
                    stack.enter_context(patch.object(target, attr, value))
        yield


def record_all() -> dict:
    """跑完 8 脚本 × 10 场景 × 5 mode, 返回 Notify 调用序列。"""
    out: dict = {}
    for script in SCRIPTS:
        mod = _load_module(script)
        out[script] = {}
        for scen_name, (gset, uset) in SCENARIOS.items():
            out[script][scen_name] = {}
            for mode_name, (mode, message) in MODES.items():
                notify = _RecordingNotify()
                fake_cfg = _FakeConfig(gset, ["hookA", "hookB"])
                fake_user = _FakeUserConfig(uset, ["userHook"])
                with _patched(mod, fake_cfg, notify):
                    asyncio.run(
                        mod.push_notification(mode, "标题T", dict(message), fake_user)
                    )
                out[script][scen_name][mode_name] = notify.calls

            # M9A 独有入口: 版本更新通知
            if hasattr(mod, "push_version_update"):
                notify = _RecordingNotify()
                fake_cfg = _FakeConfig(gset, ["hookA", "hookB"])
                with _patched(mod, fake_cfg, notify):
                    asyncio.run(
                        mod.push_version_update(
                            "标题V", {**MSG_RESULT, "title": "T", "script_name": "S"}
                        )
                    )
                out[script][scen_name]["version_update"] = notify.calls

        # 单渠道故障: 记录「后续渠道是否仍被调用」+「异常是否冒出」
        out[script]["_channel_failure"] = {}
        for failing in ("send_mail", "ServerChanPush", "WebhookPush"):
            notify = _FailingNotify(failing)
            fake_cfg = _FakeConfig(_g(), ["hookA", "hookB"])
            fake_user = _FakeUserConfig(_u(), ["userHook"])
            raised: str | None = None
            with _patched(mod, fake_cfg, notify):
                try:
                    asyncio.run(
                        mod.push_notification(
                            "统计信息", "标题T", dict(MSG_STAT_FULL), fake_user
                        )
                    )
                except Exception as e:
                    raised = type(e).__name__
            out[script]["_channel_failure"][failing] = {
                "calls": [c[0] for c in notify.calls],
                "raised": raised,
            }
    return out


def test_notify_channel_parity_matches_baseline() -> None:
    """8 个脚本的渠道调用序列必须与基线逐字节一致。

    这个测试失败意味着某脚本的通知行为变了——重构期间不允许发生。
    若是有意变更行为, 重新生成基线并在 commit 里说明改了什么、为什么。
    """
    assert BASELINE_PATH.is_file(), (
        f"基线缺失: {BASELINE_PATH}\n"
        "请在重构前的代码上运行 python tests/task/regen_notify_baseline.py 生成"
    )
    expected = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    actual = json.loads(json.dumps(record_all(), ensure_ascii=False))

    assert set(actual) == set(expected), "脚本集合发生变化"
    for script in sorted(expected):
        for scen in sorted(expected[script]):
            for mode in sorted(expected[script][scen]):
                assert actual[script][scen][mode] == expected[script][scen][mode], (
                    f"{script} / {scen} / {mode} 的通知渠道调用序列与基线不符"
                )
