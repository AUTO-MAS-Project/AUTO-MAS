"""重新生成 notify 渠道基线。

    python tests/task/regen_notify_baseline.py

只应在两种情况下运行:
1. 重构开始前, 从未改动的代码上生成初始基线;
2. 有意变更通知行为后, 且已在 commit 说明改了什么、为什么。

平时不要跑——它会把当前行为直接写成「期望行为」, 从而掩盖回归。
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.task.test_notify_channels_parity import BASELINE_PATH, record_all  # noqa: E402


def main() -> None:
    data = record_all()
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    total = sum(
        len(calls)
        for script in data.values()
        for scen in script.values()
        for calls in scen.values()
    )
    print(f"基线已写入 {BASELINE_PATH}")
    print(f"脚本 {len(data)} 个, 录得渠道调用 {total} 次")


if __name__ == "__main__":
    main()
