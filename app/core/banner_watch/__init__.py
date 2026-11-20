# SPDX-License-Identifier: AGPL-3.0-or-later
"""卡池关注、核实和派发。"""

from .service import BANNER_REFRESH_INTERVAL_SECONDS, _BannerWatch

BannerWatch = _BannerWatch()

__all__ = ["BannerWatch", "BANNER_REFRESH_INTERVAL_SECONDS"]
