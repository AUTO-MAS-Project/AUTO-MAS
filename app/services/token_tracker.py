#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""
Token 追踪器模块

本模块负责记录和统计 LLM API 调用的 token 使用量。
"""

import json
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.utils import get_logger

logger = get_logger("Token追踪器")


@dataclass
class TokenUsageRecord:
    """Token 使用记录"""
    id: str
    timestamp: str
    provider_name: str
    model_name: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    task_id: str = ""
    
    @classmethod
    def create(
        cls,
        provider_name: str,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
        task_id: str = ""
    ) -> "TokenUsageRecord":
        """创建新的 Token 使用记录"""
        return cls(
            id=str(uuid.uuid4()),
            timestamp=datetime.now().isoformat(),
            provider_name=provider_name,
            model_name=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            task_id=task_id
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TokenUsageRecord":
        """从字典创建实例"""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            provider_name=data.get("provider_name", ""),
            model_name=data.get("model_name", ""),
            input_tokens=data.get("input_tokens", 0),
            output_tokens=data.get("output_tokens", 0),
            total_tokens=data.get("total_tokens", 0),
            task_id=data.get("task_id", "")
        )


@dataclass
class TokenStatistics:
    """Token 统计信息"""
    total_tokens: int = 0
    total_requests: int = 0
    average_tokens_per_request: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    records: List[TokenUsageRecord] = field(default_factory=list)
    
    @classmethod
    def from_records(cls, records: List[TokenUsageRecord]) -> "TokenStatistics":
        """从记录列表计算统计信息"""
        if not records:
            return cls(records=[])
        
        total_tokens = sum(r.total_tokens for r in records)
        total_requests = len(records)
        input_tokens = sum(r.input_tokens for r in records)
        output_tokens = sum(r.output_tokens for r in records)
        average = total_tokens / total_requests if total_requests > 0 else 0.0
        
        return cls(
            total_tokens=total_tokens,
            total_requests=total_requests,
            average_tokens_per_request=average,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            records=records
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（不包含 records 详情）"""
        return {
            "total_tokens": self.total_tokens,
            "total_requests": self.total_requests,
            "average_tokens_per_request": round(self.average_tokens_per_request, 2),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens
        }


class TokenTracker:
    """Token 使用量追踪器"""
    
    def __init__(self, data_path: Optional[Path] = None):
        """初始化 Token 追踪器"""
        self.data_path = data_path or Path.cwd() / "data" / "llm_token_usage.json"
        self._records: List[TokenUsageRecord] = []
        self._initialized = False
    
    async def init(self) -> None:
        """初始化追踪器，加载历史数据"""
        if self._initialized:
            return
        
        logger.info(f"初始化 Token 追踪器，数据路径: {self.data_path}")
        
        try:
            await self._load_data()
            self._initialized = True
            logger.info(f"Token 追踪器初始化成功，已加载 {len(self._records)} 条记录")
        except Exception as e:
            logger.warning(f"Token 数据加载失败，使用空数据: {e}")
            self._records = []
            self._initialized = True
    
    async def _load_data(self) -> None:
        """从文件加载数据"""
        if not self.data_path.exists():
            logger.info("Token 数据文件不存在，将创建新文件")
            self.data_path.parent.mkdir(parents=True, exist_ok=True)
            await self._save_data()
            return
        
        try:
            data = json.loads(self.data_path.read_text(encoding="utf-8"))
            records_data = data.get("records", [])
            self._records = [TokenUsageRecord.from_dict(r) for r in records_data]
        except json.JSONDecodeError as e:
            logger.warning(f"Token 数据文件 JSON 解析失败: {e}")
            raise ValueError(f"数据文件损坏: {e}")
    
    async def _save_data(self) -> None:
        """保存数据到文件"""
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "records": [r.to_dict() for r in self._records]
        }
        
        self.data_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    async def record_usage(
        self,
        provider_name: str,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
        task_id: str = ""
    ) -> TokenUsageRecord:
        """记录 Token 使用量"""
        if not self._initialized:
            await self.init()
        
        logger.info(
            f"记录 Token 使用: {provider_name}/{model_name}, "
            f"输入: {input_tokens}, 输出: {output_tokens}"
        )
        
        record = TokenUsageRecord.create(
            provider_name=provider_name,
            model_name=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            task_id=task_id
        )
        
        self._records.append(record)
        await self._save_data()
        
        logger.debug(f"Token 记录已保存: {record.id}")
        return record
    
    async def get_usage_statistics(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> TokenStatistics:
        """获取指定日期范围的使用统计"""
        if not self._initialized:
            await self.init()
        
        # 过滤指定日期范围内的记录
        filtered_records = []
        for record in self._records:
            try:
                record_time = datetime.fromisoformat(record.timestamp)
                if start_date <= record_time <= end_date:
                    filtered_records.append(record)
            except (ValueError, TypeError):
                # 跳过无效的时间戳
                continue
        
        return TokenStatistics.from_records(filtered_records)
    
    async def get_daily_usage(self) -> TokenStatistics:
        """获取当天使用统计"""
        now = datetime.now()
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        return await self.get_usage_statistics(start_of_day, end_of_day)
    
    async def get_weekly_usage(self) -> TokenStatistics:
        """获取本周使用统计"""
        now = datetime.now()
        # 计算本周一的日期
        days_since_monday = now.weekday()
        start_of_week = (now - timedelta(days=days_since_monday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end_of_week = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        return await self.get_usage_statistics(start_of_week, end_of_week)
    
    async def get_monthly_usage(self) -> TokenStatistics:
        """获取本月使用统计"""
        now = datetime.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_of_month = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        return await self.get_usage_statistics(start_of_month, end_of_month)
    
    async def get_all_records(self) -> List[TokenUsageRecord]:
        """获取所有记录"""
        if not self._initialized:
            await self.init()
        
        return self._records.copy()
    
    async def get_records_by_provider(
        self,
        provider_name: str
    ) -> List[TokenUsageRecord]:
        """按提供商名称获取记录"""
        if not self._initialized:
            await self.init()
        
        return [r for r in self._records if r.provider_name == provider_name]
    
    async def clear_records(self) -> None:
        """
        清空所有记录
        
        警告：此操作不可逆
        """
        logger.warning("清空所有 Token 使用记录")
        self._records = []
        await self._save_data()
    
    async def delete_records_before(self, date: datetime) -> int:
        """删除指定日期之前的记录"""
        if not self._initialized:
            await self.init()
        
        original_count = len(self._records)
        
        self._records = [
            r for r in self._records
            if datetime.fromisoformat(r.timestamp) >= date
        ]
        
        deleted_count = original_count - len(self._records)
        
        if deleted_count > 0:
            await self._save_data()
            logger.info(f"已删除 {deleted_count} 条 Token 记录")
        
        return deleted_count


# 全局 Token 追踪器实例
_token_tracker: Optional[TokenTracker] = None


async def get_token_tracker() -> TokenTracker:
    """获取全局 Token 追踪器实例"""
    global _token_tracker
    if _token_tracker is None:
        _token_tracker = TokenTracker()
        await _token_tracker.init()
    return _token_tracker
