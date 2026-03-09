from typing import Any, Dict


# def setup(ctx):
#     """最小插件实现."""
#     ctx.logger.info("插件已启动")

#     def _log_event(event_name: str, payload: Any) -> None:
#         ctx.logger.info(
#             f"事件触发={event_name}, 数据包={payload}"
#         )

#     def on_script_start(payload: Dict[str, Any]) -> None:
#         _log_event("script.start", payload)

#     def on_script_exit(payload: Dict[str, Any]) -> None:
#         _log_event("script.exit", payload)

#     def on_script_error(payload: Dict[str, Any]) -> None:
#         _log_event("script.error", payload)

#     ctx.events.on("script.start", on_script_start)
#     ctx.events.on("script.exit", on_script_exit)
#     ctx.events.on("script.error", on_script_error)

#     def dispose():
#         ctx.events.off("script.start", on_script_start)
#         ctx.events.off("script.exit", on_script_exit)
#         ctx.events.off("script.error", on_script_error)
#         ctx.logger.info("插件已关闭")

#     return dispose
