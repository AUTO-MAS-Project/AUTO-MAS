"""OK-WW 多账号临时适配：上游提供稳定批次接口后删除此模块。"""

import json
import re
from pathlib import Path
from typing import Any

DAILY_TASK = {"module": "src.task.DailyTask", "class": "DailyTask"}


def normalize_account_key(value: str) -> str:
    """将手机号转换为上游登录列表去星号后的标识，保留邮箱和显示名。"""
    value = value.strip()
    if not value or any(ord(char) < 32 for char in value):
        raise ValueError("账号不能为空或包含控制字符")
    if re.fullmatch(r"1[3-9][0-9]{9}", value):
        return value[:3] + value[-4:]
    if re.fullmatch(r"1[3-9][0-9]\*{4}[0-9]{4}", value):
        return value.replace("*", "")
    if re.fullmatch(r"[0-9+()\-\s]+", value) or value.isdecimal():
        if re.fullmatch(r"1[3-9][0-9]{5}", value):
            return value
        raise ValueError(
            "手机号格式不正确：请填写 11 位大陆手机号、前三位加四个星号加后四位，或对应的 7 位标识；只填后四位无法匹配 ok-ww"
        )
    if "@" in value:
        normalized = value.replace("*", "")
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
            raise ValueError("邮箱格式不正确：请按游戏登录列表显示的邮箱填写")
        return normalized
    if "*" in value:
        raise ValueError(
            "带星号的手机号格式不正确：请按游戏登录列表填写前三位、四个星号和后四位"
        )
    return value


def write_attempt(config_dir: Path, accounts: list[dict[str, Any]]) -> None:
    """下发本轮账号，并清除本次运行目录中的历史结果。

    调用方须先由 manager 快照并恢复整个原生配置目录。先清空结果，
    任何写入失败均中止启动；因此缺失或未更新的结果始终是未知状态。
    """
    if not accounts:
        raise ValueError("没有待运行的 OK-WW 账号")
    identifiers = [account["account_key"] for account in accounts]
    if any(
        not isinstance(key, str) or not key.strip() or key != key.strip() or "*" in key
        for key in identifiers
    ):
        raise ValueError("请填写登录列表中去掉星号后的完整账号标识")
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("OK-WW 多账号标识不能重复")
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "MultiAccountResults.json").write_text("{}\n", encoding="utf-8")
    document = {"accounts": accounts}
    (config_dir / "MultiAccountConfig.json").write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def completed_accounts(config_dir: Path, attempted: set[str]) -> set[str]:
    """读取本轮可确认的成功结果；文件不存在、未知状态不会判成功。"""
    path = config_dir / "MultiAccountResults.json"
    if not path.exists():
        return set()
    document = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(document, dict):
        raise ValueError(f"OK-WW 账号结果格式错误: {path}")
    completed = set()
    for account, result in document.items():
        if not isinstance(result, dict) or result.get("status") not in {
            "success",
            "failed",
            "cancelled",
        }:
            raise ValueError(f"OK-WW 账号结果格式错误: {path}")
        if account in attempted and result["status"] == "success":
            completed.add(account)
    return completed
