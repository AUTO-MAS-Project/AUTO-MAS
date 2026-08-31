"""日志类型常量

与推送策略的普通/失败语义保持一致（引用 LogPatternExtractor 的
LOG_TYPE_NORMAL / LOG_TYPE_ERROR），保证 log_box 结果可直接进推送报告。
"""

from app.utils.LogPatternExtractor import LOG_TYPE_ERROR, LOG_TYPE_NORMAL


class LogType:
    """日志类型

    - NORMAL = 普通：任何推送报告均包含；
    - FAIL = 失败：仅在存在未完成用户的报告中纳入。
    """

    NORMAL = LOG_TYPE_NORMAL  # "普通"
    FAIL = LOG_TYPE_ERROR  # "失败"
