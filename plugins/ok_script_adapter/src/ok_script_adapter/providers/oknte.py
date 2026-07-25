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

from ..common.provider import (
    GameLaunchDescriptor,
    GamePathCandidate,
    OkScriptProvider,
    OkScriptTaskOption,
)


OK_SCRIPT_PROVIDER_PROFILE_ABI_VERSION = 1


OKNTE_PROVIDER = OkScriptProvider(
    resource_name="ok-nte",
    display_name="异环",
    exe_name="ok-nte.exe",
    config_dir="data/apps/ok-nte/working/configs",
    log_file="data/apps/ok-nte/working/logs/ok-script.log",
    pythonw_path="data/apps/ok-nte/python/pythonw.exe",
    track_process_name="pythonw.exe",
    game_process_name="HTGame.exe",
    running_status="OK-NTE 正常运行中",
    fatal_patterns=(
        ("Resolution Error", "OK-NTE 游戏分辨率不符合要求"),
        ("Timed out waiting for game process", "OK-NTE 等待游戏进程超时"),
        ("Timed out waiting for launcher process", "OK-NTE 等待启动器进程超时"),
        ("info_set 错误", "OK-NTE 流程产生错误，请检查游戏状态"),
        ("exception stopped", "OK-NTE 任务执行异常，请检查脚本日志"),
        ("Start task failed", "OK-NTE 启动任务失败"),
        ("Start failed", "OK-NTE 启动失败"),
        ("Traceback", "OK-NTE 运行异常，请检查脚本日志"),
    ),
    success_patterns=(
        "Successfully Executed Task",
        "任务执行完成",
        "task completed",
    ),
    max_task_index=11,
    task_options=(
        OkScriptTaskOption(1, "LauncherTask（启动游戏）"),
        OkScriptTaskOption(2, "DailyTask（日常）"),
        OkScriptTaskOption(3, "CoffeeTask（一咖舍）"),
        OkScriptTaskOption(4, "FishingTask（钓鱼）"),
        OkScriptTaskOption(5, "AnomalyTask（异象界域）"),
        OkScriptTaskOption(6, "RhythmTask（音游）"),
        OkScriptTaskOption(7, "OwnerSelectionTask（业主选拔）"),
        OkScriptTaskOption(8, "AutoHeistTask（粉爪大劫案）"),
        OkScriptTaskOption(9, "DarkTask（暗域任务）"),
        OkScriptTaskOption(10, "BagelAITools（呗果智能体）"),
        OkScriptTaskOption(11, "DiagnosisTask（诊断）"),
    ),
    config_schema_module="ok_script_adapter.providers.oknte_schema",
    config_info_loader="get_all_config_info",
    game_launch=GameLaunchDescriptor(
        mode="launcher",
        launch_kind="executable",
        path_candidates=(
            GamePathCandidate("NTEGame.exe", "launch"),
            GamePathCandidate("NTEGlobalGame.exe", "launch"),
            GamePathCandidate("HTGame.exe", "ready"),
            GamePathCandidate("HTGame.exe", "cleanup"),
        ),
        ready_process_name="HTGame.exe",
        already_running_policy="attach",
        cleanup_policy="always",
        verification="unverified",
    ),
    runtime_verified=False,
    runtime_block_reason=(
        "OK-NTE 当前仅完成配置/schema 适配，真实成功/失败日志尚未实跑确认，"
        "请先完成运行日志验证后再启用调度。"
    ),
)
