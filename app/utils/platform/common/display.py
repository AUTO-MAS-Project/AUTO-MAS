from .errors import UnsupportedPlatformError


def _unsupported(*args, **kwargs):
    raise UnsupportedPlatformError("display")


MonitorInfo = None

per_monitor_dpi = _unsupported
list_monitors = _unsupported
frame_size_for_client = _unsupported
can_host_client = _unsupported
find_host_monitor = _unsupported
has_real_display = _unsupported
real_display_devices = _unsupported
describe_monitors = _unsupported
