#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

"""MSS（星塔旅人）项目认领判据回归测试（纯函数，无 I/O）。

官方版与个人版等衍生版认成同一个脚本类型（MSSConfig）；无关项目必须落到通用 MaaFW。
判据只看 interface 的三个字段，所以用字典喂入即可。
"""

from app.task.MSS.flavor import github_repo_name, is_mss_project

OFFICIAL = {
    "name": "MaaStellaSora",
    "github": "https://github.com/MaaStellaSora/MaaStellaSora",
    "mirrorchyan_rid": "SSAH",
}
PERSONAL = {
    "name": "MaaStellaSora-Personal",
    "github": "https://github.com/beichen24a1/MaaStellaSora-Personal",
}


def test_official_project_is_claimed() -> None:
    assert is_mss_project(OFFICIAL) is True


def test_personal_project_is_claimed() -> None:
    assert is_mss_project(PERSONAL) is True


def test_project_name_alone_is_enough() -> None:
    assert is_mss_project({"name": "MaaStellaSora"}) is True
    assert is_mss_project({"name": "maastellasora-personal"}) is True


def test_github_repo_alone_is_enough() -> None:
    assert (
        is_mss_project(
            {"github": "https://github.com/beichen24a1/MaaStellaSora-Personal"}
        )
        is True
    )
    assert (
        is_mss_project({"github": "https://github.com/MaaStellaSora/MaaStellaSora.git"})
        is True
    )


def test_unrelated_project_is_not_claimed() -> None:
    assert (
        is_mss_project({"name": "OtherProject", "github": "https://github.com/foo/bar"})
        is False
    )
    assert is_mss_project({}) is False
    ## 名字只是以 MSS 字样开头但并非本项目的，不认领
    assert is_mss_project({"name": "MaaStellaSoraX"}) is False


def test_github_repo_name_parsing() -> None:
    assert (
        github_repo_name("https://github.com/MaaStellaSora/MaaStellaSora")
        == "MaaStellaSora"
    )
    assert (
        github_repo_name("https://github.com/MaaStellaSora/MaaStellaSora.git")
        == "MaaStellaSora"
    )
    assert (
        github_repo_name("https://github.com/beichen24a1/MaaStellaSora-Personal/")
        == "MaaStellaSora-Personal"
    )
    assert github_repo_name("") == ""
    assert github_repo_name("MaaStellaSora") == ""
