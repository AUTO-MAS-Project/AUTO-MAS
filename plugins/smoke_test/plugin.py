from typing import Any, Dict


def _to_bool(value: Any, default: bool = False) -> bool:
	if isinstance(value, bool):
		return value
	if isinstance(value, str):
		text = value.strip().lower()
		if text in {"1", "true", "yes", "on"}:
			return True
		if text in {"0", "false", "no", "off"}:
			return False
	return default


def _to_int(value: Any, default: int = 15) -> int:
	try:
		return int(value)
	except Exception:
		return default


def setup(ctx):
	"""M3 运行时能力验证插件。"""
	config = ctx.config or {}

	if not _to_bool(config.get("enable", True), True):
		ctx.logger.info("smoke_test 已禁用，跳过运行")
		return lambda: None

	runtime = getattr(ctx, "runtime", None)
	runtime_info = None

	if runtime is not None and _to_bool(config.get("runtime_check_on_start", True), True):
		try:
			runtime_info = runtime.get_runtime_info(force_refresh=True)
			interpreter_check = runtime_info.get("interpreter_check", {})
			ctx.logger.info(
				"runtime 信息: "
				f"selected={runtime_info.get('selected_python', '')}, "
				f"ok={interpreter_check.get('ok', False)}, "
				f"version={interpreter_check.get('version', '')}"
			)
		except Exception as e:
			ctx.logger.error(f"获取 runtime 信息失败: {e}")

	if runtime is not None and _to_bool(config.get("run_runtime_probe", True), True):
		probe_code = str(
			config.get(
				"runtime_probe_code",
				"import sys,platform; print(sys.executable); print(platform.platform())",
			)
		)
		python_executable = str(config.get("python_executable", "")).strip() or None
		timeout_seconds = _to_int(config.get("python_timeout_seconds", 15), 15)
		try:
			probe_result = runtime.run_python_snippet(
				probe_code,
				python_executable=python_executable,
				timeout_seconds=timeout_seconds,
			)
			ctx.logger.info(
				"runtime 探针结果: "
				f"ok={probe_result.get('ok', False)}, "
				f"returncode={probe_result.get('returncode', -1)}"
			)
			if _to_bool(config.get("log_probe_stdout", True), True):
				stdout = str(probe_result.get("stdout", "")).strip()
				if stdout:
					ctx.logger.info(f"runtime 探针 stdout:\n{stdout}")
		except Exception as e:
			ctx.logger.error(f"执行 runtime 探针失败: {e}")

	def _log_event(event_name: str, payload: Any) -> None:
		message = str(config.get("message", "smoke_test 事件触发"))
		include_payload = _to_bool(config.get("include_payload", True), True)
		if include_payload:
			ctx.logger.info(f"{message} | event={event_name} | payload={payload}")
		else:
			ctx.logger.info(f"{message} | event={event_name}")

		if _to_bool(config.get("include_runtime_in_event_log", False), False) and runtime_info:
			ctx.logger.info(
				"event runtime: "
				f"selected={runtime_info.get('selected_python', '')}, "
				f"ok={runtime_info.get('interpreter_check', {}).get('ok', False)}"
			)

	def on_script_start(payload: Dict[str, Any]) -> None:
		_log_event("script.start", payload)

	def on_script_success(payload: Dict[str, Any]) -> None:
		_log_event("script.success", payload)

	def on_script_error(payload: Dict[str, Any]) -> None:
		_log_event("script.error", payload)

	def on_script_cancelled(payload: Dict[str, Any]) -> None:
		_log_event("script.cancelled", payload)

	ctx.events.on("script.start", on_script_start)
	ctx.events.on("script.success", on_script_success)
	ctx.events.on("script.error", on_script_error)
	ctx.events.on("script.cancelled", on_script_cancelled)

	ctx.logger.info("smoke_test 插件已启动")

	def dispose():
		ctx.events.off("script.start", on_script_start)
		ctx.events.off("script.success", on_script_success)
		ctx.events.off("script.error", on_script_error)
		ctx.events.off("script.cancelled", on_script_cancelled)
		ctx.logger.info("smoke_test 插件已关闭")

	return dispose
