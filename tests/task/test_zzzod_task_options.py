#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License
#   as published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""ZZZ-OD 任务计划动态选项与 plan_list 合并原语测试。"""

from pathlib import Path

import yaml

from app.task.ZzzOd.tools import (
    agent_id_options,
    agent_names,
    auto_battle_options,
    coffee_options,
    expand_team_list,
    get_task_app_fields,
    get_task_app_jump,
    hollow_zero_challenge_options,
    hollow_zero_missions,
    lost_void_challenge_options,
    lost_void_missions,
    merge_plan_list,
    read_team_list,
    resolve_field_options,
    train_categories,
    world_patrol_route_lists,
    write_team_list,
)


def _make_root(tmp_path: Path) -> Path:
    """构造一个最小 zzz-od 安装目录（compendium + 配置目录）。"""

    (tmp_path / "assets" / "game_data" / "agent").mkdir(parents=True)
    (tmp_path / "config" / "auto_battle").mkdir(parents=True)
    (tmp_path / "config" / "lost_void_challenge").mkdir(parents=True)
    (tmp_path / "config" / "hollow_zero_challenge").mkdir(parents=True)
    (tmp_path / "config" / "world_patrol_route_list").mkdir(parents=True)
    (tmp_path / "assets" / "game_data" / "compendium_data.yml").write_text(
        yaml.safe_dump(
            [
                {"tab_name": "目标"},
                {
                    "tab_name": "训练",
                    "category_list": [
                        {
                            "category_name": "实战模拟室",
                            "mission_type_list": [
                                {
                                    "mission_type_name": "基础材料",
                                    "mission_list": [
                                        {
                                            "mission_name": "调查专项",
                                            "mission_name_display": "代理人经验",
                                        },
                                    ],
                                }
                            ],
                        },
                        {"category_name": "恶名狩猎"},
                    ],
                },
                {
                    "tab_name": "作战",
                    "category_list": [
                        {
                            "category_name": "零号空洞",
                            "mission_type_list": [
                                {
                                    "mission_type_name": "迷失之地",
                                    "mission_list": [
                                        {"mission_name": "战线肃清"},
                                    ],
                                },
                                {
                                    "mission_type_name": "旧都列车",
                                    "mission_list": [
                                        {"mission_name": "旧都列车-内部"},
                                    ],
                                },
                            ],
                        }
                    ],
                },
            ],
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    (tmp_path / "assets" / "game_data" / "coffee_data.yml").write_text(
        yaml.safe_dump(
            {
                "coffee_list": [
                    {"coffee_name": "汀曼特调"},
                    {
                        "coffee_name": "浓缩咖啡",
                        "mission_type_name": "实战模拟室",
                        "mission_name": "通用",
                    },
                ],
                "schedule": [
                    {
                        "days": [1, 2, 3, 4, 5, 6, 7],
                        "coffee_list": ["浓缩咖啡", "汀曼特调"],
                    },
                ],
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    for name, data in (
        ("anby.yml", {"agent_name": "安比"}),
        ("ellen.yml", {"agent_name": "艾莲"}),
    ):
        (tmp_path / "assets" / "game_data" / "agent" / name).write_text(
            yaml.safe_dump(data, allow_unicode=True), encoding="utf-8"
        )
    for name in ("全配队通用.merged.yml", "专属.yml.sample.yml", "临时.txt"):
        (tmp_path / "config" / "auto_battle" / name).write_text("", encoding="utf-8")
    for name in ("默认-成就模式.sample.yml", "自定义-1.yml"):
        (tmp_path / "config" / "lost_void_challenge" / name).write_text(
            "", encoding="utf-8"
        )
    (
        tmp_path / "config" / "hollow_zero_challenge" / "默认-专属空洞-艾莲.sample.yml"
    ).write_text("", encoding="utf-8")
    (tmp_path / "config" / "world_patrol_route_list" / "中央制造区.yml").write_text(
        yaml.safe_dump(
            {"name": "中央制造区", "list_type": "whitelist", "route_items": []},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_train_categories(tmp_path: Path) -> None:
    cats = train_categories(_make_root(tmp_path))
    names = [c["name"] for c in cats]
    assert names == ["实战模拟室", "恶名狩猎"]
    # 恶名狩猎与上游 CompendiumService 一致展示「恶名狩猎 深度追猎」
    assert (
        next(c for c in cats if c["name"] == "恶名狩猎")["label"] == "恶名狩猎 深度追猎"
    )
    sim = next(c for c in cats if c["name"] == "实战模拟室")
    assert sim["mission_types"][0]["missions"][0] == {
        "name": "调查专项",
        "display": "代理人经验",
    }


def test_lost_void_missions(tmp_path: Path) -> None:
    assert lost_void_missions(_make_root(tmp_path)) == ["战线肃清"]


def test_dir_template_options(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    # auto_battle：剥离 .merged/.sample 后缀，非 yml 忽略，不区分大小写排序
    assert [o["value"] for o in auto_battle_options(root)] == ["专属.yml", "全配队通用"]
    # 挑战配置：.sample 与普通 yml 均计入
    assert [o["value"] for o in lost_void_challenge_options(root)] == [
        "自定义-1",
        "默认-成就模式",
    ]


def test_resolve_field_options_dynamic(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    fields = {m["field"]: m for m in get_task_app_fields("lost_void") or []}
    assert [
        o["value"] for o in resolve_field_options(root, fields["mission_name"])
    ] == ["战线肃清"]
    assert (
        resolve_field_options(root, fields["extra_task"])[0]["value"] == "完成悬赏委托"
    )


def test_get_task_app_jump() -> None:
    assert get_task_app_jump("shiyu_defense")
    assert get_task_app_jump("lost_void")
    assert get_task_app_jump("withered_domain")
    assert not get_task_app_jump("suibian_temple")
    assert not get_task_app_jump("redemption_code")
    assert not get_task_app_jump("charge_plan")
    assert not get_task_app_jump("daily_signin")


def test_new_dynamic_sources(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    # 枯萎之都选图：零号空洞排除迷失之地，取 mission_name
    assert hollow_zero_missions(root) == ["旧都列车-内部"]
    # 枯萎之都挑战配置：sample 计入
    assert [o["value"] for o in hollow_zero_challenge_options(root)] == [
        "默认-专属空洞-艾莲"
    ]
    # 咖啡按星期取排程，展示名按类型 - 关卡回退
    assert [o["value"] for o in coffee_options(root, 1)] == ["浓缩咖啡", "汀曼特调"]
    assert coffee_options(root, 1)[0]["label"] == "实战模拟室 - 通用"
    # 锄大地路线名单：yml 内 name 字段
    assert [o["value"] for o in world_patrol_route_lists(root)] == ["中央制造区"]
    # 代理人名
    assert [o["value"] for o in agent_names(root)] == ["安比", "艾莲"]
    # 预备编队成员选项：value=agent_id（数据文件名），label=代理人名
    assert agent_id_options(root) == [
        {"label": "安比", "value": "anby"},
        {"label": "艾莲", "value": "ellen"},
    ]


def test_static_options_prepend_dynamic_source(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    fields = {m["field"]: m for m in get_task_app_fields("random_play") or []}
    opts = resolve_field_options(root, fields["agent_name_1"])
    # 静态「随机」前置 + 动态代理人
    assert [o["value"] for o in opts] == ["随机", "安比", "艾莲"]

    wp = {m["field"]: m for m in get_task_app_fields("world_patrol") or []}
    route_opts = resolve_field_options(root, wp["route_list"])
    assert [o["value"] for o in route_opts] == ["", "中央制造区"]


def test_all_configurable_apps_have_fields() -> None:
    """核心可配置任务都有元数据（防误删）。"""

    for app_id in (
        "daily_signin",
        "charge_plan",
        "notorious_hunt",
        "lost_void",
        "withered_domain",
        "coffee",
        "intel_board",
        "suibian_temple",
        "world_patrol",
        "life_on_line",
        "drive_disc_dismantle",
        "random_play",
    ):
        assert get_task_app_fields(app_id), f"{app_id} 缺元数据"


def test_team_list_write_preserves_agents(tmp_path: Path) -> None:
    """预备编队保存：成员按行保留，名称/配队方案可编辑。"""

    import tempfile

    with tempfile.TemporaryDirectory() as td:
        config_dir = Path(td)
        write_team_list(
            config_dir,
            [
                {
                    "name": "一队",
                    "auto_battle": "专属配队-艾莲",
                    "agent_id_list": ["anby", "anton", "ben"],
                },
            ],
        )
        assert read_team_list(config_dir)[0]["agent_id_list"] == [
            "anby",
            "anton",
            "ben",
        ]

        # 再次保存：不带成员，原成员按行保留
        write_team_list(config_dir, [{"name": "一队改", "auto_battle": "全配队通用"}])
        teams = read_team_list(config_dir)
        assert teams[0]["name"] == "一队改"
        assert teams[0]["auto_battle"] == "全配队通用"
        assert teams[0]["agent_id_list"] == ["anby", "anton", "ben"]


def test_expand_team_list_fills_defaults(tmp_path: Path) -> None:
    """预备编队展开：固定 20 个，缺失项补「编队N」默认（与上游 team_list 一致）。"""

    import tempfile

    with tempfile.TemporaryDirectory() as td:
        config_dir = Path(td)
        write_team_list(config_dir, [{"name": "一队", "auto_battle": "专属配队-艾莲"}])
        expanded = expand_team_list(config_dir)

        assert len(expanded) == 20
        assert expanded[0]["idx"] == 0
        assert expanded[0]["name"] == "一队"
        assert expanded[0]["auto_battle"] == "专属配队-艾莲"
        assert expanded[0]["agent_id_list"] == ["unknown", "unknown", "unknown"]
        assert expanded[1]["name"] == "编队2"
        assert expanded[1]["auto_battle"] == "全配队通用"
        assert expanded[1]["agent_id_list"] == []
        assert expanded[19]["name"] == "编队20"


def test_merge_plan_list_preserves_run_times(tmp_path: Path) -> None:
    meta = next(
        m for m in get_task_app_fields("charge_plan") or [] if m["type"] == "plan_list"
    )
    existing = [
        {"plan_id": "p1", "run_times": 2, "category_name": "实战模拟室", "junk": 1}
    ]
    incoming = [
        {
            "plan_id": "p1",
            "category_name": "实战模拟室",
            "plan_times": "3",
            "run_times": 99,
        },
        {"category_name": "合成电池", "plan_times": 2},
    ]
    merged = merge_plan_list(meta["columns"], meta["new_item"], existing, incoming)

    # 已运行进度按 plan_id 保留；白名单外的键（junk/__key）被丢弃
    assert merged[0]["run_times"] == 2 and "junk" not in merged[0]
    # 次数转 int；新计划补 plan_id 且 run_times 从 0 开始
    assert merged[0]["plan_times"] == 3 and isinstance(merged[0]["plan_times"], int)
    assert merged[1]["plan_id"] and merged[1]["run_times"] == 0
    assert merged[1]["tab_name"] == "训练"  # new_item 默认值补齐


def test_merge_plan_list_empty(tmp_path: Path) -> None:
    meta = next(
        m
        for m in get_task_app_fields("notorious_hunt") or []
        if m["type"] == "plan_list"
    )
    assert merge_plan_list(meta["columns"], meta["new_item"], [], [None, "x"]) == []


def test_predefined_team_options_and_plan_columns(tmp_path: Path) -> None:
    """游戏内配队列：选项「游戏内配队」(-1) 前置 + 全部编队；计划行保留配队下标。"""

    import tempfile

    from app.task.ZzzOd.tools import predefined_team_options

    with tempfile.TemporaryDirectory() as td:
        config_dir = Path(td)
        write_team_list(config_dir, [{"name": "一队", "auto_battle": "全配队通用"}])
        options = predefined_team_options(config_dir)
        assert options[0] == {"label": "游戏内配队", "value": -1}
        assert options[1] == {"label": "一队", "value": 0}
        assert len(options) == 21  # 游戏内配队 + 固定 20 编队

    # 体力计划列含游戏内配队（team 类型，动态源 predefined_teams）
    meta = next(
        m for m in get_task_app_fields("charge_plan") or [] if m["type"] == "plan_list"
    )
    team_col = next(c for c in meta["columns"] if c["field"] == "predefined_team_idx")
    assert team_col["type"] == "team" and team_col["source"] == "predefined_teams"

    # 配队方案与游戏内配队按上游 GUI 互斥（合成电池分类下都隐藏）
    battle_col = next(c for c in meta["columns"] if c["field"] == "auto_battle_config")
    assert {"field": "predefined_team_idx", "value": -1} in battle_col["show_when"]
    assert team_col["show_when"] == {
        "field": "category_name",
        "value": "合成电池",
        "not": True,
    }

    # 计划行合并：下拉提交的字符串下标转 int（-1=游戏内配队）
    merged = merge_plan_list(
        meta["columns"],
        meta["new_item"],
        [],
        [{"category_name": "实战模拟室", "predefined_team_idx": "2"}],
    )
    assert merged[0]["predefined_team_idx"] == 2
    assert isinstance(merged[0]["predefined_team_idx"], int)


def test_resolve_field_options_predefined_teams(tmp_path: Path) -> None:
    """predefined_teams 源按目标槽解析 team.yml；缺 config_dir 时无动态选项。

    选项 value 为原始 int 下标（端点层统一字符串化后再下发前端）。
    """

    from app.task.ZzzOd.tools import resolve_field_options

    meta = {
        "field": "predefined_team_idx",
        "type": "team",
        "source": "predefined_teams",
    }
    assert resolve_field_options(tmp_path, meta) == []

    import tempfile

    with tempfile.TemporaryDirectory() as td:
        config_dir = Path(td)
        write_team_list(config_dir, [{"name": "一队", "auto_battle": "全配队通用"}])
        options = resolve_field_options(tmp_path, meta, config_dir)
        assert options[0] == {"label": "游戏内配队", "value": -1}
        assert options[1] == {"label": "一队", "value": 0}
