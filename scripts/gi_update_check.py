"""只读探测：拉真实清单算出计划，不下载、不写盘（诊断脚本，非 pytest 入口）。

用法：``python scripts/gi_update_check.py [--game gi]``，对所给游戏的两个区服各跑一次。
文件数与体积都从清单实算，不取 ``getBuild`` 返回的统计估算——后者会把一次增量
估成整客户端全量。
"""

import asyncio
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.gi_updater import api
from app.services.gi_updater.common import summarize_size
from app.services.gi_updater.games import create_updater


async def probe(game: str, region: str, game_dir: str) -> dict:
    """按游戏与区服算一次更新计划并回报关键字段。

    Args:
        game_dir: 一个空目录，代表「未安装」的全量场景。

    Returns:
        可 JSON 序列化的探测结果。
    """
    updater = create_updater(game, region, game_dir)
    client = api.new_client()
    try:
        plan = await updater.check(client)
    finally:
        await client.aclose()
    return {
        "game": game,
        "region": region,
        "profile": updater.preset.profile_name,
        "state": plan.state.value,
        "kind": plan.kind.value,
        "source": str(plan.source_version or ""),
        "target": str(plan.target_version or ""),
        "target_raw_tag": updater.version_manager.remote_tag,
        "preload_raw_tag": updater.version_manager.preload_tag,
        "file_count": plan.file_count,
        "patch_count": plan.summary.patch_count,
        "copyover_count": plan.summary.copyover_count,
        "downgraded": plan.summary.downgraded,
        "ready": plan.summary.ready,
        "disk_need": plan.disk_need,
        "total_size": plan.total_size,
        "total_size_text": summarize_size(plan.total_size),
        "removals": len(plan.removals),
        "message": plan.message,
    }


def _game_arg() -> str:
    """取 ``--game`` 的值，缺省为原神。"""
    if "--game" in sys.argv:
        return sys.argv[sys.argv.index("--game") + 1]
    return "gi"


async def main() -> None:
    """对指定游戏的两个区服各跑一次只读探测并打印 JSON。"""
    game = _game_arg()
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        for region in ("cn", "global"):
            try:
                results.append(await probe(game, region, tmp))
            except Exception as error:  # noqa: BLE001
                results.append(
                    {
                        "game": game,
                        "region": region,
                        "error": f"{type(error).__name__}: {error}",
                    }
                )
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
