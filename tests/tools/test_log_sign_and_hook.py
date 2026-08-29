"""成功/失败标志匹配与日志处理钩子的纯逻辑回归测试"""

from app.log_box.hooks import (
    apply_hooks,
    compile_hook,
    load_hooks,
    make_line_hook,
    validate_hook,
)
from app.utils.LogPatternExtractor import (
    SIGN_MODE_REGEX,
    SIGN_MODE_SPLIT,
    compile_log_signs,
)


# ==================== 成功/失败标志匹配 ====================
def test_split_mode_keeps_legacy_substring_semantics():
    """Split 模式保持存量语义：「|」分隔多关键字任一子串命中"""

    matcher = compile_log_signs("任务执行完成|Successfully Executed Task")

    assert matcher.configured is True
    assert matcher.search("2026-08-29 任务执行完成\n") == "任务执行完成"
    assert matcher.search("nothing here") is None


def test_split_mode_ignores_blank_keywords():
    """空配置与全空关键字均视为未配置，不会命中任意日志"""

    assert compile_log_signs("").configured is False
    assert compile_log_signs("").search("anything") is None

    blank = compile_log_signs(" | | ")
    assert blank.configured is False
    assert blank.search("anything") is None


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


def test_unknown_mode_falls_back_to_split():
    """未知模式按 Split 处理，保证存量配置读到旧值时行为不变"""

    matcher = compile_log_signs("a.c", "")

    assert matcher.mode == SIGN_MODE_SPLIT
    assert matcher.search("xxa.cxx") == "a.c"
    assert matcher.search("xxabcxx") is None


# ==================== 日志处理钩子 ====================
def test_drop_rule_discards_matched_line():
    hooks = load_hooks('[{"type":"drop","match":"heartbeat"}]')

    assert apply_hooks("2026-08-29 heartbeat\n", hooks) is None
    assert apply_hooks("2026-08-29 任务执行完成\n", hooks) == "2026-08-29 任务执行完成\n"


def test_replace_rule_rewrites_line_and_keeps_newline():
    hooks = load_hooks(r'[{"type":"replace","match":"token=\\w+","replace":"token=***"}]')

    assert apply_hooks("login token=abc123\n", hooks) == "login token=***\n"


def test_rules_run_in_order_and_replace_results_stack():
    """replace 改写后继续交给后续规则，drop 命中即结束"""

    hooks = load_hooks(
        '[{"type":"replace","match":"WARN","replace":"INFO"},'
        '{"type":"drop","match":"INFO"}]'
    )

    assert apply_hooks("WARN something\n", hooks) is None


def test_disabled_and_invalid_rules_are_skipped():
    """停用规则、非法正则与非法替换模板均跳过，不影响其余规则"""

    hooks = load_hooks(
        '[{"type":"drop","match":"noise","enabled":false},'
        '{"type":"drop","match":"[unclosed"},'
        '{"type":"replace","match":"a","replace":"\\\\1"},'
        '{"type":"drop","match":"progress"}]'
    )

    assert len(hooks) == 1
    assert apply_hooks("noise line\n", hooks) == "noise line\n"
    assert apply_hooks("progress 50%\n", hooks) is None


def test_compile_hook_rejects_unknown_type_and_empty_match():
    assert compile_hook({"type": "unknown", "match": "x"}) is None
    assert compile_hook({"type": "drop", "match": "   "}) is None


def test_non_string_fields_are_skipped_instead_of_raising():
    """规则 JSON 可被手工编辑或分享导入，字段类型不符时按无效规则跳过

    否则 AutoProxy.prepare 编译钩子时就会抛异常，导致整个任务无法启动。
    """
    assert load_hooks('[{"type":"replace","match":"a","replace":123}]') == []
    assert load_hooks('[{"type":"drop","match":123}]') == []
    assert load_hooks('[{"type":123,"match":"a"}]') == []
    assert load_hooks('[{"type":"drop","match":{"a":1}}]') == []
    # 非法条目不影响同一份配置中的其余规则
    hooks = load_hooks('[{"type":"drop","match":123},{"type":"drop","match":"progress"}]')
    assert len(hooks) == 1
    assert apply_hooks("progress 50%\n", hooks) is None


def test_make_line_hook_returns_none_without_usable_rules():
    """无可用规则时返回 None，调用方据此保持与未启用钩子完全一致的行为"""

    assert make_line_hook("") is None
    assert make_line_hook("not json") is None
    assert make_line_hook("[]") is None

    line_hook = make_line_hook('[{"type":"drop","match":"noise"}]')
    assert line_hook is not None
    assert line_hook("noise\n") is None


def test_validate_hook_reports_user_facing_errors():
    assert validate_hook({"type": "drop", "match": "ok"}) is None
    assert validate_hook({"type": "drop", "match": ""}) == "匹配正则为空，该规则不生效"
    assert "匹配正则语法错误" in (validate_hook({"type": "drop", "match": "[a"}) or "")
    assert "未知钩子类型" in (validate_hook({"type": "x", "match": "a"}) or "")
    assert validate_hook({"type": "drop", "match": 123}) == "匹配正则必须为字符串"
    assert (
        validate_hook({"type": "replace", "match": "a", "replace": 123})
        == "替换文本必须为字符串"
    )
    assert "替换文本语法错误" in (
        validate_hook({"type": "replace", "match": "a", "replace": r"\1"}) or ""
    )
