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

"""ZZZ-OD YAML 契约与实例槽备份恢复原语的最小回归测试。

用临时目录模拟 zzz-od 安装结构（config/one_dragon.yml 与实例目录），
验证实例发现、instance_run 读写、账号/任务 YAML 读写（目录参数化）、
实例槽备份恢复闭环与运行记录 diff 的纯逻辑。
"""

import json
import shutil
from pathlib import Path

import pytest

from app.task.ZzzOd.tools.backup_archive import (
    archive_mas_config_backup,
    archive_onedragon_backup,
    materialize_user_fields,
    onedragon_backup_root,
)
from app.task.ZzzOd.tools.catalog import list_app_catalog
from app.task.ZzzOd.tools.native_config import (
    NATIVE_INSTANCE_RUN_OPTIONS,
    read_native_account_fields,
    read_native_instance_run,
    read_native_tasks,
    save_native_account_fields,
    save_native_instance_run,
    save_native_tasks,
)
from app.task.ZzzOd.tools.zzz_od_config import (
    INSTANCE_RUN_ALL,
    RUN_STATUS_FAILED,
    RUN_STATUS_NOT_RUN,
    RUN_STATUS_RUNNING,
    RUN_STATUS_SUCCESS,
    add_instance,
    backup_instance,
    clear_run_records,
    diff_run_records,
    find_active_instance,
    find_free_instance_idx,
    instance_dir,
    list_instances,
    read_app_group,
    read_game_account,
    remove_instance,
    rename_instance,
    restore_instance,
    restore_instance_view,
    set_active_instance,
    set_instance_active_in_od,
    set_instance_force_login,
    snapshot_run_records,
    validate_root,
    write_app_group,
    write_game_account,
    write_instance_view,
)
from app.utils.config_archive import dir_files, list_times
from app.utils.io import read_file, write_file


def _make_root(tmp_path: Path) -> Path:
    """构造最小 zzz-od 安装结构：src 目录 + 单实例配置。"""
    (tmp_path / "src").mkdir()
    write_file(
        tmp_path / "config" / "one_dragon.yml",
        {
            "instance_list": [
                {
                    "idx": 1,
                    "name": "主号",
                    "active": True,
                    "active_in_od": True,
                    "force_login_before_run": False,
                }
            ],
            "instance_run": "仅运行当前",
        },
    )
    write_file(
        tmp_path / "config" / "01" / "game_account.yml",
        {
            "game_region": "cn",
            "game_path": r"G:\Games\ZenlessZoneZero.exe",
            "account": "主号账号",
            "password": "主号密码",
        },
    )
    write_file(
        tmp_path / "config" / "01" / "game.yml",
        {"full_screen": True},
    )
    write_file(
        tmp_path / "config" / "01" / "one_dragon" / "_group.yml",
        {"app_list": [{"app_id": "email", "enabled": True}]},
    )
    return tmp_path


def test_validate_root_rejects_missing_src(tmp_path: Path) -> None:
    try:
        validate_root(tmp_path)
        raise AssertionError("应当抛出 ValueError")
    except ValueError:
        pass


def test_instance_discovery(tmp_path: Path) -> None:
    root = _make_root(tmp_path)

    active = find_active_instance(root)
    assert active is not None and active["idx"] == 1
    assert [item["idx"] for item in list_instances(root)] == [1]


