#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

from app.task.Ok.common.provider import (
    OkScriptAccountConfig,
    OkScriptProvider,
    OkScriptTaskOption,
)
from app.task.Ok.providers.okef_report import OkefDailySummaryReportHandler


OKEF_PROVIDER = OkScriptProvider(
    resource_name="ok-ef",
    display_name="终末地",
    exe_name="ok-ef.exe",
    config_dir="data/apps/ok-ef/working/configs",
    log_file="data/apps/ok-ef/working/logs/ok-script.log",
    pythonw_path="data/apps/ok-ef/python/pythonw.exe",
    track_process_name="pythonw.exe",
    game_process_name="Endfield.exe",
    running_status="OK-EF 正常运行中",
    fatal_patterns=(
        ("info_set 错误", "OK-EF 流程产生错误，请检查游戏状态"),
        ("exception stopped", "OK-EF 任务执行异常，请检查脚本日志"),
        ("Start task failed", "OK-EF 启动任务失败"),
        ("Start failed", "OK-EF 启动失败"),
        ("Traceback", "OK-EF 运行异常，请检查脚本日志"),
    ),
    success_patterns=(
        "Successfully Executed Task, Exiting Game and App!",
    ),
    max_task_index=11,
    task_options=(
        OkScriptTaskOption(1, "DailyTask（日常）"),
        OkScriptTaskOption(2, "TakeDeliveryTask（收取派送）"),
        OkScriptTaskOption(3, "WarehouseTransferTask（仓库转运）"),
        OkScriptTaskOption(4, "DeliveryTask（派送）"),
        OkScriptTaskOption(5, "BattleTask（战斗）"),
        OkScriptTaskOption(6, "DemoDrawTask（抽卡演示）"),
        OkScriptTaskOption(7, "Test（测试）"),
        OkScriptTaskOption(8, "YingTuoTask（莺鸵）"),
        OkScriptTaskOption(9, "TestStartGame（启动游戏测试）"),
        OkScriptTaskOption(10, "RealtimeDetectTask（实时识别）"),
        OkScriptTaskOption(11, "DiagnosisTask（诊断）"),
    ),
    config_schema_module="app.task.Okef.config_schema",
    config_info_loader="get_config_info_from_dir",
    config_info_uses_directory=True,
    account_config=OkScriptAccountConfig(
        enabled_key="多账户模式",
        independent_key="多账户独立配置",
        account_list_key="账号列表",
    ),
    report_handler_factory=OkefDailySummaryReportHandler,
)
