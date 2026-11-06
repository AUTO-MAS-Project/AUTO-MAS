from contextlib import contextmanager
from importlib import import_module
from types import SimpleNamespace

import pytest

CLICK_MODULES = (
    "app.task.OkNte.tools.launcher_start",
    "app.task.OkNte.tools.account_switch",
    "app.task.Okww.tools.launcher_start",
    "app.task.Okww.tools.account_switch",
    "app.task.MaaEnd.tools.launcher_start",
    "app.task.MaaEnd.tools.login",
    "app.task.BetterGI.tools.account_switch_native",
)


@pytest.fixture
def desktop(monkeypatch):
    """模拟改变缩放后，普通线程坐标被 Windows 虚拟化。"""
    state = SimpleNamespace(physical=False, cursor=(300, 200), clicks=[], scrolls=[])

    @contextmanager
    def physical_dpi():
        previous = state.physical
        state.physical = True
        try:
            yield
        finally:
            state.physical = previous

    def position():
        x, y = state.cursor
        return (x, y) if state.physical else (round(x / 0.8), round(y / 0.8))

    def move(x, y):
        state.cursor = (x, y) if state.physical else (round(x * 0.8), round(y * 0.8))

    mouse = SimpleNamespace(
        position=position,
        moveTo=move,
        click=lambda: state.clicks.append(state.cursor),
        scroll=lambda amount: state.scrolls.append((state.cursor, amount)),
    )

    def prepare(module):
        monkeypatch.setattr(
            module, "_utils_display", SimpleNamespace(per_monitor_dpi=physical_dpi)
        )
        monkeypatch.setattr(module, "pyautogui", mouse, raising=False)
        monkeypatch.setattr(
            module,
            "win32gui",
            SimpleNamespace(ClientToScreen=lambda hwnd, point: point),
            raising=False,
        )
        monkeypatch.setattr(
            module, "_client_size", lambda *args, **kwargs: (1920, 1080)
        )
        monkeypatch.setattr(module.time, "sleep", lambda seconds: None)
        if hasattr(module, "_pause"):
            monkeypatch.setattr(module, "_pause", lambda *args: None)

    return state, prepare


@pytest.mark.parametrize("module_name", CLICK_MODULES)
def test_click_uses_physical_coordinates_after_scale_change(module_name, desktop):
    state, prepare = desktop
    module = import_module(module_name)
    prepare(module)

    module._click_box(1, (990, 490, 20, 20), activate=False)

    assert state.clicks == [(1000, 500)]
    assert state.cursor == (300, 200)


@pytest.mark.parametrize("module_name", (CLICK_MODULES[1], CLICK_MODULES[6]))
def test_account_list_scroll_uses_physical_coordinates(module_name, desktop):
    state, prepare = desktop
    module = import_module(module_name)
    prepare(module)

    module._scroll_list(1)

    assert state.scrolls == [(module._LIST_SCROLL_POINT, -3)]
