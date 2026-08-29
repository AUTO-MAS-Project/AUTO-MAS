import getpass
import tempfile
from contextlib import suppress
from datetime import datetime
from pathlib import Path

from app.utils.platform.common.process_runner import ProcessRunner


class WindowsStartupManager:
    supported = True

    _task_name = "AUTO-MAS_AutoStart"

    async def set_enabled(self, enabled: bool) -> None:
        if enabled:
            await self._create_task()
        elif await self.is_enabled():
            result = await ProcessRunner.run_process(
                "schtasks", "/delete", "/tn", self._task_name, "/f"
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr or result.stdout)

    async def _create_task(self) -> None:
        current_user = getpass.getuser()
        current_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
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
                        <RunLevel>HighestAvailable</RunLevel>
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
                        <Command>{Path.cwd() / 'AUTO-MAS.exe'}</Command>
                        <Arguments>--auto-start</Arguments>
                    </Exec>
                </Actions>
            </Task>"""

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".xml", delete=False, encoding="utf-16"
        ) as f:
            f.write(xml_content)
            xml_file = f.name

        try:
            result = await ProcessRunner.run_process(
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
        result = await ProcessRunner.run_process(
            "schtasks", "/query", "/tn", self._task_name
        )
        return result.returncode == 0
