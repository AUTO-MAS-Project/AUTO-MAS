import importlib

from app.core.config import RESTORE_POOL_MODULE_BOOK
from app.models.config import CLASS_BOOK


def test_restore_pool_book_covers_every_script_domain() -> None:
    assert set(RESTORE_POOL_MODULE_BOOK) == set(CLASS_BOOK.values())


def test_restore_pool_modules_expose_pools() -> None:
    for module_name in RESTORE_POOL_MODULE_BOOK.values():
        pools = getattr(importlib.import_module(module_name), "RESTORE_POOLS")
        assert isinstance(pools, list)
