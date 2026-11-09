"""根据上游公开进度日志确定批次账号与当前阶段。"""

from collections.abc import Iterable, Iterator


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
