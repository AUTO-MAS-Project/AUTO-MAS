import psutil
import pytest

from app.utils.common.process.manager import ProcessInfo, ProcessManager


@pytest.mark.asyncio
@pytest.mark.parametrize("other_attributes", [["name"], ["exe", "create_time"]])
async def test_search_process_survives_an_overlapping_scan(
    monkeypatch, other_attributes
):
    process = psutil.Process()
    process_iter = psutil.process_iter
    # 先填充 psutil 缓存，确保两次枚举取到同一个 Process 对象。
    list(process_iter())

    def scan_with_overlap(attrs=None):
        candidate = next(
            proc for proc in process_iter(attrs) if proc.pid == process.pid
        )
        # 在查询方读取字段前，插入另一轮只取部分字段的真实扫描。
        next(proc for proc in process_iter(other_attributes) if proc.pid == process.pid)
        yield candidate

    monkeypatch.setattr(psutil, "process_iter", scan_with_overlap)
    manager = ProcessManager()

    await manager.search_process(
        ProcessInfo(pid=process.pid, name=process.name(), exe=process.exe()),
        timeout_seconds=3,
        min_create_time=process.create_time(),
        owned=False,
    )

    assert manager.main_pid == process.pid
