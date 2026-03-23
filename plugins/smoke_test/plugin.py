from typing import Any, Callable, Dict


def _safe_to_int(value: Any, default: int = 0) -> int:
	"""将任意值安全转换为整数，常用于读取缓存中的计数器。"""
	try:
		return int(value)
	except Exception:
		return default


class CacheSmokeTestPlugin:
	"""缓存能力验证插件：验证注册、CRUD 与超限清理。"""

	def __init__(self, ctx):
		"""初始化插件上下文与运行参数。"""
		self.ctx = ctx
		self.config = ctx.config or {}
		self.enabled = self.config.get("enable", True)
		self.listen_task_events = self.config.get("listen_task_events", True)
		self.write_count = max(1, int(self.config.get("write_count", 20)))
		self.payload_size = max(8, int(self.config.get("payload_size", 128)))
		self.key_prefix = str(self.config.get("key_prefix", "smoke_item")).strip() or "smoke_item"
		self.clear_before_run = self.config.get("clear_before_run", True)

		self.cache_name = str(self.config.get("cache_name", "smoke_cache")).strip() or "smoke_cache"
		self.limit_mode = str(self.config.get("limit_mode", "count")).strip().lower() or "count"
		self.limit = self.config.get("limit", 8)
		self.limit_unit = str(self.config.get("limit_unit", "kb")).strip().lower() or "kb"

		self.cache = None
		self._handlers: list[tuple[str, Callable[[Dict[str, Any]], None]]] = []

	def _build_payload_text(self, index: int) -> str:
		"""生成指定长度的测试文本。"""
		base = f"index={index};instance={self.ctx.instance_id};"
		padding_len = max(0, self.payload_size - len(base))
		return base + ("x" * padding_len)

	def _register_cache(self):
		"""注册插件缓存并返回缓存对象。"""
		if self.limit_mode not in {"count", "bytes"}:
			raise ValueError("limit_mode 仅支持 count 或 bytes")
		return self.ctx.cache.register(
			cache_name=self.cache_name,
			backend="json",
			limit=self.limit,
			limit_mode=self.limit_mode,
			limit_unit=self.limit_unit,
		)

	def _run_crud_and_cleanup_test(self) -> None:
		"""执行一轮缓存写入、读取、更新、删除和清理验证。"""
		if self.cache is None:
			return

		if self.clear_before_run:
			self.cache.clear()

		self.cache.set("meta", {
			"plugin": "smoke_test",
			"instance": self.ctx.instance_id,
			"mode": self.limit_mode,
			"limit": self.limit,
			"limit_unit": self.limit_unit,
		})

		for i in range(self.write_count):
			self.cache.set(
				f"{self.key_prefix}:{i}",
				{
					"index": i,
					"content": self._build_payload_text(i),
				},
			)

		self.cache.update({
			"batch:0": {"name": "batch", "value": 0},
			"batch:1": {"name": "batch", "value": 1},
		})

		exists_meta = self.cache.exists("meta")
		meta_value = self.cache.get("meta", {})
		deleted = self.cache.delete("batch:0")
		stats = self.cache.stats()

		self.ctx.logger.info(
			"[smoke_test] 缓存测试完成: "
			f"exists_meta={exists_meta}, deleted_batch0={deleted}, "
			f"count={stats.get('count')}, size_bytes={stats.get('size_bytes')}, "
			f"limit_mode={stats.get('limit_mode')}, limit={stats.get('limit')}, "
			f"path={stats.get('path')}"
		)
		self.ctx.logger.info(f"[smoke_test] meta={meta_value}")

	def _bind_task_event_counter(self) -> None:
		"""监听任务事件并将事件计数写入缓存。"""
		if self.cache is None or not self.listen_task_events:
			return

		event_names = ["task.start", "task.progress", "task.log", "task.exit"]

		for event_name in event_names:
			def _handler(payload: Dict[str, Any], _event_name: str = event_name) -> None:
				counter_key = f"counter:{_event_name}"
				current = _safe_to_int(self.cache.get(counter_key, 0), 0)
				self.cache.set(counter_key, current + 1)
				if _event_name in {"task.start", "task.exit"}:
					self.ctx.logger.info(
						f"[smoke_test] 收到 {_event_name}, counter={current + 1}, task_id={payload.get('data', {}).get('task_id', '')}"
					)

			self.ctx.events.on(event_name, _handler)
			self._handlers.append((event_name, _handler))

	def start(self) -> None:
		"""启动插件并执行缓存能力测试。"""
		if not self.enabled:
			self.ctx.logger.info("[smoke_test] 插件已禁用（enable=false）")
			return

		self.cache = self._register_cache()
		self._run_crud_and_cleanup_test()
		self._bind_task_event_counter()
		self.ctx.logger.info("[smoke_test] 缓存测试插件已启动")

	def dispose(self) -> None:
		"""卸载插件并取消事件订阅。"""
		for event_name, handler in self._handlers:
			self.ctx.events.off(event_name, handler)
		self._handlers = []

		if self.cache is not None:
			stats = self.cache.stats()
			self.ctx.logger.info(
				"[smoke_test] 插件卸载，缓存最终统计: "
				f"count={stats.get('count')}, size_bytes={stats.get('size_bytes')}, path={stats.get('path')}"
			)


def setup(ctx):
	"""插件入口：创建缓存测试插件实例并返回卸载函数。"""
	plugin = CacheSmokeTestPlugin(ctx)
	plugin.start()
	return plugin.dispose
