#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

import hashlib
import json
import math
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Literal


LimitMode = Literal["count", "bytes"]
CacheBackendType = Literal["json", "database"]
LimitUnit = Literal["b", "kb", "mb", "gb"]


_LIMIT_UNIT_MULTIPLIER: Dict[str, int] = {
    "b": 1,
    "kb": 1024,
    "mb": 1024 * 1024,
    "gb": 1024 * 1024 * 1024,
}


def _utc_now_iso() -> str:
    """返回当前 UTC 时间字符串。"""
    return datetime.utcnow().isoformat() + "Z"


def _safe_instance_dir_name(instance_id: str) -> str:
    """将实例名转换为可用于文件夹的安全名称。"""
    raw = str(instance_id or "unknown_instance").strip() or "unknown_instance"
    safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", raw)
    if safe == raw:
        return safe
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:8]
    return f"{safe}_{digest}"


class JsonPluginCache:
    """JSON 缓存实现，提供简洁的键值 CRUD 并支持超限自动清理。"""

    def __init__(
        self,
        *,
        cache_name: str,
        file_path: Path,
        limit: int,
        limit_mode: LimitMode,
    ) -> None:
        self.cache_name = cache_name
        self.file_path = file_path
        self.limit = max(1, int(limit))
        self.limit_mode = limit_mode
        self._lock = threading.RLock()

        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.file_path.exists():
            self._write_store({"items": {}, "updated_at": _utc_now_iso()})

    def _read_store(self) -> Dict[str, Any]:
        """读取缓存数据结构。"""
        try:
            text = self.file_path.read_text(encoding="utf-8")
            payload = json.loads(text)
            if not isinstance(payload, dict):
                return {"items": {}, "updated_at": _utc_now_iso()}
            items = payload.get("items", {})
            if not isinstance(items, dict):
                items = {}
            return {
                "items": items,
                "updated_at": payload.get("updated_at") or _utc_now_iso(),
            }
        except Exception:
            return {"items": {}, "updated_at": _utc_now_iso()}

    def _write_store(self, payload: Dict[str, Any]) -> None:
        """原子写入缓存文件。"""
        payload["updated_at"] = _utc_now_iso()
        temp_path = self.file_path.with_suffix(f"{self.file_path.suffix}.tmp")
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(self.file_path)

    def _cleanup_if_needed(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """按配置阈值执行清理，优先淘汰最久未更新的数据。"""
        items = payload.get("items", {})
        if not isinstance(items, dict) or not items:
            payload["items"] = {}
            return payload

        if self.limit_mode == "count":
            if len(items) <= self.limit:
                return payload
            sorted_keys = sorted(
                items.keys(),
                key=lambda key: str(items.get(key, {}).get("updated_at", "")),
            )
            overflow = len(items) - self.limit
            for key in sorted_keys[:overflow]:
                items.pop(key, None)
            payload["items"] = items
            return payload

        # limit_mode == "bytes"
        while len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > self.limit and items:
            oldest_key = min(
                items.keys(),
                key=lambda key: str(items.get(key, {}).get("updated_at", "")),
            )
            items.pop(oldest_key, None)
            payload["items"] = items
        return payload

    def set(self, key: str, value: Any) -> None:
        """
        写入单个缓存键值并在必要时执行超限清理。

        Args:
            key (str): 缓存键。
            value (Any): 缓存值。

        Returns:
            None: 无返回值。
        """
        safe_key = str(key)
        with self._lock:
            payload = self._read_store()
            items = payload.setdefault("items", {})
            items[safe_key] = {
                "value": value,
                "updated_at": _utc_now_iso(),
            }
            payload["items"] = items
            payload = self._cleanup_if_needed(payload)
            self._write_store(payload)

    def get(self, key: str, default: Any = None) -> Any:
        """
        读取单个缓存键值，不存在时返回默认值。

        Args:
            key (str): 缓存键。
            default (Any): 默认返回值。

        Returns:
            Any: 命中时返回缓存值，未命中时返回 default。
        """
        safe_key = str(key)
        with self._lock:
            payload = self._read_store()
            item = payload.get("items", {}).get(safe_key)
            if not isinstance(item, dict):
                return default
            return item.get("value", default)

    def delete(self, key: str) -> bool:
        """
        删除指定缓存键并返回是否删除成功。

        Args:
            key (str): 缓存键。

        Returns:
            bool: 删除了现有键返回 True，否则返回 False。
        """
        safe_key = str(key)
        with self._lock:
            payload = self._read_store()
            items = payload.get("items", {})
            if safe_key not in items:
                return False
            items.pop(safe_key, None)
            payload["items"] = items
            self._write_store(payload)
            return True

    def exists(self, key: str) -> bool:
        """
        判断指定缓存键是否存在。

        Args:
            key (str): 缓存键。

        Returns:
            bool: 缓存键存在返回 True，否则返回 False。
        """
        safe_key = str(key)
        with self._lock:
            payload = self._read_store()
            return safe_key in payload.get("items", {})

    def update(self, mapping: Dict[str, Any]) -> None:
        """
        批量写入缓存键值并执行一次统一清理。

        Args:
            mapping (Dict[str, Any]): 待更新的键值映射。

        Returns:
            None: 无返回值。

        Raises:
            ValueError: mapping 不是字典时抛出。
        """
        if not isinstance(mapping, dict):
            raise ValueError("mapping 必须是字典")
        with self._lock:
            payload = self._read_store()
            items = payload.setdefault("items", {})
            now = _utc_now_iso()
            for key, value in mapping.items():
                items[str(key)] = {
                    "value": value,
                    "updated_at": now,
                }
            payload["items"] = items
            payload = self._cleanup_if_needed(payload)
            self._write_store(payload)

    def all(self) -> Dict[str, Any]:
        """
        返回当前缓存中的全部键值。

        Returns:
            Dict[str, Any]: 键值映射，不包含内部元数据。
        """
        with self._lock:
            payload = self._read_store()
            result: Dict[str, Any] = {}
            for key, item in payload.get("items", {}).items():
                if isinstance(item, dict) and "value" in item:
                    result[key] = item["value"]
            return result

    def clear(self) -> None:
        """
        清空当前缓存中的所有数据。

        Returns:
            None: 无返回值。
        """
        with self._lock:
            self._write_store({"items": {}, "updated_at": _utc_now_iso()})

    def stats(self) -> Dict[str, Any]:
        """
        返回当前缓存统计信息。

        Returns:
            Dict[str, Any]: 包含缓存名称、限制策略、条目数量和文件大小等统计信息。
        """
        with self._lock:
            payload = self._read_store()
            serialized = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            return {
                "cache": self.cache_name,
                "backend": "json",
                "limit_mode": self.limit_mode,
                "limit": self.limit,
                "count": len(payload.get("items", {})),
                "size_bytes": len(serialized),
                "path": str(self.file_path),
            }


class PluginCacheManager:
    """插件缓存管理器，用于按实例注册和访问缓存。"""

    def __init__(
        self,
        *,
        plugin_name: str,
        instance_id: str,
        data_root: Path,
        logger,
    ) -> None:
        self.plugin_name = plugin_name
        self.instance_id = instance_id
        self.logger = logger
        self._instance_dir = data_root / _safe_instance_dir_name(instance_id) / "plugin_cache"
        # 懒创建：仅在首次真正注册缓存时创建目录，避免未使用缓存的插件产生空目录。
        self._stores: Dict[str, JsonPluginCache] = {}

    def _build_store_key(self, cache_name: str) -> str:
        """构建缓存唯一键（内存键，不做字符清洗）。

        说明：
        - 该 key 仅用于当前进程内 `_stores` 的索引。
        - 推荐调用方直接使用英文规范名，避免同义键的命名歧义。
        - 推荐格式：`[a-zA-Z0-9_.-]+`，示例：`default`、`test_cache`、`runtime.v1`。
        """
        safe_name = str(cache_name or "default").strip() or "default"
        return safe_name

    def _build_json_path(self, cache_name: str) -> Path:
        """计算 JSON 缓存文件路径（文件名会做安全化处理）。

        当前规则：
        - 允许字符：`a-zA-Z0-9_.-`
        - 其余字符（含中文、空格和大多数特殊符号）会被替换为 `_`
        - 清洗后为空时回退为 `default`

        这意味着中文 cache_name 可以使用，但落盘文件名可能被转换成连续下划线，
        可读性较差。若需要稳定可读文件名，建议使用英文规范名。
        """
        safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", cache_name)
        safe_name = safe_name or "default"
        return self._instance_dir / f"{safe_name}.json"

    def _normalize_limit(
        self,
        *,
        limit: int | float | str,
        limit_mode: LimitMode,
        limit_unit: LimitUnit,
    ) -> int:
        """将输入阈值标准化为内部整数值。"""
        if limit_mode == "count":
            try:
                normalized_count = int(limit)
            except Exception as e:
                raise ValueError("count 模式下 limit 必须是正整数") from e
            if normalized_count <= 0:
                raise ValueError("count 模式下 limit 必须大于 0")
            return normalized_count

        unit = str(limit_unit or "b").lower().strip()
        if unit not in _LIMIT_UNIT_MULTIPLIER:
            raise ValueError("limit_unit 仅支持 b/kb/mb/gb")

        amount: float
        if isinstance(limit, str):
            text = limit.strip().lower()
            matched = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*(b|kb|mb|gb)?", text)
            if matched is None:
                raise ValueError("bytes 模式下 limit 格式无效，示例: 1024 / 10mb / 1.5gb")
            amount = float(matched.group(1))
            inline_unit = matched.group(2)
            if inline_unit:
                unit = inline_unit
        else:
            try:
                amount = float(limit)
            except Exception as e:
                raise ValueError("bytes 模式下 limit 必须是数字或带单位字符串") from e

        if amount <= 0:
            raise ValueError("bytes 模式下 limit 必须大于 0")

        normalized_bytes = int(math.ceil(amount * _LIMIT_UNIT_MULTIPLIER[unit]))
        return max(1, normalized_bytes)

    def register(
        self,
        *,
        cache_name: str = "default",
        backend: CacheBackendType = "json",
        limit: int | float | str,
        limit_mode: LimitMode = "count",
        limit_unit: LimitUnit = "b",
    ) -> JsonPluginCache:
        """
        注册缓存并返回可执行 CRUD 操作的缓存实例。

        Args:
            cache_name (str): 缓存名称；在同一实例内需唯一。
                建议使用英文规范名：`[a-zA-Z0-9_.-]+`。
                推荐示例：`auto_mas`, `test_cache`。
                若使用中文或特殊字符，系统会在生成文件名时自动替换为 `_`。
            backend (CacheBackendType): 缓存后端类型，当前仅支持 json。
            limit (int | float | str): 缓存阈值，含义由 limit_mode 决定。
            limit_mode (LimitMode): 阈值模式，count 表示条目数，bytes 表示字节数。
            limit_unit (LimitUnit): 字节单位（b/kb/mb/gb），仅在 bytes 模式生效。

        Returns:
            JsonPluginCache: 已注册或复用的缓存实例。

        Raises:
            ValueError: 在以下场景抛出：
                1) limit_mode 不在 count/bytes 范围内；
                2) limit_unit 不在 b/kb/mb/gb 范围内；
                3) limit 无法按模式解析为有效正值；
                4) 同名缓存已存在且 limit 或 limit_mode 与历史注册参数不一致。
            NotImplementedError: 在以下场景抛出：
                1) backend 不是 json；
                2) 请求了当前版本尚未实现的数据库后端。
        """
        if limit_mode not in {"count", "bytes"}:
            raise ValueError("limit_mode 仅支持 count 或 bytes")
        if str(limit_unit or "").lower().strip() not in _LIMIT_UNIT_MULTIPLIER:
            raise ValueError("limit_unit 仅支持 b/kb/mb/gb")

        normalized_limit = self._normalize_limit(
            limit=limit,
            limit_mode=limit_mode,
            limit_unit=limit_unit,
        )

        key = self._build_store_key(cache_name)
        existing = self._stores.get(key)
        if existing is not None:
            if backend != "json":
                raise NotImplementedError("当前仅支持 json 后端")
            if existing.limit != normalized_limit or existing.limit_mode != limit_mode:
                raise ValueError(
                    "同名缓存已注册且参数不一致，请使用新 cache_name 或保持参数一致"
                )
            return existing

        if backend != "json":
            raise NotImplementedError(
                "数据库后端接口已预留，当前版本仅实现 json。"
            )

        self._instance_dir.mkdir(parents=True, exist_ok=True)

        store = JsonPluginCache(
            cache_name=key,
            file_path=self._build_json_path(key),
            limit=normalized_limit,
            limit_mode=limit_mode,
        )
        self._stores[key] = store
        self.logger.info(
            f"[cache] 已注册缓存: instance={self.instance_id}, cache={key}, backend={backend}, limit_mode={limit_mode}, limit={normalized_limit}"
        )
        return store

    def get_registered(self, cache_name: str = "default") -> JsonPluginCache | None:
        """
        获取已注册缓存实例。

        Args:
            cache_name (str): 缓存名称，默认为 default。

        Returns:
            JsonPluginCache | None: 命中时返回缓存实例，否则返回 None。
        """
        return self._stores.get(self._build_store_key(cache_name))

    def list_registered(self) -> Dict[str, Dict[str, Any]]:
        """
        列出当前实例已注册缓存及其统计信息。

        Returns:
            Dict[str, Dict[str, Any]]: 键为缓存名，值为对应缓存统计信息。
        """
        result: Dict[str, Dict[str, Any]] = {}
        for key, store in self._stores.items():
            result[key] = store.stats()
        return result

    @property
    def instance_cache_dir(self) -> Path:
        """
        获取当前实例的缓存目录路径。

        Returns:
            Path: 当前实例缓存目录。
        """
        return self._instance_dir
