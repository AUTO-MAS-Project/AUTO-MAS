"""SecretAPI 的平台无关调用契约。"""

from typing import Protocol


class SecretAPI(Protocol):
    def looks_like_dpapi_blob(self, value: object) -> bool: ...

    def dpapi_encrypt(
        self, note: str, description: None | str = None, entropy: None | bytes = None
    ) -> str: ...

    def dpapi_decrypt(self, note: str, entropy: None | bytes = None) -> str: ...

    def supports_secret_storage(self) -> bool: ...

    def is_secret_storage_error(self, error: BaseException) -> bool: ...
