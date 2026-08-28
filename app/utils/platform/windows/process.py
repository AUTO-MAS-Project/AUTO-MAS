import os
import subprocess

from ..common.process_runner import ProcessRunner


class WindowsProcessPlatform:
    creation_flags = subprocess.CREATE_NO_WINDOW
    detached_flags = (
        subprocess.CREATE_NEW_PROCESS_GROUP
        | subprocess.DETACHED_PROCESS
        | subprocess.CREATE_NO_WINDOW
    )

    async def open_protocol(self, protocol_url: str) -> None:
        os.startfile(protocol_url)

    async def kill_process(
        self, pid: int, kill_tree: bool = False
    ) -> tuple[bool, str]:
        """用 taskkill 终止进程，返回 (是否成功, 失败原因)。"""

        args = ["taskkill", "/F"]
        if kill_tree:
            args.append("/T")
        args.extend(["/PID", str(pid)])

        result = await ProcessRunner.run_process(*args)
        if result.returncode != 0:
            output = result.stderr.strip() or result.stdout.strip() or "无错误信息"
            return False, f"返回码: {result.returncode}, 原因: {output}"
        return True, ""
