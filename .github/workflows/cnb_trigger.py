#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file incorporates work covered by the following copyright and
#   permission notice:
#
#       better-genshin-impact Copyright © 2023-2026 babalae
#       https://github.com/babalae/better-genshin-impact

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AUTO-MAS Build Trigger Script
用于触发 CNB 构建的 Python 脚本
"""

import requests
import json
import sys
import argparse


def build_cnb_headers(token: str) -> dict[str, str]:
    """统一构建 CNB API 请求头。"""
    return {
        "Accept": "application/vnd.cnb.api+json",
        "Authorization": token,
        "Content-Type": "application/json",
        "User-Agent": "CNB-API-Client/1.0.0",
    }


def trigger_build(
    token,
    branch="main",
    event="api_trigger_one",
    runid=None,
    release_body=None,
    version_tag=None,
    is_prerelease=None,
):
    """
    触发构建请求

    Args:
        token (str): 授权token
        branch (str): 分支名称，默认为 main
        event (str): 事件类型，默认为api_trigger_one
        runid (str): 运行ID，可选参数
        release_body (str): Release 描述正文，可选参数
        version_tag (str): 版本号，可选参数
        is_prerelease (str): 是否预发布(true/false)，可选参数

    Returns:
        dict: API响应结果
    """
    url = f"https://api.cnb.cool/AUTO-MAS-Project/AUTO-MAS/-/build/start"

    headers = build_cnb_headers(token)

    data: dict[str, object] = {"branch": branch, "event": event}

    env: dict[str, str] = {}
    if runid:
        env["RUN_ID"] = runid
    if release_body:
        env["RELEASE_BODY"] = release_body
    if version_tag:
        env["VERSION_TAG"] = version_tag
    if is_prerelease:
        env["IS_PRERELEASE"] = is_prerelease
    if env:
        data["env"] = env

    try:
        print(f"正在发起构建请求...")
        print(f"URL: {url}")

        print(f"请求体: {json.dumps(data, indent=2, ensure_ascii=False)}")

        response = requests.post(url, headers=headers, json=data)

        print(f"响应状态码: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print("构建触发成功!")
            print(f"响应内容: {json.dumps(result, indent=2, ensure_ascii=False)}")
            return result
        else:
            print(f"请求失败: {response.status_code}")
            print(f"错误信息: {response.text}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"请求异常: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"JSON解析错误: {e}")
        print(f"响应内容: {response.text}")
        return None


def main():
    parser = argparse.ArgumentParser(description="触发 AUTO-MAS 的 CNB 构建")
    parser.add_argument("token", help="授权token")
    parser.add_argument("--branch", default="main", help="分支名称 (默认: main)")
    parser.add_argument(
        "--event", default="api_trigger_one", help="事件类型 (默认: api_trigger_one)"
    )
    parser.add_argument("--runid", help="运行ID (可选)")
    parser.add_argument("--release-body", help="Release 描述正文 (可选)")
    parser.add_argument("--version-tag", help="版本号 (可选)")
    parser.add_argument(
        "--is-prerelease", choices=["true", "false"], help="是否预发布 (可选)"
    )

    args = parser.parse_args()

    if not args.token:
        print("错误: 必须提供token参数")
        sys.exit(1)

    result = trigger_build(
        args.token,
        args.branch,
        args.event,
        args.runid,
        args.release_body,
        args.version_tag,
        args.is_prerelease,
    )

    if result is None:
        sys.exit(1)


if __name__ == "__main__":
    main()
