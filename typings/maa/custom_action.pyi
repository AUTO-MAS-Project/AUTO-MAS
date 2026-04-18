from .context import Context


class CustomAction:
    class RunArg: ...

    def run(self, context: Context, argv: RunArg) -> bool: ...
