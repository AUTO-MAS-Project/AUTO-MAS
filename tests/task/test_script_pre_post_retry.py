import ast
import asyncio
from datetime import datetime
from pathlib import Path

import pytest

from app.models.task import LogRecord, ScriptItem, UserItem
from app.task.base import ScriptAutoProxyBase


class Proxy(ScriptAutoProxyBase):
    """最小 ScriptAutoProxyBase 子类：只复刻真实适配器的调用顺序（前脚本一次 + 全部重试），
    其余副作用全部省掉，用注入的 execute_script_task 记录调用。"""

    run_timeout_seconds = 10

    def __init__(self, user_config, retries):
        super().__init__()
        self.cur_user_config = user_config
        self.retries = retries
        self.cur_user_item = UserItem("test", "测试账号", "运行")
        self.cur_user_item.log_record[datetime.now()] = LogRecord(status="运行中")
        self.script_info = ScriptItem("script", "测试脚本", "运行")
        self.attempts = 0
        self.crashed = False
        self.finalized = False

    async def main_task(self):
        # 与真实适配器一致：前脚本在全部重试之前，整个重试期间只调用一次
        await self.run_user_scripts_before()
        for _ in range(self.retries):
            self.attempts += 1
            # 每轮都判为失败，模拟重试到底
        raise RuntimeError("全部重试失败")

    async def final_task(self):
        self.finalized = True

    async def on_crash(self, error):
        self.crashed = True


async def _run(proxy):
    async with asyncio.TaskGroup() as group:
        await proxy._execute_task(group)


def _record_scripts(monkeypatch, module="app.task.general.tools"):
    calls = []

    async def fake_execute(script_path, task_name):
        calls.append(Path(script_path))
        return True

    monkeypatch.setattr(f"{module}.execute_script_task", fake_execute)
    return calls


@pytest.mark.parametrize(
    "config_name",
    ["MaaUserConfig", "SrcUserConfig", "GeneralUserConfig"],
)
@pytest.mark.parametrize("retries", [1, 3])
def test_before_once_after_once_on_terminal_failure(
    config_name, retries, tmp_path, monkeypatch
):
    """用户级前/后脚本的成对语义：前脚本在全部重试前只跑一次，失败终态后置脚本仍执行一次。"""

    from app.models import config as configs

    calls = _record_scripts(monkeypatch)
    before = tmp_path / "before.bat"
    after = tmp_path / "after.bat"

    async def scenario():
        cfg = getattr(configs, config_name)()
        await cfg.set("Info", "IfScriptBeforeTask", True)
        await cfg.set("Info", "ScriptBeforeTask", str(before))
        await cfg.set("Info", "IfScriptAfterTask", True)
        await cfg.set("Info", "ScriptAfterTask", str(after))
        proxy = Proxy(cfg, retries)
        await _run(proxy)
        return proxy

    proxy = asyncio.run(scenario())

    # 前脚本恰好一次、后脚本恰好一次，与重试次数无关
    assert calls == [before, after]
    assert proxy.attempts == retries
    assert proxy.crashed and proxy.finalized
    assert proxy._user_scripts_started is False


def test_after_skipped_when_before_never_ran(tmp_path, monkeypatch):
    """后置脚本由"前置已执行"标记把关：适配器漏调前置钩子时后置不会凭空执行。"""

    from app.models import config as configs

    calls = _record_scripts(monkeypatch)
    after = tmp_path / "after.bat"

    class NoHookProxy(Proxy):
        async def main_task(self):
            raise RuntimeError("没有调用前脚本钩子")

    async def scenario():
        cfg = configs.GeneralUserConfig()
        await cfg.set("Info", "IfScriptAfterTask", True)
        await cfg.set("Info", "ScriptAfterTask", str(after))
        proxy = NoHookProxy(cfg, 1)
        await _run(proxy)
        return proxy

    proxy = asyncio.run(scenario())
    assert calls == []
    assert proxy.crashed and proxy.finalized


def _main_task(tree):
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "main_task"
        ):
            return node
    return None


