"""启动阶段的本地计时，不增加遥测事件。"""

from collections.abc import Iterator
from contextlib import contextmanager
from time import perf_counter

_started_at = perf_counter()

from app.utils.common.log.logger import get_logger  # noqa: E402

logger = get_logger("启动计时")


def startup_mark(name: str) -> None:
    """记录从计时模块加载起的累计耗时。"""
    logger.info(
        f"[启动计时] {name}，累计 {(perf_counter() - _started_at) * 1000:.1f} ms"
    )


@contextmanager
def startup_stage(name: str) -> Iterator[None]:
    """分别测量阶段耗时，嵌套或并行阶段不互相覆盖起点。"""
    started_at = perf_counter()
    logger.info(f"[启动计时] {name} 开始")
    outcome = "完成"
    try:
        yield
    except BaseException:
        outcome = "中断"
        raise
    finally:
        finished_at = perf_counter()
        logger.info(
            f"[启动计时] {name} {outcome}，"
            f"阶段 {(finished_at - started_at) * 1000:.1f} ms，"
            f"累计 {(finished_at - _started_at) * 1000:.1f} ms"
        )
