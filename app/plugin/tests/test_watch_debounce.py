"""源码监视冒烟：路径映射过滤 + 多包变更防抖合并为一次 sources_changed。

用法（仓库根目录）::

    python -m app.plugin.tests.test_watch_debounce
"""

from __future__ import annotations

import asyncio
import contextlib
import tempfile
from pathlib import Path

from app.plugin.runtime.watch import SourceWatcher
from app.plugin.signals import sources_changed
from app.plugin.types import SourcesChangedPayload


def _fail(message: str) -> None:
    raise AssertionError(message)


def _ok(message: str) -> None:
    print(f"OK: {message}")


async def test_local_dir_filter() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        w = SourceWatcher(plugins_dir=root)
        if w._local_dir(root / "a" / "src" / "x.py") != root.resolve() / "a":
            _fail("代码文件应映射到工程根")
        if w._local_dir(root / "a" / "README.md") is not None:
            _fail("非代码后缀应忽略")
        if w._local_dir(root / "a" / "__pycache__" / "x.py") is not None:
            _fail("__pycache__ 应忽略")
        if w._local_dir(root / "top.py") is not None:
            _fail("顶层文件无归属应忽略")
        if w._local_dir(root / "a", is_directory=True) != root.resolve() / "a":
            _fail("插件目录事件应映射到工程根")
        if w._local_dir(root / "a" / ".git", is_directory=True) is not None:
            _fail("忽略目录事件不应触发刷新")
        _ok("路径映射与忽略过滤")


async def test_debounce_merge() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        a = root / "a"
        b = root / "b"
        c = root / "c"
        (a / "src" / "a_pkg").mkdir(parents=True)
        (b / "src" / "b_pkg").mkdir(parents=True)
        (c / "src" / "c_pkg").mkdir(parents=True)
        (a / "src" / "a_pkg" / "__init__.py").write_text("", encoding="utf-8")
        (c / "src" / "c_pkg" / "__init__.py").write_text("", encoding="utf-8")

        w = SourceWatcher(plugins_dir=root, debounce=0.05)
        loop = asyncio.get_running_loop()
        # 不起真实 Observer：手工置 running 状态，驱动 _run 验证防抖/合并
        w._running = True
        w._loop = loop
        w._event = asyncio.Event()
        task = loop.create_task(w._run())
        received: list[SourcesChangedPayload] = []

        def on_sources(sender: object, payload: SourcesChangedPayload) -> None:
            received.append(payload)

        sources_changed.connect(on_sources)
        try:
            w.enqueue(a / "src" / "a_pkg" / "__init__.py")
            w.enqueue(b / "pyproject.toml")
            w.enqueue(c / "pyproject.toml")
            w.enqueue(c / "src" / "c_pkg" / "__init__.py")
            await asyncio.sleep(0.25)
            if len(received) != 1:
                _fail(f"防抖应合并为一次信号，收到 {len(received)}")
            payload = received[0]
            changes = {change.local_dir: change for change in payload.changes}
            expected = {str(a.resolve()), str(b.resolve()), str(c.resolve())}
            if set(changes) != expected:
                _fail(f"载荷插件目录异常: {set(changes)}")
            if not changes[str(a.resolve())].code_touched:
                _fail(".py 变更应标记 code_touched=True")
            if changes[str(b.resolve())].code_touched:
                _fail("仅 .toml 变更应保持 code_touched=False")
            if not changes[str(c.resolve())].code_touched:
                _fail("同目录 .toml 与 .py 变更应合并为 code_touched=True")
            _ok("多包变更防抖合并为一次信号，载荷正确")
        finally:
            sources_changed.disconnect(on_sources)
            w._running = False
            w._event.set()
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


async def main() -> int:
    tests = [test_local_dir_filter, test_debounce_merge]
    failed = 0
    for test in tests:
        try:
            await test()
        except Exception as e:  # noqa: BLE001
            failed += 1
            import traceback

            print(f"FAIL: {test.__name__}: {e}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