def _before_hook_calls(main_task):
    """返回 main_task 内 self.run_user_scripts_before() 的 (行号, 是否位于循环内)。"""

    found = []

    def visit(node, in_loop):
        for child in ast.iter_child_nodes(node):
            child_in_loop = in_loop or isinstance(
                child, (ast.For, ast.While, ast.AsyncFor)
            )
            if (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
                and child.func.attr == "run_user_scripts_before"
                and isinstance(child.func.value, ast.Name)
                and child.func.value.id == "self"
            ):
                found.append((child.lineno, child_in_loop))
            visit(child, child_in_loop)

    visit(main_task, False)
    return found


# 适配器目录 -> 用户配置类：判断该专项是否真的向用户暴露了前后脚本字段
ADAPTER_CONFIG = {
    "MAA": "MaaUserConfig",
    "MaaEnd": "MaaEndUserConfig",
    "SRC": "SrcUserConfig",
    "Okww": "OkwwUserConfig",
    "OkNte": "OkNteUserConfig",
    "ZzzOd": "ZzzOdUserConfig",
    "BetterGI": "BetterGIUserConfig",
    "Whimbox": "WhimboxUserConfig",
    "general": "GeneralUserConfig",
    "BAAH": "BAAHUserConfig",
}


@pytest.mark.parametrize("adapter", sorted(ADAPTER_CONFIG))
def test_before_hook_wired_before_every_retry_loop(adapter):
    """横向不变量：凡是配置里暴露了任务前脚本的专项，main_task 都必须在任何重试循环之前
    恰好调用一次前脚本钩子——漏调（BAAH 之外）或挪进重试循环都会让这条变红。"""

    from app.models import config as configs

    main_task = _main_task(
        ast.parse(
            (Path("app/task") / adapter / "AutoProxy.py").read_text(encoding="utf-8")
        )
    )
    assert main_task is not None, f"{adapter} 缺少 main_task"

    hooks = _before_hook_calls(main_task)
    loops = [
        n.lineno
        for n in ast.walk(main_task)
        if isinstance(n, (ast.For, ast.While, ast.AsyncFor))
    ]

    exposes_scripts = hasattr(
        getattr(configs, ADAPTER_CONFIG[adapter])(), "Info_IfScriptBeforeTask"
    )

    if exposes_scripts:
        assert len(hooks) == 1, f"{adapter} 前脚本钩子应恰好调用一次，实际 {hooks}"
        hook_line, in_loop = hooks[0]
        assert not in_loop, f"{adapter} 前脚本钩子被放进了重试循环，重试时会重复执行"
        assert any(loop_line > hook_line for loop_line in loops), (
            f"{adapter} 前脚本钩子没有出现在任何重试循环之前"
        )
    else:
        # 未向用户暴露前后脚本字段的专项（当前仅 BAAH）不应调用该钩子
        assert hooks == [], f"{adapter} 未暴露前后脚本字段，却调用了前脚本钩子"


def test_hsr_before_after_scripts(tmp_path, monkeypatch):
    """HSR 独立实现的用户级前后脚本：开启时各执行一次，关闭时跳过。"""

    calls = _record_scripts(monkeypatch, "app.task.HSR.tools.extra_script")
    from app.task.HSR.tools.extra_script import (
        run_script_after_task,
        run_script_before_task,
    )

    before = tmp_path / "before.bat"
    after = tmp_path / "after.bat"

    async def scenario():
        from app.models.config import HSRUserConfig

        cfg = HSRUserConfig()
        await cfg.set("Info", "IfScriptBeforeTask", True)
        await cfg.set("Info", "ScriptBeforeTask", str(before))
        await cfg.set("Info", "IfScriptAfterTask", True)
        await cfg.set("Info", "ScriptAfterTask", str(after))
        await run_script_before_task(cfg)
        await run_script_after_task(cfg)

        off = HSRUserConfig()
        await off.set("Info", "IfScriptBeforeTask", False)
        await off.set("Info", "IfScriptAfterTask", False)
        await run_script_before_task(off)
        await run_script_after_task(off)

    asyncio.run(scenario())
    assert calls == [before, after]
