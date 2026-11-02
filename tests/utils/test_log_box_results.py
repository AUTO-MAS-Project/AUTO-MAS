"""日志结果值拒绝无效的时间元数据。"""

import pytest

from app.utils import LOG_TYPE_NORMAL
from app.utils.common.log_box.results import LogEntry


@pytest.mark.parametrize("timestamp", [float("nan"), float("inf"), True, "07:02"])
def test_entry_rejects_invalid_time(timestamp):
    with pytest.raises(ValueError):
        LogEntry(LOG_TYPE_NORMAL, "邮件", timestamp)
