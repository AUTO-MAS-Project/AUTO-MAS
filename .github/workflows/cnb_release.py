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
CNB Release Uploader

依赖:
- requests
- tqdm

安装依赖:
pip install requests tqdm
"""

import os
import json
import requests
import time
import sys
import argparse
from typing import List, Dict, Optional
from pathlib import Path
from tqdm import tqdm


class CNBReleaseUploader:
    def __init__(self, token: str, base_url: str = "https://api.cnb.cool"):
        """
        初始化CNB Release上传器

        Args:
            token: 认证token
            base_url: API基础URL
        """
        self.token = token
        self.base_url = base_url
        self.headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "CNB-Release-Uploader/1.0.0",
            "Host": "api.cnb.cool",
            "Connection": "keep-alive",
        }

    def create_release(self, project_path: str, release_data: Dict) -> Optional[Dict]:
        """
        创建一个新的release

        Args:
            project_path: 项目路径
            release_data: release数据

        Returns:
            创建的release信息或None
        """
        url = f"{self.base_url}/{project_path}/-/releases"

        # 打印请求信息
        print("\n📋 请求头 (Headers):")
        for key, value in self.headers.items():
            print(f"  {key}: {value}")

        try:
            response = requests.post(url, headers=self.headers, json=release_data)
            response.raise_for_status()

            release_info = response.json()
            print(f"✅ Release创建成功: {release_info.get('name', 'N/A')}")
            print(f"   Release ID: {release_info.get('id', 'N/A')}")
            print(f"   Tag Name: {release_info.get('tag_name', 'N/A')}")
            print(f"   Created At: {release_info.get('created_at', 'N/A')}")
            print(f"   Is Latest: {release_info.get('is_latest', False)}")
            return release_info

        except requests.exceptions.RequestException as e:
            print(f"❌ 创建release失败: {e}")
            if hasattr(e, "response") and e.response is not None:
                print(f"   状态码: {e.response.status_code}")
                print(f"   响应内容: {e.response.text}")
            return None

    def get_asset_upload_url(
        self,
        project_path: str,
        release_id: str,
        asset_name: str,
        file_size: int,
        overwrite: bool = True,
    ) -> Optional[Dict]:
        """
        获取asset上传URL

        Args:
            project_path: 项目路径
            release_id: release ID
            asset_name: asset名称
            file_size: 文件大小
            overwrite: 是否覆盖现有文件

        Returns:
            包含upload_url等信息的字典或None
        """
        url = f"{self.base_url}/{project_path}/-/releases/{release_id}/asset-upload-url"

        data = {"asset_name": asset_name, "overwrite": overwrite, "size": file_size}

        try:
            response = requests.post(url, headers=self.headers, json=data)
            response.raise_for_status()

            upload_info = response.json()
            print(f"✅ 获取上传URL成功")
            return upload_info

        except requests.exceptions.RequestException as e:
            print(f"❌ 获取上传URL失败 ({asset_name}): {e}")
            if hasattr(e, "response") and e.response is not None:
                print(f"   状态码: {e.response.status_code}")
                print(f"   响应内容: {e.response.text}")
            return None

    def upload_asset(
        self, upload_url: str, file_path: str, show_progress: bool = True
    ) -> bool:
        """
        上传asset文件

        Args:
            upload_url: 上传URL
            file_path: 本地文件路径
            show_progress: 是否显示上传进度条

        Returns:
            是否上传成功
        """
        if not os.path.exists(file_path):
            print(f"❌ 文件不存在: {file_path}")
            return False

        upload_headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
        }

        file_size = os.path.getsize(file_path)
        file_name = os.path.basename(file_path)

        try:
            with open(file_path, "rb") as file:
                if show_progress and file_size > 0:
                    # 创建进度条
                    progress_bar = tqdm(
                        total=file_size,
                        unit="B",
                        unit_scale=True,
                        unit_divisor=1024,
                        desc=f"📤 上传 {file_name}",
                        ncols=80,
                        bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
                    )

                    # 创建一个包装器来更新进度条
                    class ProgressFileWrapper:
                        def __init__(self, file_obj, progress_bar):
                            self.file_obj = file_obj
                            self.progress_bar = progress_bar

                        def read(self, size=-1):
                            data = self.file_obj.read(size)
                            if data:
                                self.progress_bar.update(len(data))
                            return data

                        def __getattr__(self, name):
                            return getattr(self.file_obj, name)

                    wrapped_file = ProgressFileWrapper(file, progress_bar)
                    response = requests.put(
                        upload_url, headers=upload_headers, data=wrapped_file
                    )
                    progress_bar.close()
                else:
                    response = requests.put(
                        upload_url, headers=upload_headers, data=file
                    )

                response.raise_for_status()

            print(f"📤 上传到 {upload_url} 返回结果: {response.status_code}")

            try:
                response_data = response.json()
                print(
                    f"   响应内容 (JSON): {json.dumps(response_data, indent=2, ensure_ascii=False)}"
                )
            except (json.JSONDecodeError, ValueError):
                print(f"   响应内容 (文本): {response.text}")

            return True

        except requests.exceptions.RequestException as e:
            print(f"❌ 文件上传失败 ({os.path.basename(file_path)}): {e}")
            if hasattr(e, "response") and e.response is not None:
                print(f"   响应状态码: {e.response.status_code}")
                print(f"   响应内容: {e.response.text}")
            return False

    def verify_upload(self, verify_url: str) -> bool:
        """
        验证上传是否成功

        Args:
            verify_url: 验证URL

        Returns:
            是否验证成功
        """
        try:
            response = requests.post(verify_url, headers=self.headers)
            response.raise_for_status()

            print(f"🔍 验证请求返回状态: {response.status_code}")

            try:
                response_data = response.json()
                print(
                    f"   响应内容 (JSON): {json.dumps(response_data, indent=2, ensure_ascii=False)}"
                )
            except (json.JSONDecodeError, ValueError):
                print(f"   响应内容 (文本): {response.text}")

            return True

        except requests.exceptions.RequestException as e:
            print(f"❌ 验证上传失败: {e}")
            if hasattr(e, "response") and e.response is not None:
                print(f"   验证状态码: {e.response.status_code}")
                print(f"   验证响应内容: {e.response.text}")
            return False

    def upload_multiple_assets(
        self,
        project_path: str,
        release_id: str,
        asset_files: List[str],
        overwrite: bool = True,
        show_progress: bool = True,
    ) -> List[bool]:
        """
        上传多个assets

        Args:
            project_path: 项目路径
            release_id: release ID
            asset_files: asset文件路径列表
            overwrite: 是否覆盖现有文件
            show_progress: 是否显示进度条

        Returns:
            每个文件的上传结果列表
        """
        results = []

        print(f"\n📦 开始上传 {len(asset_files)} 个文件到release {release_id}...")

        # 计算总文件大小用于整体进度显示
        total_size = 0
        valid_files = []
        for file_path in asset_files:
            if os.path.exists(file_path):
                total_size += os.path.getsize(file_path)
                valid_files.append(file_path)

        if show_progress and valid_files:
            print(
                f"📊 总计 {len(valid_files)} 个有效文件，总大小: {total_size / 1024 / 1024:.2f} MB"
            )
            print("" + "=" * 60)

        for i, file_path in enumerate(asset_files, 1):
            if not os.path.exists(file_path):
                print(f"❌ [{i}/{len(asset_files)}] 跳过不存在的文件: {file_path}")
                results.append(False)
                continue

            file_size = os.path.getsize(file_path)
            asset_name = os.path.basename(file_path)

            print(f"\n📁 [{i}/{len(asset_files)}] 处理文件: {asset_name}")
            print(
                f"   文件大小: {file_size:,} bytes ({file_size / 1024 / 1024:.2f} MB)"
            )

            # 1. 获取上传URL
            upload_info = self.get_asset_upload_url(
                project_path, release_id, asset_name, file_size, overwrite
            )

            if not upload_info:
                results.append(False)
                continue

            # 2. 上传文件
            upload_success = self.upload_asset(
                upload_info["upload_url"], file_path, show_progress
            )
            time.sleep(1)

            # 3. 验证上传（如果有验证URL）
            final_success = upload_success
            if upload_success and "verify_url" in upload_info:
                verify_success = self.verify_upload(upload_info["verify_url"])
                final_success = verify_success
                if verify_success:
                    print(f"✅ 文件 {asset_name} 上传并验证成功")
                else:
                    print(f"❌ 文件 {asset_name} 上传成功但验证失败")
            elif upload_success:
                print(f"✅ 文件 {asset_name} 上传成功（无需验证）")

            results.append(final_success)

            # 避免请求过快
            if i < len(asset_files):
                time.sleep(1)

        return results


def load_config_from_json(json_input: str) -> Dict:
    """
    从JSON字符串或文件路径加载配置

    Args:
        json_input: JSON字符串或JSON文件路径

    Returns:
        配置字典
    """
    try:
        # 首先尝试作为JSON字符串解析
        config = json.loads(json_input)
        print("✅ 从JSON字符串加载配置成功")
        return config
    except json.JSONDecodeError:
        # 如果失败，尝试作为文件路径
        try:
            if os.path.exists(json_input):
                with open(json_input, "r", encoding="utf-8") as f:
                    config = json.load(f)
                print(f"✅ 从文件 {json_input} 加载配置成功")
                return config
            else:
                raise FileNotFoundError(f"配置文件不存在: {json_input}")
        except Exception as e:
            raise ValueError(f"无法解析JSON配置: {e}")


def validate_config(config: Dict) -> None:
    """
    验证配置的必需字段

    Args:
        config: 配置字典

    Raises:
        ValueError: 如果配置无效
    """
    required_fields = ["token", "project_path", "release_data"]
    for field in required_fields:
        if field not in config:
            raise ValueError(f"缺少必需字段: {field}")

    # 验证release_data必需字段
    release_required = ["tag_name", "name"]
    for field in release_required:
        if field not in config["release_data"]:
            raise ValueError(f"release_data缺少必需字段: {field}")

    # 验证asset_files
    if "asset_files" in config and not isinstance(config["asset_files"], list):
        raise ValueError("asset_files必须是数组")


def main():
    parser = argparse.ArgumentParser(description="CNB Release Uploader - JSON配置版本")
    parser.add_argument("config", help="JSON配置字符串或JSON配置文件路径")
    parser.add_argument("--dry-run", action="store_true", help="只验证配置，不执行上传")
    parser.add_argument("--no-progress", action="store_true", help="禁用上传进度条显示")

    args = parser.parse_args()

    try:
        # 加载配置
        print("🔧 加载配置...")
        config = load_config_from_json(args.config)

        # 验证配置
        print("🔍 验证配置...")
        validate_config(config)

        # 打印配置信息
        print("\n📋 配置信息:")
        print(f"   Token: {'*' * 20}")
        print(f"   项目路径: {config['project_path']}")
        print(f"   Release名称: {config['release_data']['name']}")
        print(f"   Tag名称: {config['release_data']['tag_name']}")
        print(f"   Asset文件数量: {len(config.get('asset_files', []))}")

        if args.dry_run:
            print("\n🧪 Dry-run模式，配置验证通过，退出程序")
            return 0

        # 创建上传器实例
        uploader = CNBReleaseUploader(
            token=config["token"],
            base_url=config.get("base_url", "https://api.cnb.cool"),
        )

        # 1. 创建release
        print("\n🚀 开始创建release...")
        release_info = uploader.create_release(
            config["project_path"], config["release_data"]
        )

        if not release_info:
            print("❌ 创建release失败，退出程序")
            return 1

        release_id = release_info.get("id")
        if not release_id:
            print("❌ 无法获取release ID，退出程序")
            return 1

        # 2. 上传assets（如果有）
        asset_files = config.get("asset_files", [])
        if asset_files:
            overwrite = config.get("overwrite", True)
            show_progress = (
                not args.no_progress
            )  # 默认显示进度条，除非指定 --no-progress
            results = uploader.upload_multiple_assets(
                config["project_path"],
                release_id,
                asset_files,
                overwrite,
                show_progress,
            )

            # 3. 显示结果
            print("\n" + "=" * 50)
            print("📊 上传结果汇总:")
            print("=" * 50)

            success_count = sum(results)
            total_count = len(results)

            for i, (file_path, success) in enumerate(zip(asset_files, results)):
                status = "✅ 成功" if success else "❌ 失败"
                print(f"   [{i + 1}] {status} - {os.path.basename(file_path)}")

            print(f"\n🎉 完成! 成功上传 {success_count}/{total_count} 个文件")

            if success_count == total_count:
                print("🎊 所有文件都上传成功!")
                return 0
            elif success_count > 0:
                print("⚠️  部分文件上传成功，请检查失败的文件")
                return 2
            else:
                print("💥 所有文件上传失败，请检查配置和网络")
                return 1
        else:
            print("\n📦 没有指定asset文件，只创建了release")
            return 0

    except Exception as e:
        print(f"❌ 程序执行失败: {e}")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
