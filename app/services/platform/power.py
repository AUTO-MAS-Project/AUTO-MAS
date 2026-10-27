from app.utils import IS_WINDOWS

if IS_WINDOWS:
    from .windows.power import WindowsPowerController

    power = WindowsPowerController()
else:
    from .common.power import CommonPowerController

    power = CommonPowerController()
