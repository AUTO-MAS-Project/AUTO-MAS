import base64
import getpass
import tempfile
from contextlib import suppress
from datetime import datetime
from pathlib import Path

from app.utils import process_runner as _utils_process_runner


def build_launch_arguments(exe_path: Path) -> str:
    """拼出引导 powershell 的参数：走 UAC 提权拉起 AUTO-MAS，并等它退出。

    exe_path 不能直接写进 -Command。PowerShell 单引号字符串里的 ' 必须写成 ''，
    命令行和 schtasks 的 XML 又各有一层引号语义，像 C:/Users/O'Brien/AUTO-MAS
    这样的合法安装路径会被其中一层吃掉：设置自启时 schtasks /create 不校验这段
    脚本，注册成功，直到下次登录才失败。改走 -EncodedCommand——脚本按 PowerShell
    自身规则转义后编码成 base64（UTF-16LE），命令行里只剩 [A-Za-z0-9+/=]，
    路径内容既破坏不了解析，也注入不了命令，顺带避开 XML 的 & / < / > 转义。

    -PassThru + WaitForExit 让计划任务的动作与 AUTO-MAS 同生命周期。
    Start-Process 默认在目标进程起来后立刻返回，动作进程（powershell）随即退出，
    MultipleInstancesPolicy=IgnoreNew 就挡不住下一次触发，会再拉起一个实例抢
    同一个监听端口。
    """

    quoted = str(exe_path).replace("'", "''")
    script = (
        f"$p = Start-Process -FilePath '{quoted}' -ArgumentList '--auto-start' "
        "-Verb RunAs -PassThru; if ($null -ne $p) { $p.WaitForExit() }"
    )
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return f"-NoProfile -WindowStyle Hidden -EncodedCommand {encoded}"


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
                        <Arguments>{build_launch_arguments(exe_path)}</Arguments>
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
