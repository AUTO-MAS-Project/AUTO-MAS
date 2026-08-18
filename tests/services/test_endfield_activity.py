from datetime import datetime

from app.services.endfield_activity import (
    ENDFIELD_TIMEZONE,
    EndfieldActivityService,
    _build_pool_records,
)


def test_build_pool_records_resolves_time_name_and_up_character() -> None:
    records = _build_pool_records(
        pools={
            "special_1_4_2": {
                "name": {"id": 1001},
                "type": 0,
                "sortId": 2,
                "upCharIds": ["chr_0035_liino"],
            }
        },
        time_ranges={
            "time_special_1_4_2": {
                "timeRangeList": [
                    {
                        "openTime": "2026/08/09 12:00:00",
                        "closeTime": "2026/09/02 06:00:00",
                    }
                ]
            }
        },
        characters={"chr_0035_liino": {"name": {"id": 1002}}},
        text_table={"1001": "明耀晨星", "1002": "黎诺"},
    )

    assert len(records) == 1
    assert records[0].name == "明耀晨星"
    assert records[0].pool_type == "特许寻访"
    assert records[0].up_characters == ("黎诺",)
    assert records[0].start_time == datetime(
        2026, 8, 9, 12, 0, tzinfo=ENDFIELD_TIMEZONE
    )
    assert records[0].image_url.endswith("/charremoteicon/icon_chr_0035_liino.png")


def test_empty_overview_contains_pool_collection() -> None:
    service = EndfieldActivityService()
    # 清理可能已存在的磁盘缓存，避免测试依赖本地运行环境
    service._version_id = ""
    service._source_updated_at = ""
    service._activities = []
    service._pools = []

    overview = service._build_overview()

    assert overview["Pools"] == []
    assert overview["Activities"] == []
