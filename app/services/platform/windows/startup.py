import getpass
import tempfile
from contextlib import suppress
from datetime import datetime
from pathlib import Path

from app.utils import process_runner as _utils_process_runner


class WindowsStartupManager:
    supported = True

    _task_name = "AUTO-MAS_AutoStart"

    async def set_enabled(self, enabled: bool) -> None:
        if enabled:
            await self._create_task()
        elif await self.is_enabled():
            result = await _utils_process_runner.ProcessRunner.run_process(
                "schtasks", "/delete", "/tn", self._task_name, "/f"
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr or result.stdout)

    async def _create_task(self) -> None:
        current_user = getpass.getuser()
        current_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        # 计划任务本身不提权（否则令牌会带 TokenMandatoryPolicy=3，MuMu 6.8.8 会因此自降
        # 权限、拉不起 MuMuNxMain），改由引导脚本走 UAC 提权，拿到正常的管理员令牌
        exe_path = Path.cwd() / "AUTO-MAS.exe"
        xml_content = f"""<?xml version="1.0" encoding="UTF-16"?>
            <Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
                <RegistrationInfo>
                    <Date>{current_time}</Date>
                    <Author>{current_user}</Author>
                    <Description>AUTO-MAS自启动服务</Description>
                    <URI>\\AUTO-MAS_AutoStart</URI>
                </RegistrationInfo>
                <Triggers>
                    <LogonTrigger>
                        <StartBoundary>{current_time}</StartBoundary>
                        <Enabled>true</Enabled>
                    </LogonTrigger>
                </Triggers>
                <Principals>
                    <Principal id="Author">
                        <LogonType>InteractiveToken</LogonType>
                        <RunLevel>LeastPrivilege</RunLevel>
                    </Principal>
                </Principals>
                <Settings>
                    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
                    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
                    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
                    <AllowHardTerminate>false</AllowHardTerminate>
                    <StartWhenAvailable>true</StartWhenAvailable>
                    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
                    <IdleSettings>
                        <StopOnIdleEnd>false</StopOnIdleEnd>
                        <RestartOnIdle>false</RestartOnIdle>
                    </IdleSettings>
                    <AllowStartOnDemand>true</AllowStartOnDemand>
                    <Enabled>true</Enabled>
                    <Hidden>false</Hidden>
                    <RunOnlyIfIdle>false</RunOnlyIfIdle>
                    <WakeToRun>false</WakeToRun>
                    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
                    <Priority>7</Priority>
                </Settings>
                <Actions Context="Author">
                    <Exec>
                        <Command>powershell.exe</Command>
                        <Arguments>-NoProfile -WindowStyle Hidden -Command "Start-Process -FilePath '{exe_path}' -ArgumentList '--auto-start' -Verb RunAs"</Arguments>
                    </Exec>
                </Actions>
            </Task>"""

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".xml", delete=False, encoding="utf-16"
        ) as f:
            f.write(xml_content)
            xml_file = f.name

        try:
            result = await _utils_process_runner.ProcessRunner.run_process(
                "schtasks",
                "/create",
                "/tn",
                self._task_name,
                "/xml",
                xml_file,
                "/f",
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr or result.stdout)
        finally:
            with suppress(Exception):
                Path(xml_file).unlink()

    async def is_enabled(self) -> bool:
        result = await _utils_process_runner.ProcessRunner.run_process(
            "schtasks", "/query", "/tn", self._task_name
        )
        return result.returncode == 0
