#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

"""Legacy import facade for the plugin-owned OK-WW runtime."""

from okww_adapter.adapter.autoproxy import AutoProxyTask, _OKWW_REL_CONFIG_DIR

__all__ = ["AutoProxyTask", "_OKWW_REL_CONFIG_DIR"]
