import ctypes
import subprocess


class WindowsPowerController:
    supported_actions = frozenset(
        {"Shutdown", "ShutdownForce", "Reboot", "Hibernate", "Sleep", "Logoff"}
    )

    async def execute(self, action: str) -> None:
        commands = {
            "Shutdown": ["shutdown", "/s", "/t", "0"],
            "ShutdownForce": ["shutdown", "/s", "/t", "0", "/f"],
            "Reboot": ["shutdown", "/r", "/t", "0"],
            "Hibernate": ["shutdown", "/h"],
            "Sleep": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
            "Logoff": ["shutdown", "/l"],
        }
        subprocess.run(commands[action])

    async def set_sleep_prevention(self, enabled: bool) -> None:
        state = 0x80000000 | (0x00000001 if enabled else 0)
        ctypes.windll.kernel32.SetThreadExecutionState(state)
