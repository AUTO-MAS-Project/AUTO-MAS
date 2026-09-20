class UnsupportedPlatformError(RuntimeError):
    def __init__(self, capability: str) -> None:
        self.capability = capability
        super().__init__(f"Capability '{capability}' is not supported on this platform")
