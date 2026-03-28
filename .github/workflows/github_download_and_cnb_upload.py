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
GitHub Actions 构建物下载和上传脚本

该脚本用于：
1. 从 GitHub Actions 下载指定运行（或最新成功运行）的构建物
2. 解压构建物到本地
3. 调用 cnb_release.py 上传文件到 CNB

使用方法：
    python github_download_and_cnb_upload.py --cnb-token YOUR_CNB_TOKEN [--github-token YOUR_GITHUB_TOKEN] [--run-id RUN_ID] [--target-commitish BRANCH] [--release-body BODY]

参数说明：
    --cnb-token: CNB API Token (必需)
    --github-token: GitHub Personal Access Token (可选，用于提高API限制)
    --run-id: 指定 GitHub Actions 运行 ID (可选，默认获取最新运行)
    --target-commitish: Release 关联的目标分支或提交 (可选，默认 main)
    --release-body: Release 描述正文 (可选，默认自动生成)

依赖：
- requests: HTTP 请求库
- tqdm: 进度条显示库

安装依赖：pip install -r requirements.txt
"""

import os
import sys
import json
import requests
import zipfile
import re
from pathlib import Path
from typing import List, Dict, Optional
from tqdm import tqdm

# 导入 CNBReleaseUploader
from cnb_release import CNBReleaseUploader


DEFAULT_OWNER = "AUTO-MAS-Project"
DEFAULT_REPO = "AUTO-MAS"
DEFAULT_WORKFLOW_FILE = "build-app.yml"
DEFAULT_PROJECT_PATH = "AUTO-MAS-Project/AUTO-MAS"
DEFAULT_ARTIFACT_NAMES = ["build-artifacts"]
DEFAULT_ASSET_GLOB = "AUTO-MAS-*-x64.zip"
DEFAULT_TARGET_COMMITISH = "main"


class GitHubActionsDownloader:
    def __init__(self, token: Optional[str] = None):
        """
        初始化 GitHub Actions 下载器

        Args:
            token: GitHub Personal Access Token (可选，用于提高API限制)
        """
        self.token = token
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "AUTO-MAS-Downloader/1.0.0",
        }
        if token:
            self.headers["Authorization"] = f"token {token}"

    def get_latest_workflow_run(
        self, owner: str, repo: str, workflow_file: str
    ) -> Optional[Dict]:
        """
        获取最新的工作流运行

        Args:
            owner: 仓库所有者
            repo: 仓库名称
            workflow_file: 工作流文件名

        Returns:
            最新的工作流运行信息或None
        """
        url = f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/{workflow_file}/runs"
        params = {"status": "completed", "conclusion": "success", "per_page": 1}

        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()

            data = response.json()
            runs = data.get("workflow_runs", [])

            if not runs:
                print("❌ 没有找到成功完成的工作流运行")
                return None

            latest_run = runs[0]
            print(f"✅ 找到最新的工作流运行:")
            print(f"   Run ID: {latest_run['id']}")
            print(f"   创建时间: {latest_run['created_at']}")
            print(f"   状态: {latest_run['status']} / {latest_run['conclusion']}")
            print(f"   分支: {latest_run['head_branch']}")

            return latest_run

        except requests.exceptions.RequestException as e:
            print(f"❌ 获取工作流运行失败: {e}")
            return None

    def get_artifacts(self, owner: str, repo: str, run_id: int) -> List[Dict]:
        """
        获取指定运行的构建物列表

        Args:
            owner: 仓库所有者
            repo: 仓库名称
            run_id: 运行ID

        Returns:
            构建物列表
        """
        url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}/artifacts"

        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()

            data = response.json()
            artifacts = data.get("artifacts", [])

            print(f"📦 找到 {len(artifacts)} 个构建物:")
            for artifact in artifacts:
                print(f"   - {artifact['name']} ({artifact['size_in_bytes']:,} bytes)")

            return artifacts

        except requests.exceptions.RequestException as e:
            print(f"❌ 获取构建物列表失败: {e}")
            return []

    def download_artifact(
        self,
        owner: str,
        repo: str,
        artifact_id: int,
        artifact_name: str,
        download_dir: str,
    ) -> Optional[str]:
        """
        下载指定的构建物

        Args:
            owner: 仓库所有者
            repo: 仓库名称
            artifact_id: 构建物ID
            artifact_name: 构建物名称
            download_dir: 下载目录

        Returns:
            下载的文件路径或None
        """
        url = f"https://api.github.com/repos/{owner}/{repo}/actions/artifacts/{artifact_id}/zip"

        try:
            print(f"📥 开始下载构建物: {artifact_name}")
            response = requests.get(url, headers=self.headers, stream=True)
            response.raise_for_status()

            # 获取文件总大小
            total_size = int(response.headers.get("content-length", 0))

            # 保存到临时文件
            zip_path = os.path.join(download_dir, f"{artifact_name}.zip")

            # 使用 tqdm 创建进度条
            chunk_size = 8192
            with open(zip_path, "wb") as f:
                with tqdm(
                    total=total_size,
                    unit="B",
                    unit_scale=True,
                    unit_divisor=1024,
                    desc=f"下载 {artifact_name}",
                    ncols=80,
                    bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
                ) as pbar:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))

            print(f"✅ 下载完成: {zip_path}")
            return zip_path

        except requests.exceptions.RequestException as e:
            print(f"❌ 下载构建物失败 ({artifact_name}): {e}")
            return None

    def extract_artifact(self, zip_path: str, extract_dir: str) -> List[str]:
        """
        解压构建物

        Args:
            zip_path: ZIP文件路径
            extract_dir: 解压目录

        Returns:
            解压出的文件列表
        """
        extracted_files = []

        try:
            print(f"📂 解压构建物: {os.path.basename(zip_path)}")
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(extract_dir)
                extracted_files = [
                    os.path.join(extract_dir, name) for name in zip_ref.namelist()
                ]

            print(f"✅ 解压完成，共 {len(extracted_files)} 个文件")
            for file_path in extracted_files:
                if os.path.isfile(file_path):
                    size = os.path.getsize(file_path)
                    print(f"   - {os.path.basename(file_path)} ({size:,} bytes)")

            return extracted_files

        except Exception as e:
            print(f"❌ 解压失败: {e}")
            return []


def extract_version_from_filename(filename: str) -> Optional[str]:
    """
    从文件名中提取版本号

    Args:
        filename: 文件名

    Returns:
        版本号或None
    """
    # 去除扩展名
    import os

    filename_without_ext = os.path.splitext(filename)[0]

    # 匹配版本号模式，如 v1.2.3, 1.2.3-alpha.1 等
    patterns = [
        r"v?([0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?)",
        r"_v?([0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?)",
    ]

    for pattern in patterns:
        match = re.search(pattern, filename_without_ext)
        if match:
            return match.group(1)

    return None


def create_cnb_config(
    files: List[str],
    version: str,
    token: str,
    project_path: str = DEFAULT_PROJECT_PATH,
    target_commitish: str = DEFAULT_TARGET_COMMITISH,
    release_body: Optional[str] = None,
) -> Dict:
    """
    创建CNB上传配置

    Args:
        files: 要上传的文件列表
        version: 版本号
        token: CNB token

    Returns:
        CNB配置字典
    """
    normalized_version = version.lstrip("vV")

    # 判断是否为预发布版本
    is_prerelease = "-" in normalized_version
    make_latest = not is_prerelease
    body = release_body or f"AUTO-MAS v{normalized_version} 自动发布"

    config = {
        "token": token,
        "project_path": project_path,
        "base_url": "https://api.cnb.cool",
        "overwrite": True,
        "release_data": {
            "tag_name": f"v{normalized_version}",
            "name": f"AUTO-MAS v{normalized_version}",
            "body": body,
            "draft": False,
            "prerelease": is_prerelease,
            "target_commitish": target_commitish,
            "make_latest": make_latest,
        },
        "asset_files": files,
    }

    return config


def main():
    import argparse

    # 解析命令行参数
    parser = argparse.ArgumentParser(description="AUTO-MAS 构建物下载和上传工具")
    parser.add_argument(
        "--run-id",
        type=str,
        help="指定 GitHub Actions 运行 ID，如果提供则不会获取最新运行",
    )
    parser.add_argument("--owner", default=DEFAULT_OWNER, help="GitHub 仓库所有者")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="GitHub 仓库名称")
    parser.add_argument(
        "--workflow-file", default=DEFAULT_WORKFLOW_FILE, help="工作流文件名"
    )
    parser.add_argument(
        "--project-path", default=DEFAULT_PROJECT_PATH, help="CNB 项目路径"
    )
    parser.add_argument(
        "--target-commitish",
        default=DEFAULT_TARGET_COMMITISH,
        help="Release 对应的目标分支或提交，默认 main",
    )
    parser.add_argument(
        "--release-body",
        type=str,
        default=None,
        help="Release 描述正文，不传则使用默认描述",
    )
    parser.add_argument(
        "--artifact-name",
        action="append",
        default=[],
        help="要下载的 Actions 构建物名称，可重复传入；默认 build-artifacts",
    )
    parser.add_argument("--github-token", type=str, help="GitHub Personal Access Token")
    parser.add_argument(
        "--cnb-token", type=str, required=True, help="CNB API Token (必需)"
    )
    args = parser.parse_args()

    print("🚀 AUTO-MAS 构建物下载和上传工具")
    print("=" * 50)

    target_artifact_names = args.artifact_name or DEFAULT_ARTIFACT_NAMES

    # 获取 token，优先使用命令行参数，其次使用环境变量
    github_token = args.github_token or os.getenv("GITHUB_TOKEN")
    cnb_token = args.cnb_token or os.getenv("CNB_TOKEN")

    if not cnb_token:
        print("❌ 错误: 请设置 CNB_TOKEN 环境变量")
        return 1

    if not github_token:
        print("⚠️  警告: 未设置 GITHUB_TOKEN，可能会遇到API限制")

    # 确定运行 ID
    if args.run_id:
        print(f"\n🎯 使用指定的运行 ID: {args.run_id}")
        run_id = args.run_id
    else:
        # 创建下载器来获取最新运行 ID
        downloader = GitHubActionsDownloader(github_token)
        print("\n🔍 查找最新的工作流运行...")
        latest_run = downloader.get_latest_workflow_run(
            args.owner, args.repo, args.workflow_file
        )
        if not latest_run:
            return 1
        run_id = str(latest_run["id"])

    # 使用当前目录下的固定目录，以action运行ID命名
    work_dir = Path.cwd() / "github_actions_cache" / run_id
    download_dir = work_dir / "downloads"
    extract_dir = work_dir / "extracted"

    print(f"\n📁 使用工作目录: {work_dir}")

    # 检查是否已存在解压后的文件
    all_files = []
    version = None

    # 检查解压目录是否已存在且包含文件
    if extract_dir.exists():
        print("🔍 检查已存在的构建物...")
        existing_files: List[str] = []

        for artifact_name in target_artifact_names:
            artifact_extract_dir = extract_dir / artifact_name
            if not artifact_extract_dir.exists():
                continue

            # build-app.yml 的 build-artifacts 产物内是 AUTO-MAS-*-x64.zip
            for file_path in artifact_extract_dir.rglob(DEFAULT_ASSET_GLOB):
                existing_files.append(str(file_path))
                if not version:
                    extracted_version = extract_version_from_filename(file_path.name)
                    if extracted_version:
                        version = extracted_version

        if existing_files and version:
            print(f"✅ 发现已存在的构建物 ({len(existing_files)} 个文件)，跳过下载")
            print(f"📋 检测到版本号: {version}")
            all_files = existing_files
        else:
            print("⚠️  已存在目录但未找到有效文件，将重新下载")

    # 如果没有找到已存在的文件，则进行下载和解压
    if not all_files:
        print("📥 需要下载构建物，正在获取构建物信息...")

        # 如果还没有创建下载器，现在创建
        if "downloader" not in locals():
            downloader = GitHubActionsDownloader(github_token)

        # 获取构建物列表
        print("\n📦 获取构建物列表...")
        artifacts = downloader.get_artifacts(args.owner, args.repo, int(run_id))
        if not artifacts:
            return 1

        # 筛选需要的构建物
        target_artifacts = []
        for artifact in artifacts:
            if artifact["name"] in target_artifact_names:
                target_artifacts.append(artifact)

        found_names = {artifact["name"] for artifact in target_artifacts}
        missing_artifacts = [
            name for name in target_artifact_names if name not in found_names
        ]
        if missing_artifacts:
            print(
                f"❌ 错误: 缺少构建物 {missing_artifacts}，实际找到 {list(found_names)}"
            )
            return 1

        print("📥 开始下载和解压构建物...")
        download_dir.mkdir(parents=True, exist_ok=True)
        extract_dir.mkdir(parents=True, exist_ok=True)

        for artifact in target_artifacts:
            # 下载
            zip_path = downloader.download_artifact(
                args.owner,
                args.repo,
                artifact["id"],
                artifact["name"],
                str(download_dir),
            )

            if not zip_path:
                continue

            # 解压
            artifact_extract_dir = extract_dir / artifact["name"]
            artifact_extract_dir.mkdir(parents=True, exist_ok=True)

            extracted_files = downloader.extract_artifact(
                zip_path, str(artifact_extract_dir)
            )

            # 按本项目构筑产物格式筛选上传文件
            for file_path in (Path(artifact_extract_dir)).rglob(DEFAULT_ASSET_GLOB):
                all_files.append(str(file_path))
                if not version:
                    extracted_version = extract_version_from_filename(file_path.name)
                    if extracted_version:
                        version = extracted_version
                        print(f"📋 检测到版本号: {version}")

    if not all_files:
        print("❌ 错误: 没有找到可上传的文件")
        return 1

    if not version:
        print("❌ 错误: 无法从文件名中提取版本号")
        return 1

    # 去重并过滤不存在文件，避免重复上传或路径异常
    normalized_files: List[str] = []
    seen_files = set()
    for file_path in all_files:
        p = Path(file_path)
        if not p.is_file():
            continue
        normalized = str(p.resolve())
        if normalized in seen_files:
            continue
        seen_files.add(normalized)
        normalized_files.append(normalized)

    all_files = normalized_files

    if not all_files:
        print("❌ 错误: 可上传文件列表为空")
        return 1

    print(f"\n📋 准备上传 {len(all_files)} 个文件:")
    for file_path in all_files:
        p = Path(file_path)
        size = p.stat().st_size
        print(f"   - {p.name} ({size:,} bytes)")

    # 创建CNB配置
    print("\n⚙️  创建CNB配置...")
    cnb_config = create_cnb_config(
        files=all_files,
        version=version,
        token=cnb_token,
        project_path=args.project_path,
        target_commitish=args.target_commitish,
        release_body=args.release_body,
    )

    # 打印脱敏后的配置，便于排查参数传递问题
    debug_config = dict(cnb_config)
    debug_config["token"] = "***"
    print("\n🧪 CNB 配置 JSON (调试):")
    print(json.dumps(debug_config, indent=2, ensure_ascii=False))

    # 保存配置文件
    config_path = work_dir / "cnb_config.json"
    with config_path.open("w", encoding="utf-8") as f:
        json.dump(cnb_config, f, indent=2, ensure_ascii=False)

    print(f"✅ 配置文件已保存: {config_path}")

    # 直接调用 CNBReleaseUploader
    print("\n🚀 开始上传到CNB...")

    try:
        # 创建 CNBReleaseUploader 实例
        uploader = CNBReleaseUploader(
            token=cnb_config["token"],
            base_url=cnb_config.get("base_url", "https://api.cnb.cool"),
        )

        # 创建 release
        print(f"📝 创建 release: {cnb_config['release_data']['name']}")
        release_result = uploader.create_release(
            project_path=cnb_config["project_path"],
            release_data=cnb_config["release_data"],
        )

        if not release_result:
            print("❌ 创建 release 失败")
            return 1

        print(f"✅ Release 创建成功: {release_result['name']}")

        # 上传文件
        print(f"📤 开始上传 {len(cnb_config['asset_files'])} 个文件...")
        upload_results = uploader.upload_multiple_assets(
            project_path=cnb_config["project_path"],
            release_id=release_result["id"],
            asset_files=cnb_config["asset_files"],
            overwrite=cnb_config.get("overwrite", True),
        )

        # 检查上传结果
        success_count = sum(1 for result in upload_results if result)
        total_count = len(upload_results)

        print(f"\n📊 上传结果汇总:")
        print(f"   ✅ 成功: {success_count}/{total_count}")

        if success_count < total_count:
            print(f"   ❌ 失败: {total_count - success_count}/{total_count}")
            for i, result in enumerate(upload_results):
                if not result:
                    file_name = Path(cnb_config["asset_files"][i]).name
                    print(f"      - {file_name}: 上传失败")

        if success_count == total_count:
            print("\n🎉 所有文件上传完成!")
            return 0
        else:
            print("\n❌ 部分文件上传失败")
            return 1

    except Exception as e:
        print(f"❌ CNB上传失败: {e}")
        return 1


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⚠️  用户中断操作")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 程序异常: {e}")
        sys.exit(1)
