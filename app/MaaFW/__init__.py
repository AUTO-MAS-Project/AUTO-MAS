#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.


#   Contact: DLmaster_361@163.com


from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .ArknightWin32 import ArknightWin32Toolkit
    from .EndFieldPCWin32 import CheckComboxBox, CheckForm


def __getattr__(name: str):
    if name == "ArknightWin32Toolkit":
        from .ArknightWin32 import ArknightWin32Toolkit
        return ArknightWin32Toolkit
    if name == "CheckComboxBox":
        from .EndFieldPCWin32 import CheckComboxBox
        return CheckComboxBox
    if name == "CheckForm":
        from .EndFieldPCWin32 import CheckForm
        return CheckForm
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["ArknightWin32Toolkit", "CheckComboxBox", "CheckForm"]
