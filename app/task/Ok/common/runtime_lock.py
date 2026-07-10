#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

import asyncio
from pathlib import Path


_ROOT_RUNTIME_LOCKS: dict[str, asyncio.Lock] = {}


def get_ok_script_root_lock(root_path: Path) -> asyncio.Lock:
    """Return the runtime lock for an ok-script physical root path."""

    root_key = str(root_path.resolve(strict=False)).casefold()
    lock = _ROOT_RUNTIME_LOCKS.get(root_key)
    if lock is None:
        lock = asyncio.Lock()
        _ROOT_RUNTIME_LOCKS[root_key] = lock
    return lock
