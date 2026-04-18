from typing import Any

from .controller import Job


class TaskJob(Job): ...


class ControllerHandle:
    connected: bool


class Tasker:
    controller: ControllerHandle
    inited: bool

    def __init__(self) -> None: ...

    def bind(self, resource: Any, controller: Any) -> None: ...

    def post_stop(self) -> Job: ...

    def post_task(
        self,
        entry: str,
        pipeline_override: dict[str, Any] = ...,
    ) -> TaskJob: ...
