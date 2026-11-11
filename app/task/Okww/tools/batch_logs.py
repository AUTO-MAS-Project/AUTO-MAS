"""根据上游公开进度日志确定批次账号与当前阶段。"""

from collections.abc import Iterable, Iterator

NATIVE_SWITCH_UNSUPPORTED_MESSAGE = (
    "当前ok-ww版本不支持或已移除原生账号切换，请检查ok-ww版本，或改用 MAS 切换账号。"
)


class NativeSwitchUnsupportedError(RuntimeError):
    """上游明确拒绝 MAS 使用的原生切号任务入口。"""


def native_switch_unsupported(line: str) -> bool:
    """只识别任务入口缺失和旧版 CLI 拒绝任务名称，不将执行失败判为不兼容。"""
    return (
        "Task not found: MultiAccountConfigTask" in line
        or "No module named 'src.task.MultiAccountConfigTask'" in line
        or (
            "argument -t/--task:" in line
            and "invalid int value:" in line
            and "MultiAccountConfigTask" in line
        )
    )


def account_log_context(lines: Iterable[str]) -> Iterator[tuple[str | None, str, str]]:
    current = None
    stage = "切换账号"
    for line in lines:
        if "MultiAccountConfigTask:info_set 状态 执行中" in line:
            current = None
            stage = "切换账号"
        marker = "MultiAccountConfigTask:info_set 当前账号 "
        if marker in line:
            current = line.split(marker, 1)[1].strip()
            stage = "切换账号"
        if "MultiAccountConfigTask:" in line and (
            " logged in successfully" in line or "登录成功" in line
        ):
            stage = "账号任务"
        yield current, stage, line
