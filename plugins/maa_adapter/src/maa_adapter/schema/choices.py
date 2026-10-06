"""MAA 配置取值常量。"""

from __future__ import annotations

_SERVERS = (
    "Official",
    "Bilibili",
    "YoStarEN",
    "YoStarJP",
    "YoStarKR",
    "txwy",
)
_ANNIHILATION = (
    "Close",
    "Annihilation",
    "Chernobog@Annihilation",
    "LungmenOutskirts@Annihilation",
    "LungmenDowntown@Annihilation",
)
_WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)
_INFRAST = ("Normal", "Rotation", "Custom")
_SERIES = ("0", "6", "5", "4", "3", "2", "1", "-1")
_TRANSITION = ("NoAction", "ExitGame", "ExitEmulator")
_STAGE_KEYS = ("MedicineNumb", "SeriesNumb", "Stage", "Stage_1", "Stage_2", "Stage_3")
_DEPOT_DEFAULT = (
    '[{"Stage":"PR-A-1","DropId":"3261","DropCount":20},'
    '{"Stage":"PR-A-1","DropId":"3231","DropCount":20},'
    '{"Stage":"PR-B-1","DropId":"3251","DropCount":20},'
    '{"Stage":"PR-B-1","DropId":"3241","DropCount":20},'
    '{"Stage":"PR-C-1","DropId":"3211","DropCount":20},'
    '{"Stage":"PR-C-1","DropId":"3271","DropCount":20},'
    '{"Stage":"PR-D-1","DropId":"3221","DropCount":20},'
    '{"Stage":"PR-D-1","DropId":"3281","DropCount":20},'
    '{"Stage":"PR-A-2","DropId":"3262","DropCount":20},'
    '{"Stage":"PR-A-2","DropId":"3232","DropCount":20},'
    '{"Stage":"PR-B-2","DropId":"3252","DropCount":20},'
    '{"Stage":"PR-B-2","DropId":"3242","DropCount":20},'
    '{"Stage":"PR-C-2","DropId":"3212","DropCount":20},'
    '{"Stage":"PR-C-2","DropId":"3272","DropCount":20},'
    '{"Stage":"PR-D-2","DropId":"3222","DropCount":20},'
    '{"Stage":"PR-D-2","DropId":"3282","DropCount":20},'
    '{"Stage":"CE-6","DropId":"4001","DropCount":2000000},'
    '{"Stage":"AP-5","DropId":"4006","DropCount":5000},'
    '{"Stage":"CA-5","DropId":"3303","DropCount":200}]'
)
