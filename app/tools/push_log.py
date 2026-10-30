"""节点报告兼容入口；公共实现归 log_box 所有，存量调用路径继续可用。"""

from app.log_box.report import (
    PUSH_LOG_MODE_AGGREGATE,
    PUSH_LOG_MODE_OFF,
    PUSH_LOG_MODE_SCATTER,
    build_task_result_text,
    build_user_result_text,
    mirror_report_to_dispatch,
    render_aggregate_push_log,
)

__all__ = [
    "PUSH_LOG_MODE_AGGREGATE",
    "PUSH_LOG_MODE_OFF",
    "PUSH_LOG_MODE_SCATTER",
    "build_task_result_text",
    "build_user_result_text",
    "mirror_report_to_dispatch",
    "render_aggregate_push_log",
]
