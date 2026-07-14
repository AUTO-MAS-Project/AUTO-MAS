#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

"""Process-local locks keyed by a normalized filesystem path."""

from __future__ import annotations

import asyncio
from pathlib import Path


_PATH_RUNTIME_LOCKS: dict[str, asyncio.Lock] = {}


def get_path_runtime_lock(path: Path) -> asyncio.Lock:
    """Return the process-local lock for a filesystem path."""

    key = str(path.resolve(strict=False)).casefold()
    lock = _PATH_RUNTIME_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _PATH_RUNTIME_LOCKS[key] = lock
    return lock
