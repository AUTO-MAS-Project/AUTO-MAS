from pathlib import Path
from typing import Any, Callable, TypeVar

from .controller import Job

_T = TypeVar("_T")


class Resource:
    def post_bundle(self, path: str | Path) -> Job: ...

    def custom_action(self, name: str) -> Callable[[type[_T]], type[_T]]: ...
