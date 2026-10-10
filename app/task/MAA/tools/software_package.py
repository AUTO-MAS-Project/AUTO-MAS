#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.
#
#   Contact: DLmaster_361@163.com


"""MAA 本体更新包原语：共享缓存、完整包校验、待更新登记。

与 resource_package.py（资源包合并）平行的本体包最小实现，只做三件事：
- 共享缓存：``data/maa_update/software/{os}/{arch}/{channel}/`` 下每个通道
  架构只保留一个最新有效完整包（package.zip + manifest.json）；
- 完整包校验：zip 可读、条目路径安全、根目录无 OTA 清单、关键程序集存在；
- 待更新登记：点读点写新旧两份 MAA 配置的待更新字段，包复制成功后才写
  ``Update.Name``/``Update.UpdatePackage``（新版）或 ``Global.VersionUpdate.
  name``/``package``（旧版），已有合法登记一律保护，值经手语义不过手。

上游对齐点（MaaAssistantArknights dev-v2）：登记字段是 Bootstrapper 启动
应用的唯一开关（PendingUpdateApplier.HasPendingUpdatePackage 要求 Name 与
UpdatePackage 同时非空且包文件存在）；完整包文件名沿用上游 Mirror 酱下载
路径的 ``MirrorChyanApp<版本>.zip``；登记使用绝对路径（上游 GetPlanned
UpdatePackagePath 同款）；根目录出现 ``removelist.txt``/``changes.json``
即 OTA 包（HasOtaMetadata 判据）——启动应用路径不校验包基准版本，本模块
的拒收是唯一防线，因此只接受完整包。

归属判定与合规边界见 software_update.py 模块头。
"""

from __future__ import annotations

import os
import re
import shutil
import zipfile
from pathlib import Path

from app.utils import get_logger
from app.utils.io import ConfigCorruptedError, read_dict_file, write_file

# 复用资源包的同款原语（哈希与覆盖式复制），避免第二套实现
from .resource_package import _copy_if_changed, _file_sha256

logger = get_logger("MAA 本体更新")

# 上游 OTA 包的根目录清单文件（PendingUpdateApplier.HasOtaMetadata 判据）
_OTA_MANIFEST_ENTRIES = frozenset({"removelist.txt", "changes.json"})
# 官方发行包根目录必备的 GUI 托管程序集与启动器
_ESSENTIAL_ENTRIES = frozenset({"maa.exe", "maa.dll"})
_FULL_PACKAGE_PREFIX = "MirrorChyanApp"
# 上游写入 MAA 安装根目录的委托安装失败标志（PendingUpdateApplier 声明）
_FAILURE_FLAG_FILE = "pending-update-failure.txt"
# 完整包安装峰值占用 ≈ 包 + 解压临时目录 + .old 备份（MaaUpdater 换血语义）
_FREE_SPACE_SCALE = 3
_ILLEGAL_NAME_RE = re.compile(r'[\\/:*?"<>|]')


# --------------------------------------------------------------------------
# 共享缓存
# --------------------------------------------------------------------------


def software_cache_dir(os_name: str, arch: str, channel: str) -> Path:
    """本体更新共享缓存目录：按系统、架构、通道隔离，互不覆盖。"""
    return Path.cwd() / "data" / "maa_update" / "software" / os_name / arch / channel


def load_cache_manifest(cache_dir: Path) -> dict[str, str] | None:
    """读缓存清单；缺失、损坏或字段不全返回 None（缓存是 MAS 自产数据，
    按「无缓存、重建自愈」处理，不视为错误）。"""
    try:
        manifest = read_dict_file(cache_dir / "manifest.json")
    except Exception:
        return None
    fields = ("version", "channel", "os", "arch", "package_type", "sha256")
    if any(
        not isinstance(manifest.get(key), str) or not manifest[key] for key in fields
    ):
        return None
    if manifest["package_type"] != "full":
        return None
    return {key: str(manifest[key]) for key in fields}


def cache_zip_matches(cache_dir: Path, manifest: dict[str, str]) -> bool:
    """复核缓存包仍在且内容与清单一致（线程内执行，全量哈希）。"""
    package = cache_dir / "package.zip"
    try:
        return package.is_file() and _file_sha256(package) == manifest["sha256"]
    except OSError:
        return False


