import os
import subprocess


class WindowsProcessPlatform:
    creation_flags = subprocess.CREATE_NO_WINDOW
    detached_flags = (
        subprocess.CREATE_NEW_PROCESS_GROUP
        | subprocess.DETACHED_PROCESS
        | subprocess.CREATE_NO_WINDOW
    )

    async def open_protocol(self, protocol_url: str) -> None:
        os.startfile(protocol_url)
