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
        """写入单个键值，必要时触发超限清理。"""
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
        """读取单个键值，不存在时返回默认值。"""
        safe_key = str(key)
        with self._lock:
            payload = self._read_store()
            item = payload.get("items", {}).get(safe_key)
            if not isinstance(item, dict):
                return default
            return item.get("value", default)

    def delete(self, key: str) -> bool:
        """删除键值并返回是否实际删除。"""
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
        """判断键是否存在。"""
        safe_key = str(key)
        with self._lock:
            payload = self._read_store()
            return safe_key in payload.get("items", {})

    def update(self, mapping: Dict[str, Any]) -> None:
        """批量更新键值并执行一次清理。"""
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
        """返回当前缓存中的全部键值。"""
        with self._lock:
            payload = self._read_store()
            result: Dict[str, Any] = {}
            for key, item in payload.get("items", {}).items():
                if isinstance(item, dict) and "value" in item:
                    result[key] = item["value"]
            return result

    def clear(self) -> None:
        """清空缓存数据。"""
        with self._lock:
            self._write_store({"items": {}, "updated_at": _utc_now_iso()})

    def stats(self) -> Dict[str, Any]:
        """返回缓存统计信息。"""
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
        self._instance_dir.mkdir(parents=True, exist_ok=True)
        self._stores: Dict[str, JsonPluginCache] = {}

    def _build_store_key(self, cache_name: str) -> str:
        """构建缓存唯一键。"""
        safe_name = str(cache_name or "default").strip() or "default"
        return safe_name

    def _build_json_path(self, cache_name: str) -> Path:
        """计算 JSON 缓存文件路径。"""
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
        """注册缓存并返回可直接 CRUD 的缓存实例。

        参数说明：
        - cache_name: 缓存名称；同实例内唯一。
        - backend: 缓存后端类型，当前支持 json。
        - limit: 必填阈值（数量或字节）。
        - limit_mode: 阈值模式，count 表示条目数，bytes 表示字节大小。
        - limit_unit: 字节单位（b/kb/mb/gb），仅在 bytes 模式生效。
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
        """获取已注册缓存，若不存在返回 None。"""
        return self._stores.get(self._build_store_key(cache_name))

    def list_registered(self) -> Dict[str, Dict[str, Any]]:
        """列出当前实例已注册缓存及其统计信息。"""
        result: Dict[str, Dict[str, Any]] = {}
        for key, store in self._stores.items():
            result[key] = store.stats()
        return result

    @property
    def instance_cache_dir(self) -> Path:
        """返回当前实例缓存目录路径。"""
        return self._instance_dir
