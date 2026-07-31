#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""历史记录模块（``HistoryStore``）：统一双文件存储与查询合并。

存储布局::

    history/YYYY-MM-DD/username/HH-MM-SS.json
    history/YYYY-MM-DD/username/HH-MM-SS.log
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from app.utils import get_logger

logger = get_logger("历史记录")


class HistoryStore:
    """全局历史记录存储。"""

    def __init__(self) -> None:
        self.root = Path.cwd() / "history"
        self.root.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        *,
        time: datetime,
        username: str,
        type_key: str,
        status: str,
        message: str,
        logs: str,
        data: dict[str, Any] | None = None,
    ) -> Path:
        """保存一条执行记录；起始时间由调用方传入。"""
        date_path = (
            self.root / time.strftime("%Y-%m-%d") / username / time.strftime("%H-%M-%S")
        )
        date_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "status": status,
            "message": message,
            "type_key": type_key,
            "username": username,
            "data": data or {},
        }
        date_path.with_suffix(".json").write_text(
            json.dumps(record, ensure_ascii=False, indent=4), encoding="utf-8"
        )
        date_path.with_suffix(".log").write_text(logs, encoding="utf-8")
        logger.info(f"已保存历史记录: {date_path}")
        return date_path.with_suffix(".json")

    def search(
        self,
        *,
        start_date: str,
        end_date: str,
        mode: Literal["DAILY", "WEEKLY", "MONTHLY"] = "DAILY",
    ) -> dict[str, dict[str, dict[str, Any]]]:
        """按日期范围查询；按 mode 分组、按用户聚合并合并 ``data``。"""
        result: dict[str, dict[str, dict[str, Any]]] = {}

        conflicted_by_bucket: dict[tuple[str, str], set[str]] = {}

        def merge_value(
            conflicted: set[str], key_chain: str, old: Any, new: Any
        ) -> Any:
            if key_chain in conflicted:
                return old
            if isinstance(old, (int, float)) and isinstance(new, (int, float)):
                return old + new
            if isinstance(old, dict) and isinstance(new, dict):
                merged = dict(old)
                for k, v in new.items():
                    sk = f"{key_chain}.{k}"
                    if k in merged:
                        if sk in conflicted:
                            continue
                        merged[k] = merge_value(conflicted, sk, merged[k], v)
                    else:
                        merged[k] = v
                return merged
            conflicted.add(key_chain)
            return {"__error__": -1}

        for date_dir in sorted(self.root.iterdir()):
            if not date_dir.is_dir():
                continue
            name = date_dir.name
            if name < start_date or name > end_date:
                continue
            try:
                d = datetime.strptime(name, "%Y-%m-%d")
            except ValueError:
                logger.warning(f"非日期格式的目录: {date_dir}")
                continue
            if mode == "DAILY":
                date_key = name
            elif mode == "WEEKLY":
                date_key = d.strftime("%G-W%V")
            elif mode == "MONTHLY":
                date_key = d.strftime("%Y-%m")

            for user_dir in date_dir.iterdir():
                if not user_dir.is_dir():
                    continue
                bucket = result.setdefault(date_key, {}).setdefault(
                    user_dir.name,
                    {"index": [], "data": {}, "error_info": {}},
                )
                conflicted = conflicted_by_bucket.setdefault(
                    (date_key, user_dir.name), set()
                )
                for json_path in sorted(user_dir.glob("*.json")):
                    try:
                        rec = json.loads(json_path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        continue
                    date_label = datetime.strptime(
                        f"{name} {json_path.stem}", "%Y-%m-%d %H-%M-%S"
                    ).strftime("%Y-%m-%d %H:%M:%S")
                    ok = rec.get("status") == "success"
                    bucket["index"].append(
                        {
                            "date": date_label,
                            "status": "DONE" if ok else "ERROR",
                            "jsonFile": str(json_path),
                        }
                    )
                    for k, v in (rec.get("data") or {}).items():
                        bucket["data"][k] = (
                            merge_value(conflicted, k, bucket["data"][k], v)
                            if k in bucket["data"]
                            else v
                        )
                    if not ok:
                        bucket["error_info"][date_label] = str(rec.get("message") or "")

        return {
            k: v for k, v in sorted(result.items(), key=lambda x: x[0], reverse=True)
        }

    def get_detail(self, json_path: str | Path) -> dict[str, Any]:
        """读取单条记录详情（含日志）；路径须落在历史根目录内。"""
        p = Path(json_path).resolve()
        try:
            p.relative_to(self.root.resolve())
        except ValueError as exc:
            raise ValueError("不允许访问历史目录外文件") from exc
        out = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        log_path = p.with_suffix(".log")
        out["log_content"] = (
            log_path.read_text(encoding="utf-8") if log_path.exists() else ""
        )
        return out

    def get_overview(self) -> dict[str, dict[str, Any]]:
        """今日代理概览（首页用）。"""
        today = datetime.now().strftime("%Y-%m-%d")
        overview: dict[str, dict[str, Any]] = {}
        for users in self.search(
            start_date=today, end_date=today, mode="DAILY"
        ).values():
            for username, info in users.items():
                index = info.get("index") or []
                overview[username] = {
                    "LastProxyDate": index[-1]["date"] if index else "暂无代理数据",
                    "ProxyTimes": len(index),
                    "ErrorTimes": len(info.get("error_info") or {}),
                    "ErrorInfo": info.get("error_info") or {},
                }
        return overview

    def clean(self, retention_days: int | None = None) -> int:
        """删除超过保留天数的日期目录；``<=0`` 表示永久保留。"""
        if retention_days is None:
            from app.core.config import Config

            retention_days = int(Config.setting.function.history_retention_time)
        if retention_days <= 0:
            logger.info("历史记录永久保留, 跳过清理")
            return 0

        cutoff = datetime.now().date() - timedelta(days=retention_days)
        count = 0
        for date_dir in list(self.root.iterdir()):
            if not date_dir.is_dir():
                continue
            try:
                folder_date = datetime.strptime(date_dir.name, "%Y-%m-%d").date()
            except ValueError:
                logger.warning(f"非日期格式的目录: {date_dir}")
                continue
            if folder_date < cutoff:
                shutil.rmtree(date_dir, ignore_errors=True)
                count += 1
                logger.debug(f"已删除超期日志目录: {date_dir}")
        logger.success(f"历史清理完成: {count} 个日期目录")
        return count


history_store = HistoryStore()
