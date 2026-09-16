from app.models.config import CLASS_BOOK, USER_CONFIG_BOOK


def test_user_config_book_covers_every_script_domain() -> None:
    assert set(USER_CONFIG_BOOK) == set(CLASS_BOOK.values())


def test_user_config_book_maps_domains_to_distinct_classes() -> None:
    values = list(USER_CONFIG_BOOK.values())
    assert len(set(values)) == len(values)
    assert all(isinstance(cls, type) for cls in values)
