class Window:
    left: int
    top: int
    width: int
    height: int
    isMinimized: bool
    isActive: bool

    def restore(self) -> None: ...

    def activate(self) -> None: ...


def getWindowsWithTitle(title: str) -> list[Window]: ...
