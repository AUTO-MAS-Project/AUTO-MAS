#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

from app.task.BetterGI.tools import account_switch
from app.utils.io import read_file, write_file


def _seed(root):
    """搭一个最小的假 BetterGI RootPath（订阅文件 + 主配置 + 可选的仓库/脚本目录）。"""
    (root / "User" / "Subscriptions").mkdir(parents=True)
    write_file(
        root / "User" / "Subscriptions" / "bettergi-scripts-list.json",
        [],
    )
    write_file(root / "User" / "config.json", {})


def test_deleted_script_forces_repo_and_resubscribes(tmp_path) -> None:
    """用户误删脚本（目录缺失）→ 强制清空本地仓库逼 BGI 重建，并重新订阅。"""
    root = tmp_path
    _seed(root)

    # 脚本不存在（被误删 / 初次使用）
    repo_dir = root / "Repos" / "bettergi-scripts-list"
    repo_dir.mkdir(parents=True)
    (repo_dir / "repo.json").write_text("{}", encoding="utf-8")

    result = account_switch.ensure_switch_subscription(root)

    assert result is False
    # 本地仓库副本被清掉，BGI 下次启动重检出
    assert not repo_dir.exists()
    # 订阅被重新补回
    data = read_file(
        root / "User" / "Subscriptions" / "bettergi-scripts-list.json"
    )
    assert account_switch._SCRIPT_REPO_PATH in data
    # 自动更新开关被打开、渠道固定 CNB
    config = read_file(root / "User" / "config.json")
    assert config["scriptConfig"]["autoUpdateBeforeCommandLineRun"] is True
    assert config["scriptConfig"]["autoUpdateSubscribedScripts"] is True
    assert config["scriptConfig"]["selectedChannelName"] == "CNB"


def test_present_script_keeps_repo(tmp_path) -> None:
    """脚本已就绪 → 不删除本地仓库，正常返回 True。"""
    root = tmp_path
    _seed(root)
    repo_dir = root / "Repos" / "bettergi-scripts-list"
    repo_dir.mkdir(parents=True)
    (root / "User" / "JsScript" / "SwitchAccountMultipleMode").mkdir(
        parents=True
    )

    result = account_switch.ensure_switch_subscription(root)

    assert result is True
    assert repo_dir.exists()  # 脚本在时不做强制重建