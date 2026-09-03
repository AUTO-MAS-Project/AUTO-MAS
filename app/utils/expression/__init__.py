"""提取表达式模块

提供表达式解析、编译和求值功能，供日志采集器和未来其他模块复用。

表达式语法::

    $(正则)              正则提取作用域
    "文本"               字面量（支持 \" \\ \n \t 转义）
    +                    同行拼接
    ;                    换行拼接
    $(正则).函数(参数)   函数链处理

示例::

    $(\\d+/\\d+).replace("/","-")+"："+$(邮件：[^\\n]+)

用法::

    from app.utils.expression import compile_expression

    expr = compile_expression('$(\\d+).replace("/",":")')
    result = expr.extract("1/4")  # → "1:4"
"""

from .evaluator import CompiledExpression, compile_expression
from .functions import (
    FUNCTIONS,
    REGISTRY,
    Process,
    apply_function,
    make_process,
    register_process,
)
from .parser import ExpressionError, parse

__all__ = [
    "compile_expression",
    "CompiledExpression",
    "ExpressionError",
    "parse",
    "FUNCTIONS",
    "Process",
    "REGISTRY",
    "register_process",
    "make_process",
    "apply_function",
]