def store_cache(
    cache_dir: Path, part: Path, fields: dict[str, str], sha256: str
) -> None:
    """校验通过的包原子入缓存；换位顺序对齐 resource_update._build_stage：

    1. 动旧包之前先删 manifest——半途死掉时盘上「无 manifest」，下一轮按
       无缓存重建，绝不拿旧 manifest 配新包；
    2. 临时包原子改名就位；
    3. manifest 最后写——它是缓存的提交标记。
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "manifest.json").unlink(missing_ok=True)
    os.replace(part, cache_dir / "package.zip")
    write_file(
        cache_dir / "manifest.json",
        {**fields, "sha256": sha256},
    )


def validate_software_zip(zip_path: Path) -> None:
    """校验完整包 zip，不满足完整包特征时抛 ValueError（线程内执行）。

    - 全条目 CRC 校验（服务端不下发摘要，损坏只能靠包自身完整性兜底）；
    - 条目路径安全：绝对路径、盘符、``..`` 段一律拒绝；
    - 根目录出现 removelist.txt / changes.json 即 OTA 包，拒收；
    - 根目录（或单层包装目录内）须有 MAA.exe 与 MAA.dll。
    """
    with zipfile.ZipFile(zip_path) as archive:
        corrupted = archive.testzip()
        if corrupted is not None:
            raise ValueError(f"zip 条目 CRC 校验失败: {corrupted}")
        names = archive.namelist()

    essentials: set[str] = set()
    for name in names:
        normalized = name.replace("\\", "/")
        segments = [segment for segment in normalized.split("/") if segment]
        if not segments:
            continue
        if normalized.startswith(("/", "\\")) or ":" in segments[0] or ".." in segments:
            raise ValueError(f"更新包含路径异常条目: {name}")
        if len(segments) == 1 and segments[0].lower() in _OTA_MANIFEST_ENTRIES:
            raise ValueError("更新包是 OTA 包（根目录含 OTA 清单），只支持完整包")
        if segments[-1].lower() in _ESSENTIAL_ENTRIES and len(segments) <= 2:
            essentials.add(segments[-1].lower())
    missing = _ESSENTIAL_ENTRIES - essentials
    if missing:
        raise ValueError(f"更新包缺少关键文件: {sorted(missing)}")


# --------------------------------------------------------------------------
# 待更新登记
# --------------------------------------------------------------------------


def has_delegated_update_failure(maa_root: Path) -> bool:
    """上游委托安装失败标志是否存在（只读检查）。

    存在表示上次官方安装失败、安装可能处于半更新状态，MAA 下次启动会弹
    阻塞式修复窗；此时不再登记新包，交由用户按上游修复流程处理。
    """
    return (maa_root / _FAILURE_FLAG_FILE).is_file()


def read_pending_update(maa_root: Path) -> tuple[str, str]:
    """读已登记的待更新包，返回 (版本名, 包路径)。

    读取顺序对齐 UpdateMAA.update_maa：新格式 gui.new.json 的 Update 组
    优先，回落旧格式 gui.json 的 Global.VersionUpdate.*。配置损坏或读取
    失败上抛，由登记入口告警并停止，不把无法读取伪装成无登记。
    """
    new_set = read_dict_file(maa_root / "config" / "gui.new.json")
    update = new_set.get("Update")
    if isinstance(update, dict):
        package = str(update.get("UpdatePackage") or "")
        if package:
            return str(update.get("Name") or ""), package
    old_set = read_dict_file(maa_root / "config" / "gui.json")
    global_set = old_set.get("Global")
    if isinstance(global_set, dict):
        package = str(global_set.get("VersionUpdate.package") or "")
        if package:
            return str(global_set.get("VersionUpdate.name") or ""), package
    return "", ""


def register_pending_update(
    maa_root: Path,
    *,
    version: str,
    package_zip: Path,
    package_sha256: str,
) -> bool:
    """把完整包复制进 MAA 安装目录并登记待更新字段，返回是否登记成功。

    由 software_update.prepare_maa_software_update 在原有 update_maa() 调用
    点前调用；登记后仍由未改动的 update_maa() 启动 MAA 官方更新链安装。

    - 上游失败标志存在、磁盘预算不足（包大小 ×3）时不登记；
    - 已有指向现存包的其他登记时不覆盖，保护现有登记；
    - 包以临时名复制、完成后原子改名，并复核 SHA256 与缓存一致；
    - 新版配置写 Update.Name / Update.UpdatePackage（绝对路径，上游同款）；
      仅旧版安装（无 gui.new.json）写 Global.VersionUpdate.name 与
      VersionUpdate.package 两个字段（上游 HasPendingUpdatePackage 语义下
      两者缺一不可，而 update_maa 只回写 package）；
    - 配置写入失败时回滚本次复制，不留半成品登记。

    幂等：重复调用对同版本包只复制一次、登记值重复写入无副作用。
    """
    if not version or _ILLEGAL_NAME_RE.search(version):
        logger.warning(f"MAA 本体更新: 版本名无法用作包文件名，跳过登记: {version!r}")
        return False
    if has_delegated_update_failure(maa_root):
        logger.warning(
            "MAA 本体更新: 检测到上游安装失败标志，跳过登记，请先在 MAA 内完成修复"
        )
        return False

    target = maa_root / f"{_FULL_PACKAGE_PREFIX}{version}.zip"
    if not target.is_absolute():
        target = Path(os.path.abspath(target))

    try:
        existing_name, existing_package = read_pending_update(maa_root)
    except (ConfigCorruptedError, OSError) as e:
        logger.warning(f"MAA 本体更新: 无法确认已有待更新登记，跳过登记: {e}")
        return False
    existing_path = Path(existing_package) if existing_package else None
    if existing_path is not None and not existing_path.is_absolute():
        existing_path = maa_root / existing_path
    if existing_path is not None and existing_path.is_file():
        if (
            os.path.normcase(str(existing_path)) == os.path.normcase(str(target))
            and existing_name == version
        ):
            try:
                if _file_sha256(existing_path) == package_sha256:
                    return True
            except OSError as e:
                logger.warning(f"MAA 本体更新: 已登记包暂不可读，保留现有登记: {e}")
                return False
        # 同版本也可能是 MAA 自己下载的不同压缩包，不能覆盖后再靠删除回滚。
        logger.info(
            f"MAA 本体更新: 已有待更新登记 {existing_name or '未知版本'}"
            f"（{existing_package}），保护现有登记，跳过"
        )
        return False

    usage = shutil.disk_usage(maa_root)
    if usage.free < package_zip.stat().st_size * _FREE_SPACE_SCALE:
        logger.warning(
            f"MAA 本体更新: {maa_root} 所在磁盘剩余空间不足"
            f"（需约 {package_zip.stat().st_size * _FREE_SPACE_SCALE // (1024 * 1024)} MB），跳过登记"
        )
        return False

    copied = False
    try:
        # 复用 resource_package 同款原语：目标已一致则跳过，临时名复制、
        # SHA256 复核、原子换位、只读位清理
        target_valid = target.is_file() and _file_sha256(target) == package_sha256
        _copy_if_changed(package_zip, target, expected_sha256=package_sha256)
        copied = not target_valid

        new_config = maa_root / "config" / "gui.new.json"
        old_config = maa_root / "config" / "gui.json"
        if new_config.is_file():
            config_path = new_config
            data = read_dict_file(config_path)
            update = data.setdefault("Update", {})
            update["Name"] = version
            update["UpdatePackage"] = str(target)
        elif old_config.is_file():
            config_path = old_config
            data = read_dict_file(config_path)
            global_set = data.setdefault("Global", {})
            global_set["VersionUpdate.name"] = version
            global_set["VersionUpdate.package"] = str(target)
        else:
            logger.warning("MAA 本体更新: 安装目录缺少 MAA 配置文件，跳过登记")
            if copied:
                target.unlink(missing_ok=True)
            return False
        write_file(config_path, data)
        return True
    except Exception as e:
        if copied:
            # 只回滚本次复制出的包，不动复用或既有的文件
            target.unlink(missing_ok=True)
            logger.warning(f"MAA 本体更新: 登记失败（已回滚本次复制）: {e}")
        else:
            logger.warning(f"MAA 本体更新: 登记失败: {e}")
        return False
