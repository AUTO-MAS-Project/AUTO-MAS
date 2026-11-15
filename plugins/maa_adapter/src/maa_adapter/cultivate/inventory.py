import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from auto_mas_core.host.core import Config
from auto_mas_core.host.utils import get_logger

from maa_adapter.config.access import _maa_script_config
from maa_adapter.config.script import MaaConfig
from maa_adapter.constants import MAA_DEPOT_EXCLUDED_ITEM_IDS

logger = get_logger("MAA")


# MAA 的 resource/item_index.json 约 220 KB，编辑页与预览每次都要用；
# 按文件 mtime 缓存解析结果，选择器与名称映射共用这一份
_item_index_cache: dict[Path, tuple[int, dict[str, Any]]] = {}


def _load_item_index(script_config: MaaConfig) -> dict[str, Any]:
    """读 MAA 物品资源表 resource/item_index.json（按文件 mtime 缓存）。"""

    root_path = script_config.Info.Path
    if root_path is None:
        raise ValueError("Path未配置，请检查路径设置")
    path = root_path / "resource" / "item_index.json"
    if not path.exists():
        raise FileNotFoundError(f"未找到 MAA 物品资源: {path}，请更新 MAA 后重试")
    mtime_ns = path.stat().st_mtime_ns
    cached = _item_index_cache.get(path)
    if cached is not None and cached[0] == mtime_ns:
        return cached[1]
    items = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(items, dict):
        raise ValueError(f"MAA 物品资源格式异常: {path}")
    _item_index_cache[path] = (mtime_ns, items)
    return items


async def get_depot_items(script_id: str) -> list[dict[str, str]]:
    """获取 MAA 库存保持物品选项。"""

    items = _load_item_index(_maa_script_config(script_id))
    return [
        {"label": item.get("name") or item_id, "value": item_id}
        for item_id, item in sorted(
            (
                (item_id, item)
                for item_id, item in items.items()
                if item_id.isdigit()
                and item_id not in MAA_DEPOT_EXCLUDED_ITEM_IDS
                and isinstance(item, dict)
            ),
            key=lambda entry: int(entry[0]),
        )
    ]


async def get_depot_stage_candidates(
    script_id: str, item_id: str
) -> list[dict[str, str]]:
    """获取掉落指定材料的关卡候选（按单件期望理智升序，即 xx 理智/件）。

    编排逻辑在 tools.cultivate.service；本函数只做脚本定位与转发，
    保持既有对外契约不变。
    """

    _maa_script_config(script_id)

    from maa_adapter.cultivate import depot_cultivate_service

    return await depot_cultivate_service.stage_candidates(
        config_path=Config.config_path,
        item_id=item_id,
        proxy=Config.proxy,
    )


async def get_depot_stage_candidates_batch(
    *, script_id: str, item_ids: list[str]
) -> dict[str, list[dict[str, str]]]:
    """一次返回编辑页所需材料的关卡候选。"""

    _maa_script_config(script_id)

    from maa_adapter.cultivate import depot_cultivate_service

    return await depot_cultivate_service.stage_candidates_batch(
        config_path=Config.config_path, item_ids=item_ids, proxy=Config.proxy
    )


async def get_depot_inventory(
    script_id: str, user_id: str
) -> tuple[list[dict[str, str]], str | None]:
    """获取当前账号档案的仓库库存（label=数量，value=物品ID）与识别时间。

    查询链只读用户档案（决策 31）：多账号共用 MAA 安装时不再可能读到
    他人数字；档案由运行期识别采集写入（T1.17），缺失 = 该账号未识别。
    """

    _maa_script_config(script_id)

    from maa_adapter.cultivate import depot_cultivate_service

    archive_dir = Path.cwd() / f"data/{uuid.UUID(script_id)}/{uuid.UUID(user_id)}"
    result = await depot_cultivate_service.inventory(maa_data_dir=archive_dir)
    if result is None:
        raise FileNotFoundError(
            f"未找到用户识别档案: {archive_dir / 'DepotData.json'}，"
            "请先运行一次代理完成仓库识别"
        )
    inventory, recognized_at = result
    recognized_iso = (
        datetime.fromtimestamp(recognized_at).isoformat(timespec="seconds")
        if recognized_at > 0
        else None
    )
    items = [
        {"label": str(count), "value": item_id}
        for item_id, count in sorted(inventory.items())
    ]
    return items, recognized_iso


async def _item_names(script_id: str) -> dict[str, str]:
    """MAA 物品 id→名称全量映射（不受选择器排除规则影响，预览展示用）。"""

    items = _load_item_index(_maa_script_config(script_id))
    return {
        item_id: str(entry.get("name") or item_id)
        for item_id, entry in items.items()
        if isinstance(entry, dict)
    }
