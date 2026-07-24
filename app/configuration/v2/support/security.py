"""Config v2 的共享 DPAPI 配置密文入口。

实现、application entropy 和版本兼容策略统一由 ``app.utils.security``
维护；本模块只保留 Config v2 既有导入路径。
"""

from __future__ import annotations

from app.utils.security import (
    DPAPI_CONFIG_PREFIX,
    DPAPIDecryptionResult,
    DPAPIProtectionError,
    decrypt_config_value as dpapi_decrypt,
    decrypt_config_value_with_status as dpapi_decrypt_with_status,
    encrypt_config_value as dpapi_encrypt,
    is_probable_dpapi_ciphertext,
)

__all__ = [
    "DPAPI_CONFIG_PREFIX",
    "DPAPIDecryptionResult",
    "DPAPIProtectionError",
    "dpapi_decrypt",
    "dpapi_decrypt_with_status",
    "dpapi_encrypt",
    "is_probable_dpapi_ciphertext",
]
