"""只读探测：拉真实清单算出计划，不下载、不写盘（诊断脚本，非 pytest 入口）。"""

import asyncio
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.gi_updater import create_updater  # noqa: E402
from app.services.gi_updater.common.progress import summarize_size  # noqa: E402


async def probe(region: str, game_dir: str) -> dict:
    """按区服算一次更新计划并回报关键字段。

    Args:
        region: ``cn`` / ``global``。
        game_dir: 一个空目录，代表「未安装」的全量场景。

    Returns:
        可 JSON 序列化的探测结果。
    """
    updater = create_updater(region, game_dir)
    plan = await asyncio.to_thread(updater.check)
    return {
        "region": region,
        "profile": updater.preset.profile_name,
        "state": plan.state.value,
        "kind": plan.kind.value,
        "source": str(plan.source_version or ""),
        "target": str(plan.target_version or ""),
        "target_raw_tag": updater.installer._raw_target_tag(False),
        "matching_fields": list(plan.matching_fields),
        "file_count": plan.file_count,
        "total_size": plan.total_size,
        "total_size_text": summarize_size(plan.total_size),
        "assets_enum": len(plan.assets),
    }


async def main() -> None:
    """对两个区服各跑一次只读探测并打印 JSON。"""
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        for region in ("cn", "global"):
            try:
                results.append(await probe(region, tmp))
            except Exception as error:  # noqa: BLE001
                results.append(
                    {"region": region, "error": f"{type(error).__name__}: {error}"}
                )
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
