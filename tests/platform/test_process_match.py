"""match_process 只用 process_iter 预取的 proc.info 字段比对, 不再逐进程重新查询。"""

import unittest
from pathlib import Path
from types import SimpleNamespace

from app.utils.platform.common.process import ProcessInfo, match_process


def _proc(pid=1, name="game.exe", exe=r"C:\Game\game.exe", cmdline=None):
    return SimpleNamespace(
        pid=pid, info={"name": name, "exe": exe, "cmdline": cmdline or [exe]}
    )


class MatchProcessTest(unittest.TestCase):
    def test_matches_on_prefetched_info(self):
        target = ProcessInfo(name="game.exe", exe=str(Path(r"C:\Game\game.exe")))
        self.assertTrue(match_process(_proc(), target))

    def test_mismatch_and_denied_fields(self):
        self.assertFalse(match_process(_proc(), ProcessInfo(name="other.exe")))
        self.assertFalse(match_process(_proc(pid=2), ProcessInfo(pid=3)))
        # 无权限读到的 exe 为 None: 按不匹配处理, 不抛异常
        self.assertFalse(
            match_process(_proc(exe=None), ProcessInfo(exe=r"C:\Game\game.exe"))
        )

    def test_cmdline_compares_prefetched_list(self):
        target = ProcessInfo(cmdline=["game.exe", "--x"])
        self.assertTrue(match_process(_proc(cmdline=["game.exe", "--x"]), target))
        self.assertFalse(match_process(_proc(cmdline=["game.exe"]), target))
