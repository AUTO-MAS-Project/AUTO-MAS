"""原生 debug 日志会轮转，收尾时不能只按字节偏移去取。

MaaFW 把 ``debug/maafw.log`` 涨到一定大小后整体挪成
``maafw.bak.<时间戳>.log``，再开一个空文件继续写。原先的做法是运行前记下
文件大小、运行后从该偏移读到 EOF；轮转发生后新文件重新长回超过该偏移，
于是拿运行前的偏移去 seek 一个内容毫不相干的文件，运行前半段就此丢失，
切口还落在任意字节位置上。

真机现场（2026-08-30 MaaEnd）：运行 22:55:15 开始，「基建任务」22:56:08 失败，
框架却在 22:58:30 轮转了一次；保存下来的 ``*.maafw.log`` 从 22:58:34 才开始，
失败任务那段全在没人读的 ``maafw.bak.2026.08.30-22.58.30.451.log`` 里。
偏偏长到会触发轮转的运行，正是最需要日志的那些。
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import app.core  # noqa: F401  # 初始化宿主配置

NL = chr(10)


from app.task.MaaFW.tools.embedded.runner_task import (
    _plan_native_debug_log_sources,
    _read_native_debug_log_segment,
    _snapshot_native_debug_log_state,
)


class NativeDebugLogRotationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.debug_dir = Path(self._tmp.name) / "debug"
        self.debug_dir.mkdir()
        self.log_path = self.debug_dir / "maafw.log"

    def _write(self, text: str) -> None:
        self.log_path.write_bytes(text.encode("utf-8"))

    def _append(self, text: str) -> None:
        with self.log_path.open("ab") as handle:
            handle.write(text.encode("utf-8"))

    def _rotate(self, stamp: str) -> Path:
        """模拟 MaaFW 轮转：当前文件整体改名，再开一个空文件。"""

        rotated = self.debug_dir / ("maafw.bak." + stamp + ".log")
        self.log_path.rename(rotated)
        self.log_path.write_bytes(b"")
        return rotated

    def _collect(self, offset: int, known: frozenset) -> str:
        return "".join(
            _read_native_debug_log_segment(path, start)
            for _, path, start in _plan_native_debug_log_sources(
                self.log_path, offset, known
            )
        )

    def test_没有轮转时只读当前文件的增量(self) -> None:
        self._write("运行前" + NL)
        offset, known = _snapshot_native_debug_log_state(self.log_path)

        self._append("本次运行" + NL)

        sources = _plan_native_debug_log_sources(self.log_path, offset, known)
        self.assertEqual(
            [(label, start) for label, _, start in sources],
            [("debug/maafw.log", offset)],
        )
        self.assertEqual(self._collect(offset, known), "本次运行" + NL)

    def test_运行中轮转仍能取回完整日志(self) -> None:
        self._write("运行前" + NL)
        offset, known = _snapshot_native_debug_log_state(self.log_path)

        self._append("前半段" + NL)
        self._rotate("2026.08.30-22.58.30.451")
        # 轮转后新文件重新长回，长度超过运行前的偏移——正是旧写法失效的条件。
        self._append("后半段，比运行前那点内容长得多" + NL)
        self.assertGreater(self.log_path.stat().st_size, offset)

        self.assertEqual(
            self._collect(offset, known),
            "前半段" + NL + "后半段，比运行前那点内容长得多" + NL,
        )

    def test_运行前就存在的轮转文件不重复收录(self) -> None:
        self._write("上一次运行" + NL)
        stale = self._rotate("2026.08.30-22.41.22.463")
        self._write("运行前" + NL)
        offset, known = _snapshot_native_debug_log_state(self.log_path)
        self.assertIn(stale.name, known)

        self._append("本次运行" + NL)

        collected = self._collect(offset, known)
        self.assertEqual(collected, "本次运行" + NL)
        self.assertNotIn("上一次运行", collected)

    def test_多次轮转按时间顺序拼接(self) -> None:
        self._write("运行前" + NL)
        offset, known = _snapshot_native_debug_log_state(self.log_path)

        for index, stamp in enumerate(
            ("2026.08.30-22.58.30.451", "2026.08.30-23.05.11.002"), start=1
        ):
            self._append("第" + str(index) + "段" + NL)
            self._rotate(stamp)
        self._append("第3段" + NL)

        self.assertEqual(
            self._collect(offset, known),
            "第1段" + NL + "第2段" + NL + "第3段" + NL,
        )

    def test_只有首个分片跳过运行前的内容(self) -> None:
        self._write("运行前" + NL)
        offset, known = _snapshot_native_debug_log_state(self.log_path)
        self._rotate("2026.08.30-22.58.30.451")
        self._rotate("2026.08.30-23.05.11.002")

        starts = [
            start
            for _, _, start in _plan_native_debug_log_sources(
                self.log_path, offset, known
            )
        ]
        self.assertEqual(starts, [offset, 0, 0])

    def test_文件缺失时安静返回空(self) -> None:
        self.assertEqual(
            _read_native_debug_log_segment(self.debug_dir / "不存在.log", 0), ""
        )


if __name__ == "__main__":
    unittest.main()
