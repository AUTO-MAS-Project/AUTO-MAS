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

from ..common.provider import OkScriptProvider, OkScriptTaskOption


OKWW_PROVIDER = OkScriptProvider(
    resource_name="ok-ww",
    display_name="鸣潮",
    exe_name="ok-ww.exe",
    config_dir="data/apps/ok-ww/working/configs",
    log_file="data/apps/ok-ww/working/logs/ok-script.log",
    pythonw_path="data/apps/ok-ww/python/pythonw.exe",
    track_process_name="pythonw.exe",
    game_process_name="Client-Win64-Shipping.exe",
    running_status="OK-WW 正常运行中",
    fatal_patterns=(
        ("游戏更新成功, 游戏即将重启", "OK-WW 游戏更新后正在重启"),
        ("info_set 错误", "OK-WW 流程产生错误，请检查游戏状态"),
    ),
    success_patterns=(
        "任务执行完成",
        "task completed",
    ),
    max_task_index=8,
    task_options=(
        OkScriptTaskOption(1, "DailyTask（日常）"),
        OkScriptTaskOption(2, "MultiAccountDailyTask（多账号日常）"),
        OkScriptTaskOption(3, "FarmEchoTask（刷声骸）"),
        OkScriptTaskOption(4, "AutoRogueTask（半自动肉鸽）"),
        OkScriptTaskOption(5, "ForgeryTask（凝素领域）"),
        OkScriptTaskOption(6, "NightmareNestTask（梦魇巢穴）"),
        OkScriptTaskOption(7, "SimulationTask（模拟领域）"),
        OkScriptTaskOption(8, "TacetTask（无音区）"),
    ),
    config_schema_module="ok_script_adapter.providers.okww_schema",
    config_info_loader="get_all_config_info",
)
