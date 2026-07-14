from __future__ import annotations

from app.plugins import ScriptAdapterHooks


class HSRAdapterHooks(ScriptAdapterHooks):
    """HSR 统一编排钩子。"""

    async def check(self, runtime) -> str:
        registry = runtime.get_service("hsr.registry.v1")
        if registry is None:
            return "请启用 HSR 核心插件"

        runtime.script_config = await runtime.build_script_model()
        runtime.user_config = await runtime.storage.load_user_collection()
        snapshot = registry.snapshot(
            script_config=runtime.script_config,
        )
        runtime.extra["hsr_capability_snapshot"] = snapshot
        if not snapshot.available:
            return snapshot.unavailable_reason or "请至少配置一个 HSR 引擎路径"
        if runtime.mode not in snapshot.supported_modes:
            return f"当前 HSR 引擎组合不支持任务模式 {runtime.mode}"
        return "Pass"

    def run_auto_proxy(self, runtime):
        raise RuntimeError("HSR 使用顺序多用户编排器，不通过 BaseAdapterManager 运行")

    def run_manual_review(self, runtime):
        raise RuntimeError("HSR 使用顺序多用户编排器，不通过 BaseAdapterManager 运行")
