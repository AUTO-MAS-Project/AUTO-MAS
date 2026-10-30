#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""装配 MAS 自定义脚本执行器，调度器和各专项共用同一入口。"""

from app.services.custom_script import CustomScriptExecutor
from app.utils import ProcessRunner, process_platform

execute_script_task = CustomScriptExecutor(
    run_process=ProcessRunner.run_process,
    open_file=process_platform.platform_process.open_protocol,
).execute
