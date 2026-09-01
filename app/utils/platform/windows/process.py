import os
import subprocess

from ..common.process_runner import ProcessRunner


class WindowsProcessPlatform:
    # 后端被 AUTO-MAS-Runtime 用 Job Object 监督（KILL_ON_JOB_CLOSE）时，这两
    # 组标志启动的都是不该随后端一起被回收的进程——模拟器/游戏/外部脚本，以及
    # 自更新时接替当前进程的安装程序——所以都叠加 CREATE_BREAKAWAY_FROM_JOB
    # 显式脱离。注意 DETACHED_PROCESS 本身不会让子进程脱离 Job，必须靠这个
    # 标志才行，不要以为 DETACHED_PROCESS 已经处理了这件事。
    #
    # 父进程若恰好处在一个不允许 breakaway 的 Job 里，带这个标志的
    # CreateProcess 会以 ERROR_ACCESS_DENIED（WinError 5）失败；
    # ProcessManager.open_process 对此有去掉该位重试一次的兜底。
    creation_flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_BREAKAWAY_FROM_JOB
    detached_flags = (
        subprocess.CREATE_NEW_PROCESS_GROUP
        | subprocess.DETACHED_PROCESS
        | subprocess.CREATE_NO_WINDOW
        | subprocess.CREATE_BREAKAWAY_FROM_JOB
    )

    async def open_protocol(self, protocol_url: str) -> None:
        os.startfile(protocol_url)

    async def kill_process(self, pid: int, kill_tree: bool = False) -> tuple[bool, str]:
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
