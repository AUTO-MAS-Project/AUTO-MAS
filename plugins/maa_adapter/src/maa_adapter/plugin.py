"""明日方舟 MAA 脚本适配。"""

from __future__ import annotations

import json
from typing import Any, Awaitable

from auto_mas_core import (
    EmulatorExpect,
    ScriptAdapterPlugin,
    ScriptEntry,
    ScriptTypeDecl,
    TaskMode,
    plugin_route,
)
from auto_mas_core.utils import get_logger

from .api import service as maa_api
from .task.expander import MaaExpander
from .schema import MaaPlan, MaaScript, MaaUser

logger = get_logger("MAA 接口")


def maa_expect(entry: ScriptEntry) -> EmulatorExpect | None:
    """MAA 截图识别需要固定分辨率与关闭动态调帧等。"""

    return EmulatorExpect(
        width=1280,
        height=720,
        dpi=None,
        keep_alive=True,
        high_frame_rate=False,
        vertical_sync=False,
        display_fps=False,
        auto_rotate=False,
        vram_strategy=("auto", "perf"),
    )


class Plugin(ScriptAdapterPlugin):
    """登记 MAA 脚本 / 用户 / 计划表。展示名在包内 i18n。"""

    script_type_key = "maa"
    decl = ScriptTypeDecl(
        entry_type=MaaScript,
        user_type=MaaUser,
        expander_class=MaaExpander,
        plan_entry_type=MaaPlan,
        supported_modes=(TaskMode.AUTO_PROXY, TaskMode.SCRIPT_CONFIG),
        expect_builder=maa_expect,
    )

    @plugin_route("/user/infrastructure", methods=["POST"])
    async def import_infrastructure(self, request):
        b = await _body(request)
        return await _out(
            maa_api.set_infrastructure(b["scriptId"], b["userId"], b["jsonFile"])
        )

    @plugin_route("/user/infrastructure/plan-select", methods=["POST"])
    async def set_infrast_plan_select(self, request):
        b = await _body(request)
        return await _out(
            maa_api.set_infrast_plan_select(b["scriptId"], b["userId"], b["index"])
        )

    @plugin_route("/user/infrastructure/plan-select/get", methods=["POST"])
    async def get_infrast_plan_select(self, request):
        b = await _body(request)
        return await _out(maa_api.get_infrast_plan_select(b["scriptId"], b["userId"]))

    @plugin_route("/user/combox/infrastructure", methods=["POST"])
    async def user_combox_infrastructure(self, request):
        b = await _body(request)
        return await _out(
            maa_api.get_user_combox_infrastructure(b["scriptId"], b["userId"])
        )

    @plugin_route("/depot/items", methods=["POST"])
    async def depot_items(self, request):
        b = await _body(request)
        return await _out(maa_api.get_depot_items(b["scriptId"]))

    @plugin_route("/depot/stage/candidates", methods=["POST"])
    async def depot_stage_candidates(self, request):
        b = await _body(request)
        return await _out(maa_api.get_depot_stage_candidates(b["scriptId"], b["itemId"]))

    @plugin_route("/depot/inventory", methods=["POST"])
    async def depot_inventory(self, request):
        b = await _body(request)
        out = await _out(maa_api.get_depot_inventory(b["scriptId"], b["userId"]))
        if out["code"] == 200:
            out["data"], out["recognizedAt"] = out["data"]
        return out

    @plugin_route("/cultivate/skland/bindings", methods=["POST"])
    async def cultivate_skland_bindings(self):
        return await _out(maa_api.get_cultivate_skland_bindings())

    @plugin_route("/cultivate/operators", methods=["POST"])
    async def cultivate_operators(self, request):
        b = await _body(request)
        return await _out(maa_api.get_cultivate_operators(b["scriptId"], b["userId"]))

    @plugin_route("/cultivate/preview", methods=["POST"])
    async def cultivate_preview(self, request):
        b = await _body(request)
        targets = b.get("targets", "[]")
        if not isinstance(targets, str):
            targets = json.dumps(targets, ensure_ascii=False)
        return await _out(
            maa_api.get_cultivate_preview(b["scriptId"], b["userId"], targets)
        )


async def _body(request) -> dict:
    """网关只注入 Request；空体按 {} 处理。"""

    raw = await request.body()
    return json.loads(raw) if raw else {}


async def _out(call: Awaitable[Any]) -> dict[str, Any]:
    """套主程序 OutBase 外壳，异常转 code=500 而非裸 HTTP 500。"""

    try:
        data = await call
    except Exception as e:
        logger.opt(exception=True).warning(f"MAA 接口失败: {type(e).__name__}: {e}")
        return {"code": 500, "status": "error", "message": f"{type(e).__name__}: {e}"}
    return {"code": 200, "status": "success", "message": "操作成功", "data": data}
