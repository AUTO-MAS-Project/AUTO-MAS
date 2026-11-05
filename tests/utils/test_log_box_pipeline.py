"""纯文本内核：显式输入、元数据、前后处理和异常传播。"""

import re


from app.utils import log_box
from app.utils.common.log.patterns import MultiLineAggregator


def test_multiline_flush_preserves_caller_metadata_and_instance_isolation():
    pipeline = log_box.LogPipeline()
    pipeline.scope_rules.append(
        MultiLineAggregator(start_re=re.compile("^BEGIN$"), end_re=None)
    )
    pipeline.feed("BEGIN", timestamp=1.0)
    pipeline.feed("内容", timestamp=2.0)
    assert pipeline.finish() == [log_box.LogEntry("普通", "BEGIN\n内容", 2.0)]
    assert log_box.LogPipeline().finish() == []
