import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
from loguru import logger

from app.core import Config


def analyze_maa_logs(logs_directory: Path):
    """
    遍历 logs_directory 下所有 .log 文件，解析公招和掉落信息，并保存为 JSON 文件
    """
    if not logs_directory.exists():
        logger.error(f"目录不存在: {logs_directory}")
        return

    # **检查并删除超期日志**
    clean_old_logs(logs_directory)

    # 设定 JSON 输出路径
    json_output_path = logs_directory / f"{logs_directory.name}.json" if logs_directory.parent.name == "maa_run_history" else logs_directory.parent / f"{logs_directory.name}.json"

    aggregated_data = {
        # "recruit_statistics": defaultdict(int),
        "drop_statistics": defaultdict(lambda: defaultdict(int)),
    }

    log_files = list(logs_directory.rglob("*.log"))
    if not log_files:
        logger.error(f"没有找到 .log 文件: {logs_directory}")
        return

    for log_file in log_files:
        analyze_single_log(log_file, aggregated_data)

    # 生成 JSON 文件
    with open(json_output_path, "w", encoding="utf-8") as json_file:
        json.dump(aggregated_data, json_file, ensure_ascii=False, indent=4)

    logger.info(f"统计完成：{json_output_path}")

def analyze_single_log(log_file_path: Path, aggregated_data):
    """
    解析单个 .log 文件，提取公招结果 & 关卡掉落数据
    """
    # recruit_data = aggregated_data["recruit_statistics"]
    drop_data = aggregated_data["drop_statistics"]

    with open(log_file_path, "r", encoding="utf-8") as f:
        logs = f.readlines()

    # # **公招统计**
    # i = 0
    # while i < len(logs):
    #     if "公招识别结果:" in logs[i]:
    #         tags = []
    #         i += 1
    #         while i < len(logs) and "Tags" not in logs[i]:  # 读取所有公招标签
    #             tags.append(logs[i].strip())
    #             i += 1
    #
    #         if i < len(logs) and "Tags" in logs[i]:  # 确保 Tags 行存在
    #             star_match = re.search(r"(\d+)\s*Tags", logs[i])  # 提取 3,4,5,6 星
    #             if star_match:
    #                 star_level = f"{star_match.group(1)}★"
    #                 recruit_data[star_level] += 1
    #     i += 1

    # **掉落统计**
    current_stage = None
    for i, line in enumerate(logs):
        drop_match = re.search(r"(\d+-\d+) 掉落统计:", line)
        if drop_match:
            current_stage = drop_match.group(1)
            continue

        if current_stage and re.search(r"(\S+)\s*:\s*(\d+)\s*\(\+\d+\)", line):
            item_match = re.findall(r"(\S+)\s*:\s*(\d+)\s*\(\+(\d+)\)", line)
            for item, total, increment in item_match:
                drop_data[current_stage][item] += int(increment)

    logger.info(f"处理完成：{log_file_path}")


def clean_old_logs(logs_directory: Path):
    """
    删除超过用户设定天数的日志文件
    """
    retention_setting = Config.global_config.get(Config.global_config.function_LogRetentionDays)
    retention_days_mapping = {
        "7 天": 7,
        "15 天": 15,
        "30 天": 30,
        "60 天": 60,
        "永不清理": None
    }

    retention_days = retention_days_mapping.get(retention_setting, None)
    if retention_days is None:
        logger.info("🔵 用户设置日志保留时间为【永不清理】，跳过清理")
        return

    cutoff_time = datetime.now() - timedelta(days=retention_days)

    deleted_count = 0
    for log_file in logs_directory.rglob("*.log"):
        file_time = datetime.fromtimestamp(log_file.stat().st_mtime)  # 获取文件的修改时间
        if file_time < cutoff_time:
            try:
                os.remove(log_file)
                deleted_count += 1
                logger.info(f"🗑️ 已删除超期日志: {log_file}")
            except Exception as e:
                logger.error(f"❌ 删除日志失败: {log_file}, 错误: {e}")

    logger.info(f"✅ 清理完成: {deleted_count} 个日志文件")

# # 运行代码
# logs_directory = Path("")
# analyze_maa_logs(logs_directory)
