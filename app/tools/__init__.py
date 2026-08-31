#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

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


from .skland import login_skland_with_password, skland_sign_in
from .game_sign import run_all_sign_in, format_sign_results
from .community import (
    format_community_sign_results,
    has_community_credentials,
    run_community_sign_in,
)

__all__ = [
    "format_community_sign_results",
    "has_community_credentials",
    "login_skland_with_password",
    "run_community_sign_in",
    "skland_sign_in",
    "run_all_sign_in",
    "format_sign_results",
]
