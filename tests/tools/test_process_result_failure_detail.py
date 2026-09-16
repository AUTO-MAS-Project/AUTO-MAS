"""命令失败文案：returncode / stdout / stderr 一个都不能少。"""

from app.utils.platform.common.process_runner import ProcessResult


def test_failure_detail_includes_everything():
    """雷电 dnconsole.exe 崩溃时的真实形态：返回码非零，stdout 与 stderr 都是空的。"""

    detail = ProcessResult(stdout="", stderr="", returncode=3221225480).failure_detail()

    assert "3221225480" in detail
    assert "stdout=''" in detail
    assert "stderr=''" in detail


def test_failure_detail_quotes_multiline_output():
    """多行输出用 repr 呈现，日志里不会串成好几行。"""

    detail = ProcessResult(stdout="line1\nline2", stderr="错误", returncode=1).failure_detail()

    assert "returncode=1" in detail
    assert "line1\\nline2" in detail
    assert "stderr='错误'" in detail
