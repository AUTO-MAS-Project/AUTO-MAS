#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
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


import hashlib
import hmac
import re
import threading

CHALLENGE_HEADER = "X-Auto-MAS-Challenge"
PROOF_HEADER = "X-Auto-MAS-Proof"
TIMESTAMP_HEADER = "X-Auto-MAS-Timestamp"
SECRET_ENVIRONMENT = "AUTO_MAS_SUPERVISION_SECRET"


def valid_secret(secret: str) -> bool:
    """只接受监督器生成的固定编码密钥。"""
    return re.fullmatch(r"[0-9a-f]{64}", secret) is not None


def health_proof(secret: str, challenge: str, body: bytes) -> str:
    """绑定原始正文，避免依赖 JSON 字段排序。"""
    message = b"auto-mas-health-v1\n" + challenge.encode("ascii") + b"\n" + body
    return hmac.new(secret.encode("ascii"), message, hashlib.sha256).hexdigest()


class CloseVerifier:
    """保存时间窗口内已经接受的挑战，拒绝重放并限制缓存规模。"""

    def __init__(self) -> None:
        self._used: dict[str, int] = {}
        self._lock = threading.Lock()

    def verify(
        self,
        secret: str,
        challenge: str,
        timestamp: str,
        proof: str,
        port: int,
        now: int,
    ) -> bool:
        if not valid_secret(secret) or not 1024 <= port <= 65535:
            return False
        if (
            re.fullmatch(r"[0-9a-f]{32}", challenge) is None
            or re.fullmatch(r"[0-9a-f]{64}", proof) is None
        ):
            return False
        if re.fullmatch(r"[0-9]{1,12}", timestamp) is None:
            return False
        signed_at = int(timestamp)
        if abs(now - signed_at) > 30:
            return False
        message = f"auto-mas-close-v1\nPOST\n/api/core/close\n{port}\n{timestamp}\n{challenge}"
        expected = hmac.new(
            secret.encode("ascii"), message.encode("ascii"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, proof):
            return False
        with self._lock:
            self._used = {
                nonce: expiry for nonce, expiry in self._used.items() if expiry >= now
            }
            if challenge in self._used or len(self._used) >= 1024:
                return False
            self._used[challenge] = signed_at + 30
        return True
