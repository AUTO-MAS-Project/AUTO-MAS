"""守住旧日志规则和会话函数表的共同边界。"""

import pytest

from app.utils.common.expression import (
    ExpressionError,
    ExpressionEvaluationError,
    ExpressionFunction,
    compile_expression,
)


def test_legacy_rule_preserves_fallback_and_output_lines():
    expression = compile_expression(
        r'"体力："+$((\d+/\d+)).replace().replace("/","-");$(mail:(\d+))'
    )

    assert expression.extract("120/180") == "体力：120-180"
    assert expression.extract("120/180\nmail:2") == "体力：120-180\n2"


def test_rule_keeps_its_session_function_after_reload():
    def original(text: str, args: list[str | int]) -> str:
        return f"旧：{text}{args[0]} "

    def updated(text: str, args: list[str | int]) -> str:
        return f"新：{text}{args[0]} "

    name = "example-adapter:format"
    rule = r'$((\d+)).example-adapter:format("件").trim()'
    functions: dict[str, ExpressionFunction] = {name: original}
    old_rule = compile_expression(rule, extensions=functions)

    functions[name] = updated
    new_rule = compile_expression(rule, extensions=functions)

    assert old_rule.extract("掉落 3") == "旧：3件"
    assert new_rule.extract("掉落 3") == "新：3件"
    with pytest.raises(ExpressionError):
        compile_expression(rule)
    with pytest.raises(ExpressionError, match=name):
        compile_expression(rule, extensions={})


def test_invalid_extension_call_is_distinct_from_no_match():
    def format_count(text: str, args: list[str | int]) -> str:
        if len(args) != 1 or not isinstance(args[0], int):
            raise ValueError("需要一个整数参数")
        return str(int(text) * args[0])

    expression = compile_expression(
        r'$((\d+)).example-adapter:count("invalid")',
        extensions={"example-adapter:count": format_count},
    )

    assert expression.extract("no count") == ""
    with pytest.raises(ExpressionEvaluationError, match="example-adapter:count"):
        expression.extract("count: 3")


def test_extension_cannot_replace_builtin_function():
    with pytest.raises(ExpressionError, match="trim"):
        compile_expression("$().trim()", extensions={"trim": lambda text, _: text})