def test_game_account_read_modify_write(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    config_dir = root / "config" / "01"
    write_game_account(config_dir, {"account": "新账号", "use_custom_win_title": True})

    account = read_game_account(config_dir)
    assert account["account"] == "新账号"
    assert account["game_region"] == "cn"
    # 未知字段应保留
    assert account["use_custom_win_title"] is True


def test_app_group_write_normalizes(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    config_dir = root / "config" / "01"
    write_app_group(
        config_dir,
        [
            {"app_id": "coffee", "enabled": True},
            {"app_id": "email", "enabled": False},
            {"app_id": "  ", "enabled": True},  # 空 app_id 剔除
        ],
    )
    assert read_app_group(config_dir) == [
        {"app_id": "coffee", "enabled": True},
        {"app_id": "email", "enabled": False},
    ]


def test_snapshot_and_diff_run_records(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    record_dir = root / "config" / "01" / "app_run_record"
    write_file(record_dir / "email.yml", {"run_status": 0, "dt": "20260901"})
    write_file(record_dir / "coffee.yml", {"run_status": RUN_STATUS_SUCCESS})

    before = snapshot_run_records(root, 1)
    assert before == {"email": RUN_STATUS_NOT_RUN, "coffee": RUN_STATUS_SUCCESS}

    # 模拟运行：email 成功、coffee 保持成功、notify 新失败、daily 运行中
    write_file(record_dir / "email.yml", {"run_status": RUN_STATUS_SUCCESS})
    write_file(record_dir / "notify.yml", {"run_status": RUN_STATUS_FAILED})
    write_file(record_dir / "daily_signin.yml", {"run_status": RUN_STATUS_RUNNING})

    after = snapshot_run_records(root, 1)
    diffs = dict((app_id, new) for app_id, _, new in diff_run_records(before, after))
    assert diffs == {"email": RUN_STATUS_SUCCESS, "notify": RUN_STATUS_FAILED}
    # 运行中与未变化的不进 diff


def test_clear_run_records_and_backup_restore(tmp_path: Path) -> None:
    """清运行记录 + 备份/恢复闭环（MAS 注入前后的现场保护）。"""
    root = _make_root(tmp_path)
    record_dir = root / "config" / "01" / "app_run_record"
    write_file(record_dir / "email.yml", {"run_status": RUN_STATUS_SUCCESS})

    # 模拟用户态注入：写账号字段 + 任务编排 + 清运行记录
    slot_dir = instance_dir(root, 1)
    write_game_account(slot_dir, {"account": "注入账号"})
    write_app_group(slot_dir, [{"app_id": "coffee", "enabled": True}])
    clear_run_records(root, 1)
    assert read_game_account(slot_dir)["account"] == "注入账号"
    assert snapshot_run_records(root, 1) == {}

    # 备份/恢复闭环：注入前备份的原配置可原样恢复
    backup_dir = tmp_path / "backup"
    (root / "config" / "01.bak_seed").mkdir()
    shutil.rmtree(root / "config" / "01")
    write_file(root / "config" / "01" / "game_account.yml", {"account": "主号账号"})
    backup_instance(root, 1, backup_dir)
    write_game_account(slot_dir, {"account": "改过的账号"})
    assert read_game_account(slot_dir)["account"] == "改过的账号"
    restore_instance(root, 1, backup_dir)
    assert read_game_account(slot_dir)["account"] == "主号账号"


def test_find_free_instance_idx_with_used_set(tmp_path: Path) -> None:
    """空闲 idx 分配：原生注册表与 MAS 已绑定槽（跨脚本）共同占位。"""
    root = _make_root(tmp_path)
    assert find_free_instance_idx(root) == 2  # 1 被原生实例占用
    assert find_free_instance_idx(root, {2, 3}) == 4

    register_slot_dir = instance_dir(root, 2)
    register_slot_dir.mkdir(parents=True)
    assert find_free_instance_idx(root, {2}) == 3


def test_instance_view_write_restore_and_crash_recovery(tmp_path: Path) -> None:
    """合成注册表视图：写入/恢复/闪退自愈闭环。

    视图只含给定 MAS 槽（active_in_od=True、active 指向目标槽），
    恢复后 one_dragon.yml 回到原生内容；sidecar 保证闪退后可自愈。
    """
    root = _make_root(tmp_path)
    sidecar = root / "config" / "one_dragon.yml.mas-view.bak"

    write_instance_view(root, [(2, "MAS-用户B"), (3, "MAS-用户C")], active_idx=2)

    # 视图内容：仅 MAS 槽、全部参与一条龙、active 指向目标、运行范围为全部实例
    instances = list_instances(root)
    assert [(i["idx"], i["name"]) for i in instances] == [
        (2, "MAS-用户B"),
        (3, "MAS-用户C"),
    ]
    assert instances[0]["active"] is True
    assert instances[1]["active"] is False
    assert all(i["active_in_od"] for i in instances)
    assert (read_file(root / "config" / "one_dragon.yml") or {}).get(
        "instance_run"
    ) == INSTANCE_RUN_ALL
    assert sidecar.exists()

    # 恢复：原生注册表（含原生 instance_run）原样回来，sidecar 清除
    restore_instance_view(root)
    assert [item["idx"] for item in list_instances(root)] == [1]
    assert find_active_instance(root)["idx"] == 1
    assert (read_file(root / "config" / "one_dragon.yml") or {}).get(
        "instance_run"
    ) == "仅运行当前"
    assert not sidecar.exists()

    # 幂等：无 sidecar 时再恢复不报错不变化
    restore_instance_view(root)
    assert [item["idx"] for item in list_instances(root)] == [1]


def test_list_app_catalog_parses_const_files(tmp_path: Path) -> None:
    app_dir = tmp_path / "src" / "zzz_od" / "application"
    (app_dir / "email_app").mkdir(parents=True)
    (app_dir / "email_app" / "email_app_const.py").write_text(
        'APP_ID = "email"\nAPP_NAME = "邮件"\nDEFAULT_GROUP = True\nPRIORITY = 200\n',
        encoding="utf-8",
    )
    (app_dir / "coffee").mkdir()
    # 单引号写法也要能解析
    (app_dir / "coffee" / "coffee_const.py").write_text(
        "APP_ID = 'coffee'\nAPP_NAME = '咖啡店'\nDEFAULT_GROUP = False\n",
        encoding="utf-8",
    )
    # 无 APP_ID 的非应用 const 文件应被过滤
    (app_dir / "misc").mkdir()
    (app_dir / "misc" / "not_app_const.py").write_text(
        "SOME_VALUE = 1\n", encoding="utf-8"
    )

    apps = list_app_catalog(tmp_path)
    assert [app["app_id"] for app in apps] == ["email", "coffee"]
    assert apps[0]["app_name"] == "邮件"
    assert apps[0]["default_group"] is True
    assert apps[0]["priority"] == 200
    assert apps[1]["priority"] == 9999  # 未写 PRIORITY 置底


def test_list_app_catalog_missing_dir(tmp_path: Path) -> None:
    try:
        list_app_catalog(tmp_path)
        raise AssertionError("应当抛出 ValueError")
    except ValueError:
        pass


def test_native_account_fields_whitelist_and_write(tmp_path: Path) -> None:
    """直控账号字段：字段集固定、白名单过滤、未知字段保留。"""
    root = _make_root(tmp_path)
    slot_dir = instance_dir(root, 1)

    fields = read_native_account_fields(root, 1)
    assert [f["key"] for f in fields] == [
        "game_region",
        "game_path",
        "account",
        "password",
        "bilibili_account_name",
        "game_language",
    ]
    by_key = {f["key"]: f for f in fields}
    assert by_key["game_region"]["value"] == "cn"
    assert by_key["account"]["value"] == "主号账号"
    # 选项字段带可选项；自由输入字段无选项（供前端渲染下拉/输入切换）
    assert len(by_key["game_region"]["options"]) > 0
    assert by_key["account"]["options"] == []

    # 未知字段拒绝
    try:
        save_native_account_fields(root, 1, {"unknown_field": "x"})
        raise AssertionError("应当抛出 ValueError")
    except ValueError:
        pass

    # 写回只改白名单字段，未知原生字段保留
    write_game_account(slot_dir, {"use_custom_win_title": True})
    save_native_account_fields(root, 1, {"account": "改后账号", "game_region": "cn_b"})
    data = read_game_account(slot_dir)
    assert data["account"] == "改后账号"
    assert data["game_region"] == "cn_b"
    assert data["use_custom_win_title"] is True


def test_native_account_default_merge_and_default_skip(tmp_path: Path) -> None:
    """直控账号字段与一条龙 GUI 同步：缺失字段合并默认值；值变化（含回退默认）落盘。

    行为：
    - 原文件缺失 + 提交值 = 默认 → 跳过（不污染）
    - 原文件缺失 + 提交值 ≠ 默认 → 落盘
    - 原文件有值 + 值变化 → 落盘（含清空回默认：删字段）
    - 原文件有值 + 值未变 → 跳过
    """
    root = _make_root(tmp_path)
    slot_dir = instance_dir(root, 1)

    # 模拟 zzz-od 只持久化非默认字段的真实情况：game_region 缺失（=默认国服）
    write_file(slot_dir / "game_account.yml", {"game_path": r"G:\Games\ZZZ.exe"})

    fields = read_native_account_fields(root, 1)
    by_key = {f["key"]: f for f in fields}
    # 缺失字段合并默认值：区服/语言回退 cn，账号/密码/B服名为空串
    assert by_key["game_region"]["value"] == "cn"
    assert by_key["game_language"]["value"] == "cn"
    assert by_key["account"]["value"] == ""
    assert by_key["password"]["value"] == ""
    assert by_key["bilibili_account_name"]["value"] == ""
    assert by_key["game_path"]["value"] == r"G:\Games\ZZZ.exe"

    # 整表 patch：所有白名单内字段（值未变时由 yaml_operator.update 自动
    # 跳过 → 不污染文件；值变化时落盘——含「等于默认」的字段）
    save_native_account_fields(
        root,
        1,
        {
            "game_region": "cn",
            "game_language": "cn",
            "account": "",
            "game_path": r"G:\Games\ZZZ.exe",
        },
    )
    data = read_game_account(slot_dir)
    # 文件内未变化的字段保持原状：game_path 原本就有仍保留；
    # game_region/game_language/account 在 patch 里显式提交且值与默认
    # 相同（等于 yaml_operator.update 跳过条件），不落盘
    assert "game_region" not in data
    assert "game_language" not in data
    assert "account" not in data
    assert data["game_path"] == r"G:\Games\ZZZ.exe"

    # 值变化时（含回退到默认）必须落盘：原值 "abc" → 清空（= 默认空串）→
    # 字段被 yaml_operator.update 写为空串（read 端会合并为默认 → 表单显示空）
    write_file(
        slot_dir / "game_account.yml",
        {
            "game_path": r"G:\Games\ZZZ.exe",
            "account": "abc",
            "password": "secret",
        },
    )
    save_native_account_fields(
        root,
        1,
        {
            "game_region": "cn",
            "account": "abc",  # 未变，跳过
            "password": "",  # 原 secret → 清空（= 默认），落盘为空串
        },
    )
    data = read_game_account(slot_dir)
    assert data["account"] == "abc"  # 未变 → 保持
    assert data["password"] == ""  # 清空回默认 → 字段被写为空串
    assert data["game_path"] == r"G:\Games\ZZZ.exe"
    # read_native_account_fields 把空串视为默认 = 表单清空
    fields = read_native_account_fields(root, 1)
    by_key = {f["key"]: f for f in fields}
    assert by_key["password"]["value"] == ""


def test_native_tasks_merge_and_full_order_writeback(tmp_path: Path) -> None:
    """直控任务编排：目录并入可选项（enabled 保持原生状态）；保存保留完整顺序。"""
    root = _make_root(tmp_path)
    catalog = [
        {"app_id": "email", "app_name": "邮件", "default_group": True, "priority": 200},
        {
            "app_id": "coffee",
            "app_name": "咖啡店",
            "default_group": True,
            "priority": 9999,
        },
    ]

    # 原生 app_list 仅 email(启用)；coffee 未加入 → 并入为禁用可选项
    tasks = read_native_tasks(root, 1, catalog)
    assert [t["app_id"] for t in tasks] == ["email", "coffee"]
    assert tasks[0]["enabled"] is True
    assert tasks[1]["enabled"] is False
    assert tasks[0]["app_name"] == "邮件"

    # 保存保留完整顺序与启用状态（未启用项原位保留，对齐原生队列语义）
    save_native_tasks(root, 1, tasks)
    assert read_app_group(instance_dir(root, 1)) == [
        {"app_id": "email", "enabled": True},
        {"app_id": "coffee", "enabled": False},
    ]

    # 翻转启用状态后顺序不变
    tasks[0]["enabled"] = False
    tasks[1]["enabled"] = True
    save_native_tasks(root, 1, tasks)
    app_list = read_app_group(instance_dir(root, 1))
    assert app_list == [
        {"app_id": "email", "enabled": False},
        {"app_id": "coffee", "enabled": True},
    ]


def test_native_instance_manage_add_rename_flag_remove(tmp_path: Path) -> None:
    """直控实例管理：添加（避开占用槽）→ 参与开关 → 重命名 → 删除的闭环。"""
    root = _make_root(tmp_path)  # 原生 instance_list 已含 idx=1

    # 添加：最小空闲槽 = 2；默认参与全部实例、不活跃；目录与空 game_account 已建
    idx = add_instance(root, "新实例", used_idxs={3})
    assert idx == 2  # 1 被原生占用、3 被 used_idxs 占用 → 取 2
    entries = {int(e["idx"]): e for e in list_instances(root)}
    assert entries[2]["name"] == "新实例"
    assert entries[2]["active_in_od"] is True
    assert entries[2]["active"] is False
    assert instance_dir(root, 2).is_dir()
    assert (instance_dir(root, 2) / "game_account.yml").is_file()

    # 参与「全部实例」开关
    set_instance_active_in_od(root, 2, False)
    assert {int(e["idx"]): e for e in list_instances(root)}[2]["active_in_od"] is False
    set_instance_active_in_od(root, 2, True)

    # 重命名（目录不受影响）
    rename_instance(root, 2, "改名实例")
    assert {int(e["idx"]): e for e in list_instances(root)}[2]["name"] == "改名实例"

    # 删除：注册表条目与目录一起消失，原生实例不受影响
    remove_instance(root, 2)
    assert [int(e["idx"]) for e in list_instances(root)] == [1]
    assert not instance_dir(root, 2).exists()


def test_native_instance_manage_guards(tmp_path: Path) -> None:
    """直控实例管理守卫：空名 / 不存在实例 / 最后实例 / MAS 绑定槽均拒绝。"""
    root = _make_root(tmp_path)

    try:
        add_instance(root, "  ")
        raise AssertionError("空名应被拒绝")
    except ValueError:
        pass

    try:
        rename_instance(root, 1, "")
        raise AssertionError("空名应被拒绝")
    except ValueError:
        pass

    try:
        set_instance_active_in_od(root, 99, True)
        raise AssertionError("不存在实例应被拒绝")
    except ValueError:
        pass

    # 只有 1 个实例：不可删
    try:
        remove_instance(root, 1)
        raise AssertionError("最后一个实例应被拒绝删除")
    except ValueError:
        pass

    # 被 MAS 绑定槽保护：不可删
    add_instance(root, "新实例")
    try:
        remove_instance(root, 2, protected_idxs={2})
        raise AssertionError("MAS 绑定槽应被保护")
    except ValueError:
        pass

    # 删除活跃实例后，剩余首个实例自动接管 active
    assert find_active_instance(root)["idx"] == 1
    set_instance_active_in_od(root, 2, False)
    remove_instance(root, 2)
    assert [int(e["idx"]) for e in list_instances(root)] == [1]


def test_set_instance_force_login_writes_registry(tmp_path: Path) -> None:
    """运行前切换账号开关：映射实例条目 force_login_before_run，不存在拒绝。"""
    root = _make_root(tmp_path)  # 原生 fixture：force_login_before_run=False

    set_instance_force_login(root, 1, True)
    entry = next(e for e in list_instances(root) if int(e["idx"]) == 1)
    assert entry["force_login_before_run"] is True

    set_instance_force_login(root, 1, False)
    entry = next(e for e in list_instances(root) if int(e["idx"]) == 1)
    assert entry["force_login_before_run"] is False

    try:
        set_instance_force_login(root, 99, True)
        raise AssertionError("不存在实例应被拒绝")
    except ValueError:
        pass


def test_set_active_instance_moves_active_flag(tmp_path: Path) -> None:
    """选择实例同步活跃：目标置 active，其余清 False；不存在实例拒绝。"""
    root = _make_root(tmp_path)  # 原生 fixture：idx=1 active
    add_instance(root, "第二个")
    assert find_active_instance(root)["idx"] == 1

    set_active_instance(root, 2)
    assert find_active_instance(root)["idx"] == 2
    by_idx = {int(e["idx"]): e for e in list_instances(root)}
    assert by_idx[1]["active"] is False
    assert by_idx[2]["active"] is True

    # 切回实例 1
    set_active_instance(root, 1)
    assert find_active_instance(root)["idx"] == 1

    try:
        set_active_instance(root, 99)
        raise AssertionError("不存在实例应被拒绝")
    except ValueError:
        pass


def test_native_instance_run_read_write_whitelist(tmp_path: Path) -> None:
    """直控运行实例：读原生 instance_run、白名单校验写回、缺失回退默认。"""

    root = _make_root(tmp_path)  # 原生 fixture 的 instance_run = "仅运行当前"

    assert read_native_instance_run(root) == "仅运行当前"

    # 白名单外取值拒绝
    try:
        save_native_instance_run(root, "单实例")
        raise AssertionError("应当抛出 ValueError")
    except ValueError:
        pass

    save_native_instance_run(root, "全部实例")
    assert read_native_instance_run(root) == INSTANCE_RUN_ALL

    # 缺失时回退「全部实例」（对齐上游 InstanceRun.ALL 默认：键缺失时
    # 实际行为就是跑全部实例，页面显示必须与之一致）
    write_file(root / "config" / "one_dragon.yml", {"instance_list": []})
    assert read_native_instance_run(root) == NATIVE_INSTANCE_RUN_OPTIONS[1]


def test_onedragon_backup_fingerprint_dedup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """直控前置备份：无备份即建、内容一致跳过、内容变化再建（指纹去重）。"""
    root = _make_root(tmp_path)
    # 备份根目录取 Path.cwd()/data，chdir 进 tmp 保证密封不污染真实 data
    monkeypatch.chdir(tmp_path)
    od_root = onedragon_backup_root(root)

    # 首次：无任何备份 → 立即归档
    first = archive_onedragon_backup(root)
    assert first is not None
    assert first.is_dir()
    assert (first / "one_dragon.yml").is_file()
    assert (first / "1" / "game_account.yml").is_file()
    # MAS 槽（名称带前缀）不进入原生备份
    assert not any("MAS-" in rel for rel in dir_files(first))

    # 内容一致：指纹相同 → 跳过（不新增时间戳）
    assert archive_onedragon_backup(root) is None
    assert len(list_times(od_root)) == 1

    # 内容变化：原生配置被改（如直控误操作改坏）→ 指纹不同 → 新建归档
    write_game_account(instance_dir(root, 1), {"game_region": "us"})
    second = archive_onedragon_backup(root)
    assert second is not None
    assert len(list_times(od_root)) == 2
    assert (second / "1" / "game_account.yml").read_text(encoding="utf-8").find(
        "us"
    ) != -1

    # force=True：即使内容一致也强制归档（恢复前存底语义）
    restored_marker = archive_onedragon_backup(root, force=True)
    assert restored_marker is not None
    assert len(list_times(od_root)) == 3


def test_archive_force_protects_existing_backups(tmp_path: Path) -> None:
    """恢复前 force 存底不清任何现存归档（``_archive`` 的 protect 语义）。

    用户选中 keep 之外的最旧一份恢复时：restore 链路先 force 归档当前
    配置，若该次归档把选中份清掉，``restore_dir`` 随即报「备份不存在」
    且那份备份永久丢失。
    """
    from app.utils.config_archive import _archive

    store = tmp_path / "pool"
    ts_book: list[str] = []
    for i in range(3):
        src = tmp_path / f"src{i}"
        src.mkdir()
        (src / "a.txt").write_text(f"v{i}", encoding="utf-8")
        dest = _archive({"a.txt": src / "a.txt"}, store, keep=2, force=True)
        assert dest is not None
        ts_book.append(dest.name)

    # 第 4 次 force 归档（keep=2）：已存在的 3 份全部受 protect，不被清理
    src3 = tmp_path / "src3"
    src3.mkdir()
    (src3 / "a.txt").write_text("v3", encoding="utf-8")
    assert _archive({"a.txt": src3 / "a.txt"}, store, keep=2, force=True) is not None
    times = list_times(store)
    assert len(times) == 4
    assert ts_book[0] in times

    # 非 force 归档正常执行保留清理：超出 keep 的最旧份被清掉（5 份 → keep 2 份）
    (src3 / "a.txt").write_text("v4", encoding="utf-8")
    assert _archive({"a.txt": src3 / "a.txt"}, store, keep=2, force=False) is not None
    times = list_times(store)
    assert len(times) == 2
    assert ts_book[0] not in times
    assert ts_book[1] not in times


def test_materialize_user_applist(tmp_path: Path) -> None:
    """退出归档前的编排物化：AppList 整表进槽 _group.yml，空/非法跳过。

    槽只有会话/运行注入才带编排；用户只在 MAS 页面保存过编排就退出的话，
    直接快照槽会漏掉它，恢复这种备份会把编排清空。
    """

    from app.task.ZzzOd.tools.backup_archive import materialize_user_applist

    slot = tmp_path / "14"
    write_file(slot / "game_account.yml", {"account": "主号"})

    applist = json.dumps(
        [
            {"app_id": "coffee", "enabled": True},
            {"app_id": "email", "enabled": False},
        ]
    )
    assert materialize_user_applist(slot, applist) is True
    assert read_app_group(slot) == [
        {"app_id": "coffee", "enabled": True},
        {"app_id": "email", "enabled": False},
    ]
    # 账号等既有文件不受影响
    assert read_game_account(slot)["account"] == "主号"

    # 空编排 / 非法 JSON：跳过不写盘
    assert materialize_user_applist(slot, "[]") is False
    assert materialize_user_applist(slot, "not-json") is False
    assert materialize_user_applist(slot, None) is False
    assert read_app_group(slot) == [
        {"app_id": "coffee", "enabled": True},
        {"app_id": "email", "enabled": False},
    ]


def test_materialize_user_fields_account_and_applist(tmp_path: Path) -> None:
    """归档前物化：账号字段与任务编排一并进槽（game_account.yml + _group.yml）。

    账号/编排只存在 MAS UserData，槽在会话/运行注入前并不带上它们——mas
    池所有归档点都必须先物化再快照，否则预览读取与恢复回填都会把账号字段
    清空（AppList 同款陷阱，账号也在内）。
    """

    class _FakeUserConfig:
        """最小桩：只支撑 ``get(section, field)`` 读取（对齐 user_field_patch）。"""

        _data = {
            "Game": {
                "GameRegion": "cn",
                "GamePath": r"G:\Games\ZZZ.exe",
                "GameLanguage": "cn",
                "Account": "17715817026",
                "Password": "secret",
                "BilibiliAccountName": "B站名",
                "UseCustomWinTitle": True,
            },
            "OneDragon": {
                "AppList": json.dumps(
                    [
                        {"app_id": "coffee", "enabled": True},
                        {"app_id": "email", "enabled": False},
                    ]
                )
            },
        }

        def get(self, section: str, field: str):
            return self._data.get(section, {}).get(field)

    slot = tmp_path / "14"
    # 槽里已有与 MAS 页面不同的区服（如 GUI 改过的残留）与未知字段
    write_file(slot / "game_account.yml", {"game_region": "us", "unrelated": 1})
    materialize_user_fields(slot, _FakeUserConfig())

    account = read_game_account(slot)
    assert account["account"] == "17715817026"
    assert account["password"] == "secret"
    assert account["game_path"] == r"G:\Games\ZZZ.exe"
    assert account["game_language"] == "cn"
    assert account["bilibili_account_name"] == "B站名"
    # 本页字段覆盖槽内残留；槽内未知字段保留
    assert account["game_region"] == "cn"
    assert account["unrelated"] == 1
    # 编排整表物化（含未启用项）
    assert read_app_group(slot) == [
        {"app_id": "coffee", "enabled": True},
        {"app_id": "email", "enabled": False},
    ]

    # 页面未填的字段不写入（不污染槽）：账号/编排缺省时槽内既有值保持
    class _PartialUserConfig:
        """最小桩：页面大部分字段为空的场景。"""

        _data = {
            "Game": {"GameRegion": "cn", "Account": "", "Password": ""},
            "OneDragon": {"AppList": "[]"},
        }

        def get(self, section: str, field: str):
            return self._data.get(section, {}).get(field)

    write_file(slot / "game_account.yml", {"account": "旧账号"})
    materialize_user_fields(slot, _PartialUserConfig())
    data = read_game_account(slot)
    assert data["account"] == "旧账号"  # 页面为空 → 不覆盖槽内既有账号
    # 已填写的字段仍会写入
    assert data["game_region"] == "cn"


def test_preview_account_fields_masks_password(tmp_path: Path) -> None:
    """预览账号字段：密码一律掩码不返回明文，其余字段缺失合并默认值。"""

    from app.core.config import AppConfig

    fields = {
        f["key"]: f["value"]
        for f in AppConfig._preview_account_fields(
            {"account": "abc", "password": "secret", "game_path": r"G:\a.exe"}
        )
    }
    assert fields["password"] == "••••••••"
    assert fields["account"] == "abc"
    assert fields["game_path"] == r"G:\a.exe"

    # 密码缺省：值为空（前端兜底 —），不返回任何明文
    empty = {f["key"]: f["value"] for f in AppConfig._preview_account_fields({})}
    assert empty["password"] == ""
    assert empty["game_region"] == "cn"  # 缺失合并默认值


def test_archive_mas_config_backup_materializes_account(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """统一归档入口：快照自带本页账号与编排（物化后落盘），不再需要调用方手工补。"""

    from app.task.ZzzOd.tools.backup_archive import list_mas_backups

    class _FakeUserConfig:
        _data = {
            "Game": {
                "GameRegion": "cn",
                "Account": "17715817026",
                "Password": "secret",
            },
            "OneDragon": {
                "AppList": json.dumps([{"app_id": "coffee", "enabled": True}])
            },
        }

        def get(self, section: str, field: str):
            return self._data.get(section, {}).get(field)

    root = _make_root(tmp_path)
    monkeypatch.chdir(tmp_path)
    script_id = "s-mas"
    slot = 1
    # 槽里原本是原生 fixture 的旧账号（主号账号）——统一入口应被本页账号覆盖后归档
    dest = archive_mas_config_backup(
        script_id, slot, instance_dir(root, slot), _FakeUserConfig()
    )
    assert dest is not None
    account = read_game_account(dest)
    assert account["account"] == "17715817026"
    assert account["password"] == "secret"
    assert read_app_group(dest) == [{"app_id": "coffee", "enabled": True}]
    times = list_mas_backups(script_id, slot)
    assert dest.name in times
