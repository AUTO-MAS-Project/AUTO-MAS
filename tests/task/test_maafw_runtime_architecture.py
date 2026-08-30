"""项目自带的原生库架构要与本机匹配。

MaaFramework 的项目普遍同时发 win-x86_64 与 win-aarch64 两种包，选错了很难
自己看出来：``Library.open`` 会失败，但原生层报的错定位不到「下载了不匹配的
发行包」。提前判断只是把同一个失败说清楚，**不会挡下任何原本能跑的情况**。

读法取自 mfwa 的 ``tools/runtime/probe.py``：解析 DOS 头的 e_lfanew 偏移、
跳到 PE 签名、读两字节 machine 字段——**不映射也不执行**这个 DLL。

重估记录：mfwa 的 ``tools/runtime``（1,467 行）主体是为「必须加载 DLL 才能
判定版本」服务的子进程隔离与探测协议。本体改用读 PE 内嵌版本串之后那个前提
消失，配套复杂度也不再需要，只有这段架构检查是真缺口，故单独取用。
"""

import tempfile
import unittest
from pathlib import Path

import app.core  # noqa: F401  # 初始化宿主配置

from app.task.MaaFW.tools.core.automas_maafw_runner.environment import (
    describe_runtime_architecture_mismatch,
    detect_pe_architecture,
    host_architecture,
)

DOS_STUB_LEN = 0x40


def make_pe(path: Path, machine: int) -> Path:
    """造一个最小的 PE 文件：MZ 头 + e_lfanew + PE 签名 + machine。"""

    header = bytearray(DOS_STUB_LEN)
    header[0:2] = b"MZ"
    header[0x3C:0x40] = DOS_STUB_LEN.to_bytes(4, "little")
    body = bytes((0x50, 0x45, 0x00, 0x00)) + machine.to_bytes(2, "little")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(header) + body)
    return path


class PeArchitectureTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)

    def test_known_machines_are_named(self) -> None:
        for machine, expected in ((0x8664, "x64"), (0xAA64, "arm64"), (0x014C, "x86")):
            with self.subTest(machine=hex(machine)):
                dll = make_pe(self.base / f"{expected}.dll", machine)
                self.assertEqual(detect_pe_architecture(dll), expected)

    def test_unknown_machine_yields_none(self) -> None:
        self.assertIsNone(detect_pe_architecture(make_pe(self.base / "x.dll", 0x1234)))

    def test_a_non_pe_file_yields_none(self) -> None:
        plain = self.base / "notpe.dll"
        plain.write_bytes(b"this is not a PE file at all")
        self.assertIsNone(detect_pe_architecture(plain))

    def test_a_truncated_file_yields_none(self) -> None:
        stub = self.base / "short.dll"
        stub.write_bytes(b"MZ")
        self.assertIsNone(detect_pe_architecture(stub))

    def test_a_missing_file_yields_none(self) -> None:
        self.assertIsNone(detect_pe_architecture(self.base / "nope.dll"))

    def test_host_architecture_is_one_of_the_known_names(self) -> None:
        self.assertIn(host_architecture(), {"x86", "x64", "arm64"})


class MismatchReportTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)

    def _runtime(self, machine: int) -> Path:
        runtime = self.base / "maafw"
        make_pe(runtime / "MaaFramework.dll", machine)
        return runtime

    def test_matching_architecture_reports_nothing(self) -> None:
        machine = {"x64": 0x8664, "arm64": 0xAA64, "x86": 0x014C}[host_architecture()]
        self.assertIsNone(
            describe_runtime_architecture_mismatch(self._runtime(machine))
        )

    def test_mismatch_names_both_sides(self) -> None:
        other = 0xAA64 if host_architecture() != "arm64" else 0x8664
        message = describe_runtime_architecture_mismatch(self._runtime(other))
        self.assertIsNotNone(message)
        self.assertIn(host_architecture(), message)
        self.assertIn("发行包", message)

    def test_unreadable_architecture_is_not_guessed(self) -> None:
        """读不出来就不猜，交给原生层去报。"""

        runtime = self.base / "unknown"
        (runtime).mkdir()
        (runtime / "MaaFramework.dll").write_bytes(b"garbage")
        self.assertIsNone(describe_runtime_architecture_mismatch(runtime))

    def test_no_runtime_path_reports_nothing(self) -> None:
        self.assertIsNone(describe_runtime_architecture_mismatch(None))


class WiringTest(unittest.TestCase):
    def test_the_check_runs_before_opening_the_library(self) -> None:
        source = (
            Path(__file__).resolve().parents[2]
            / "app/task/MaaFW/tools/core/automas_maafw_runner/runner.py"
        ).read_text(encoding="utf-8")
        check = source.index("describe_runtime_architecture_mismatch(runtime_path)")
        opened = source.index("_ensure_maafw_client_library_mode(runtime_path)")
        self.assertLess(check, opened, "架构检查必须早于 Library.open")


if __name__ == "__main__":
    unittest.main()
