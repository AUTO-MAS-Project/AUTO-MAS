from .errors import UnsupportedPlatformError


def _unsupported(*args, **kwargs):
    raise UnsupportedPlatformError("window")


get_window_handles = _unsupported
get_main_window_handle = _unsupported
is_visible = _unsupported
show_window = _unsupported
hide_window = _unsupported
minimize_window = _unsupported
activate_window = _unsupported
get_dpi_scaling = _unsupported
find_window_by_title = _unsupported
get_foreground_window = _unsupported
get_window_text = _unsupported
get_window_rect = _unsupported
is_minimized = _unsupported
restore_window = _unsupported
force_activate_window = _unsupported
