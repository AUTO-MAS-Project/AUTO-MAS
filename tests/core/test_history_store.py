from datetime import datetime

from app.core.history import HistoryStore


def test_history_uses_millisecond_stem_and_reads_legacy_seconds(tmp_path):
    store = HistoryStore()
    store.root = tmp_path
    path = store.save(
        time=datetime(2026, 10, 9, 12, 0, 1, 123456),
        username="user",
        type_key="maa",
        status="success",
        message="",
        logs="ok",
    )
    assert path.stem == "12-00-01-123"
    legacy = tmp_path / "2026-10-09" / "user" / "12-00-02.json"
    legacy.write_text('{"status":"success","data":{}}', encoding="utf-8")
    result = store.search(start_date="2026-10-09", end_date="2026-10-09")
    assert len(result["2026-10-09"]["user"]["index"]) == 2
