"""成功/失败标志匹配与日志处理钩子的纯逻辑回归测试"""

from app.utils import SIGN_MODE_REGEX, compile_log_signs
from app.utils.common.log_box.hooks import (
    apply_hooks,
    load_hooks,
)


# ==================== 成功/失败标志匹配 ====================
def test_split_mode_keeps_legacy_substring_semantics():
    """Split 模式保持存量语义：「|」分隔多关键字任一子串命中"""

    matcher = compile_log_signs("任务执行完成|Successfully Executed Task")

    assert matcher.configured is True
    assert matcher.search("2026-08-29 任务执行完成\n") == "任务执行完成"
    assert matcher.search("nothing here") is None


def test_regex_mode_returns_matched_text():
    """Regex 模式按整条正则搜索，命中返回匹配片段供状态描述展示"""

    matcher = compile_log_signs(r"任务\d+ 执行完成", SIGN_MODE_REGEX)

    assert matcher.mode == SIGN_MODE_REGEX
    assert matcher.invalid is False
    assert matcher.search("14:03 任务12 执行完成") == "任务12 执行完成"
    assert matcher.search("14:03 任务 执行完成") is None


def test_regex_mode_invalid_pattern_is_configured_but_never_matches():
    """非法正则视为已配置但永不命中：不放宽结束判定，也不中断任务执行"""

    matcher = compile_log_signs("[unclosed", SIGN_MODE_REGEX)

    assert matcher.configured is True
    assert matcher.invalid is True
    assert matcher.search("[unclosed") is None


# ==================== 日志处理钩子 ====================
def test_drop_rule_discards_matched_line():
    hooks = load_hooks('[{"type":"drop","match":"heartbeat"}]')

    assert apply_hooks("2026-08-29 heartbeat\n", hooks) is None
    assert (
        apply_hooks("2026-08-29 任务执行完成\n", hooks) == "2026-08-29 任务执行完成\n"
    )


def test_replace_rule_rewrites_line_and_keeps_newline():
    hooks = load_hooks(
        r'[{"type":"replace","match":"token=\\w+","replace":"token=***"}]'
    )

    assert apply_hooks("login token=abc123\n", hooks) == "login token=***\n"


def test_rules_run_in_order_and_replace_results_stack():
    """replace 改写后继续交给后续规则，drop 命中即结束"""

    hooks = load_hooks(
        '[{"type":"replace","match":"WARN","replace":"INFO"},'
        '{"type":"drop","match":"INFO"}]'
    )

    assert apply_hooks("WARN something\n", hooks) is None
