#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

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

"""Emulator 2.0 接口。

路径的增与删**拆成两个接口**：按项目规范，MCP 靠 ``Delete`` 标签排除破坏性接口，
增删合一就没法分类。移除前另给一个只读的预览接口，供确认页列出受影响的脚本。
"""

from typing import (
    Dict,
    List,
    Optional,
)

from fastapi import APIRouter, Body
from pydantic import (
    BaseModel,
    Field,
)

from app.core import EmulatorManager
from app.models.schema import OutBase
from app.utils import emulator2 as _utils_emulator2
from app.utils import get_logger


class Emulator2SearchIn(BaseModel):
    emulatorId: Optional[str] = Field(
        default=None, description="配置ID, 携带时会标出已添加过的路径"
    )


class Emulator2SearchItem(BaseModel):
    type: str = Field(..., description="模拟器类型")
    version: str = Field(default="", description="探测到的版本号")
    installPath: str = Field(..., description="安装目录")
    alias: str = Field(default="", description="安装别名, 默认取目录名")
    supported: bool = Field(..., description="能否加入 Emulator 2.0")
    reason: str = Field(
        ...,
        description=(
            "判定原因: ok 可添加 / version_too_old 版本太旧 / planned 后续版本接入 / "
            "unsupported 暂不支持 / already_added 已添加 / "
            "not_found 找不到模拟器程序 / probe_failed 版本认不出 / "
            "components_missing 魔改 AVD 根目录里组件不全 (用包里的「补全组件.bat」补齐) / "
            "test_package_required 根目录里的模拟器不是魔改 AVD 内测包里的自编版 / "
            "test_package_outdated 魔改 AVD 内测包编号太旧或读不到, 要换新包"
        ),
    )
    instanceCount: Optional[int] = Field(default=None, description="实例数量")


class Emulator2SearchOut(OutBase):
    emulators: List[Emulator2SearchItem] = Field(
        default_factory=list, description="搜索结果, 不可添加的也会列出并说明原因"
    )


class Emulator2DevicesIn(BaseModel):
    emulatorId: str = Field(..., description="配置ID")
    withSettings: bool = Field(
        default=True,
        description="是否连四项设置与稳定模式一起读; 状态轮询传 false, 只取在线状态与 ADB 地址",
    )


class Emulator2PathAddIn(BaseModel):
    emulatorId: str = Field(..., description="配置ID")
    installPath: str = Field(..., description="模拟器安装目录")
    alias: Optional[str] = Field(default=None, description="安装别名")


class Emulator2SlotAssignment(BaseModel):
    slot: str = Field(..., description="设备号")
    nativeIndex: str = Field(..., description="模拟器自己的实例索引")


class Emulator2PathAddOut(OutBase):
    ok: bool = Field(default=False, description="是否添加成功")
    reason: str = Field(default="", description="失败原因枚举, 与搜索结果同一套")
    pathId: str = Field(default="", description="路径标识, 由安装目录派生")
    alias: str = Field(default="", description="安装别名")
    type: str = Field(default="", description="模拟器类型")
    version: str = Field(default="", description="探测到的版本号")
    assignedSlots: List[Emulator2SlotAssignment] = Field(
        default_factory=list, description="本次新分配的设备号"
    )
    revivedSlots: List[str] = Field(
        default_factory=list, description="重新添加同一路径时沿用的原设备号"
    )


class Emulator2PathRemoveIn(BaseModel):
    emulatorId: str = Field(..., description="配置ID")
    pathId: str = Field(..., description="路径标识")


class Emulator2AffectedScript(BaseModel):
    scriptId: str = Field(..., description="脚本ID")
    name: str = Field(..., description="脚本名称")
    slot: str = Field(..., description="绑定的设备号")
    running: bool = Field(default=False, description="是否正在运行")


class Emulator2PathRemovePreviewOut(OutBase):
    slots: List[str] = Field(default_factory=list, description="将会失效的设备号")
    affectedScripts: List[Emulator2AffectedScript] = Field(
        default_factory=list, description="受影响的脚本"
    )


class Emulator2PathRemoveOut(OutBase):
    ok: bool = Field(default=False, description="是否移除成功")
    tombstonedSlots: List[str] = Field(
        default_factory=list,
        description="已失效并保留的设备号, 不会再分配给其他设备",
    )
    affectedScripts: List[Emulator2AffectedScript] = Field(
        default_factory=list, description="受影响的脚本"
    )


class Emulator2InstanceCreateIn(BaseModel):
    emulatorId: str = Field(..., description="配置ID")
    pathId: str = Field(..., description="在哪条模拟器安装下新建")
    name: Optional[str] = Field(
        default=None, description="新实例名称, 留空由模拟器自己命名"
    )
    memoryMb: Optional[int] = Field(
        default=None,
        description="仅魔改 AVD: 内存 MB, 可选 3072 / 4096 / 5120 / 6144; 留空为 6144",
    )
    cpu: Optional[int] = Field(
        default=None, description="仅魔改 AVD: CPU 核数, 可选 2 / 4 / 6, 留空为 6"
    )
    fps: Optional[int] = Field(
        default=None,
        description="仅魔改 AVD: 帧率 (hw.lcd.vsync), 可选 30 / 60, 留空为 60",
    )
    dataPartitionGb: Optional[int] = Field(
        default=None,
        description="仅魔改 AVD: 数据盘上限 GB (16–512), 按实际写入增长, 留空为 64",
    )


class Emulator2InstanceCreateOut(OutBase):
    ok: bool = Field(default=False, description="是否新建成功")
    reason: str = Field(default="", description="失败原因枚举")
    slot: str = Field(default="", description="新实例分到的设备号")
    nativeIndex: str = Field(default="", description="模拟器自己的实例索引")


class Emulator2InstanceDeleteIn(BaseModel):
    emulatorId: str = Field(..., description="配置ID")
    slot: str = Field(..., description="要删除的设备号")


class Emulator2StoreOpenIn(BaseModel):
    emulatorId: str = Field(..., description="配置ID")
    slot: str = Field(..., description="要打开游戏中心的设备号")


class Emulator2StoreOpenOut(OutBase):
    ok: bool = Field(default=False, description="游戏中心是否已在前台")
    reason: str = Field(
        default="",
        description=(
            "结局原因码: launched / already-running / no-store / not-installed"
            " / no-adb / boot-timeout / launch-timeout"
        ),
    )


class Emulator2InstanceDeletePreviewOut(OutBase):
    ok: bool = Field(default=False, description="设备号是否有效")
    reason: str = Field(default="", description="失败原因枚举")
    affectedScripts: List[Emulator2AffectedScript] = Field(
        default_factory=list, description="绑定了该设备号的脚本"
    )


class Emulator2InstanceDeleteOut(OutBase):
    ok: bool = Field(default=False, description="是否删除成功")
    reason: str = Field(default="", description="失败原因枚举")


class Emulator2SettingField(BaseModel):
    """一个设置项的值和它的来历。

    ``state`` 必须四态分开：``.config`` 里没有 ``cpuCount`` 的实例照样跑在雷电默认的
    6 核上，把「默认值」显示成「已保存」就是在声称用户设过一个他没设过的值。
    """

    value: Optional[int] = Field(default=None, description="当前值, 未设置时为 null")
    state: str = Field(
        default="unset",
        description="saved 用户保存过 / default 模拟器默认 / unset 未设置 / unreadable 读不出",
    )


class Emulator2SettingsApplyIn(BaseModel):
    emulatorId: str = Field(..., description="模拟器配置ID")
    slot: str = Field(..., description="设备号")
    changes: Dict[str, int] = Field(
        ..., description="要写入的字段; 只提交用户改过的, 其余键原样保留"
    )
    expected: Dict[str, Optional[int]] = Field(
        default_factory=dict,
        description="表单打开时看到的值; 对不上说明文件被改过, 拒绝覆盖",
    )


class Emulator2SettingsApplyOut(OutBase):
    ok: bool = Field(default=False, description="是否写入成功")
    conflicts: List[str] = Field(
        default_factory=list, description="编辑期间被改动的字段名"
    )
    applied: Dict[str, int] = Field(default_factory=dict, description="真正落盘的字段")


class Emulator2GuardCaptureOut(OutBase):
    slots: List[str] = Field(default_factory=list, description="记下基准的设备号")
    count: int = Field(default=0, description="记下基准的设备台数")


class Emulator2StableModeIn(BaseModel):
    emulatorId: str = Field(..., description="模拟器配置ID")
    slots: List[str] = Field(
        default_factory=list, description="要处理的设备号; 留空表示全部"
    )


class Emulator2SettingsApplyAllIn(BaseModel):
    emulatorId: str = Field(..., description="模拟器配置ID")
    changes: Dict[str, int] = Field(..., description="要写到全部实例上的字段")


class Emulator2BatchResult(BaseModel):
    slot: str = Field(..., description="设备号")
    ok: bool = Field(default=False, description="该设备是否写入成功")
    message: str = Field(default="", description="失败原因")


class Emulator2SettingsApplyAllOut(OutBase):
    results: List[Emulator2BatchResult] = Field(
        default_factory=list, description="逐台结果"
    )
    okCount: int = Field(default=0, description="成功台数")
    failCount: int = Field(default=0, description="失败台数")


class Emulator2PathItem(BaseModel):
    pathId: str = Field(..., description="路径标识")
    installPath: str = Field(..., description="安装目录")
    alias: str = Field(default="", description="安装别名")
    type: str = Field(default="", description="模拟器类型")
    version: str = Field(default="", description="版本号")
    slots: List[str] = Field(default_factory=list, description="该路径占用的设备号")


class Emulator2DeviceItem(BaseModel):
    slot: str = Field(..., description="设备号, 脚本绑定用它")
    pathId: str = Field(..., description="所属路径标识")
    alias: str = Field(default="", description="所属安装的别名")
    realType: str = Field(
        default="", description="设备的真实模拟器类型, 不是配置的类型"
    )
    nativeIndex: str = Field(..., description="模拟器自己的实例索引")
    availability: str = Field(
        default="ok",
        description="ok 正常 / missing 这次没枚举到 / unavailable 该安装暂时不可达",
    )
    title: str = Field(default="", description="实例名称")
    status: int = Field(default=5, description="设备状态码")
    adbAddress: str = Field(default="", description="ADB 地址")
    settings: Dict[str, Emulator2SettingField] = Field(
        default_factory=dict,
        description="已保存设置, 下次启动使用; 不是运行中实例的当前配置",
    )
    stableMode: bool = Field(
        default=False, description="稳定模式是否已生效(所有干扰项都处在安全状态)"
    )
    stableUnsafe: List[str] = Field(
        default_factory=list, description="还没进入安全状态的项"
    )


class Emulator2DevicesOut(OutBase):
    paths: List[Emulator2PathItem] = Field(
        default_factory=list, description="已纳管的模拟器路径"
    )
    devices: List[Emulator2DeviceItem] = Field(
        default_factory=list, description="合并后的设备列表"
    )


class Emulator2AvdRootIn(BaseModel):
    root: str = Field(..., description="魔改 AVD 根目录 (解压好的模拟器内测包)")


class Emulator2AvdStatusIn(Emulator2AvdRootIn):
    refresh: bool = Field(
        default=False,
        description="跳过硬件加速与 Vulkan 检查的缓存重新查; 用户点「检查」时传 true",
    )


class Emulator2AvdComponentItem(BaseModel):
    id: str = Field(
        ...,
        description="组件标识: platform-tools / emulator / system-image / launcher",
    )
    name: str = Field(..., description="组件名称")
    version: str = Field(default="", description="装着的版本; 没装为空")
    installed: bool = Field(default=False, description="是否已就绪")
    optional: bool = Field(
        default=False, description="是否可选组件 (轻量桌面), 可选组件缺失不影响添加"
    )
    localSdk: bool = Field(
        default=False,
        description="是否取自 mas-avd.json 的 sdkRoot 指定的本地 SDK",
    )
    testPackage: bool = Field(
        default=False,
        description="仅 Android 模拟器: 根目录里是魔改 AVD 内测包的自编版, 已就绪",
    )
    needsTestPackage: bool = Field(
        default=False,
        description="仅 Android 模拟器: 根目录里没有模拟器、不是自编版或内测包太旧",
    )
    build: Optional[str] = Field(
        default=None,
        description="仅 Android 模拟器: 装着的内测包版本, 如 0.32.1 (有清单读清单, 没有按 Pkg.BuildId=mas-N 算 0.N.0); 不是自编版或读不到 Pkg.BuildId 为 null",
    )
    outdatedTestPackage: bool = Field(
        default=False,
        description="仅 Android 模拟器: 是自编版, 但内测包编号低于最低要求或读不到, 要换新包",
    )


class Emulator2AvdPrecheckItem(BaseModel):
    """魔改 AVD 开机前电脑检查的一项。拦截项不满足时开机直接被拒绝, 原因同 reason + advice。"""

    id: str = Field(
        ...,
        description="检查项: path / components / emulator / acceleration / vulkan / disk / memory",
    )
    title: str = Field(..., description="检查项名称")
    ok: Optional[bool] = Field(
        default=None, description="是否满足; null 表示现在查不了 (如模拟器组件还没装)"
    )
    blocking: bool = Field(
        default=True, description="不满足时是否拒绝开机; 显卡 Vulkan 只提示不拦截"
    )
    reason: str = Field(default="", description="检查结果或不满足的原因")
    advice: str = Field(default="", description="不满足时给用户的处理建议")


class Emulator2AvdStatusOut(OutBase):
    root: str = Field(default="", description="根目录")
    ready: bool = Field(default=False, description="必需组件是否齐全, 齐了才能添加")
    components: List[Emulator2AvdComponentItem] = Field(
        default_factory=list, description="组件清单"
    )
    missing: List[str] = Field(
        default_factory=list,
        description="缺着的必需组件名称 (含不合格的模拟器); adb 和系统镜像用包里的「补全组件.bat」补齐",
    )
    accelerationOk: Optional[bool] = Field(
        default=None, description="硬件加速 (WHPX) 是否可用; null 表示还查不了"
    )
    accelerationDetail: str = Field(
        default="", description="硬件加速检查结果或不可用的原因与建议"
    )
    prechecks: List[Emulator2AvdPrecheckItem] = Field(
        default_factory=list,
        description=(
            "开机前电脑检查: 目录路径、组件、模拟器版本、硬件虚拟化、显卡 Vulkan、磁盘、内存 (内存按默认档实例估), "
            "每项给 ok、原因、建议"
        ),
    )


class Emulator2AvdInstanceIn(BaseModel):
    emulatorId: str = Field(..., description="Emulator 2.0 配置 ID")
    slot: str = Field(..., description="设备号")


class Emulator2AvdInstanceOptionsOut(OutBase):
    memoryMb: Optional[int] = Field(
        default=None, description="内存 MB, 每次开机用 -memory 传"
    )
    cpu: Optional[int] = Field(default=None, description="CPU 核数")
    fps: Optional[int] = Field(
        default=None, description="帧率 (hw.lcd.vsync), 下次开机生效"
    )
    dataPartitionGb: Optional[int] = Field(default=None, description="数据盘上限 GB")
    initialized: bool = Field(
        default=False, description="首次开机初始化是否已完成 (去预装 / 装轻量桌面等)"
    )
    launcher: str = Field(default="", description="当前桌面包名, pixel 为原生桌面")
    renderer: str = Field(default="", description="首次开机记录的渲染器 (GLES 行)")
    softwareRenderer: bool = Field(
        default=False,
        description="是否在用软件渲染 (SwiftShader); 为 true 时应提示用户更新显卡驱动",
    )
    consolePort: int = Field(default=0, description="控制台端口")
    adbPort: int = Field(default=0, description="adb 端口")
    grpcPort: int = Field(default=0, description="gRPC 端口 (带 token 鉴权)")


class Emulator2AvdApkInstallIn(BaseModel):
    emulatorId: str = Field(..., description="Emulator 2.0 配置 ID")
    slot: str = Field(..., description="设备号, 实例必须已开机")
    apkPath: str = Field(
        ..., description="本机 .apk 文件的完整路径; .xapk / 拆分安装包不支持"
    )


class Emulator2AvdApkInstallOut(OutBase):
    ok: bool = Field(default=False, description="是否安装成功")
    reason: str = Field(default="", description="ok 安装成功")
    result: str = Field(default="", description="adb install 的结果行 (Success)")


class Emulator2AvdUpdateIn(BaseModel):
    root: str = Field(
        ..., description="魔改 AVD 根目录; 必须已加进 Emulator 2.0, 别的目录一律拒绝"
    )


class Emulator2AvdUpdateStatusIn(Emulator2AvdUpdateIn):
    check: bool = Field(
        default=False,
        description=(
            "先强制查一次最新版本 (界面上的「检查更新」; 不走缓存, 不带 CDK); "
            "查不到不算失败, 原因写在 checkError"
        ),
    )


class Emulator2AvdUpdateProgress(BaseModel):
    stage: str = Field(
        default="idle",
        description=(
            "idle / downloading / extracting / verifying / staged (已下载好但这次没换上) / "
            "installing / installed / failed"
        ),
    )
    status: str = Field(default="idle", description="running / success / failed / idle")
    message: str = Field(default="", description="当前阶段的用户可读描述")
    percent: Optional[float] = Field(default=None, description="当前阶段进度百分比")
    downloadedBytes: Optional[int] = Field(default=None, description="已处理字节数")
    totalBytes: Optional[int] = Field(default=None, description="本阶段总字节数")
    speedBytesPerSec: Optional[float] = Field(
        default=None, description="下载速度 (B/s)"
    )


class Emulator2AvdUpdateResult(BaseModel):
    action: str = Field(..., description="update 换上新版 / prepare 准备新版没成")
    ok: bool = Field(default=True, description="是否成功")
    version: str = Field(default="", description="涉及的版本号")
    error: str = Field(default="", description="失败原因")


class Emulator2AvdUpdateStatusOut(OutBase):
    root: str = Field(default="", description="根目录")
    updatable: bool = Field(default=False, description="能不能更新")
    notUpdatableReason: str = Field(
        default="",
        description="不能更新的原因 (设了 sdkRoot、mas-avd.json 读不出、没有 sdk\\emulator)",
    )
    currentVersion: str = Field(
        default="",
        description="装着的版本 (有清单读清单, 没有按 Pkg.BuildId=mas-N 算 v0.N.0)",
    )
    currentBuild: str = Field(default="", description="装着的构建号, 如 mas-32")
    belowMinimum: bool = Field(
        default=False,
        description="装着的低于 MAS 要求的最低构建号, 开机前检查会拒绝开机",
    )
    minimumBuild: str = Field(default="", description="MAS 要求的最低构建号, 如 mas-25")
    minimumVersion: str = Field(
        default="",
        description="MAS 要求的最低构建号对应的版本 v0.N.0, 如 v0.25.0 (界面显示时去掉 v)",
    )
    checkError: str = Field(default="", description="上次查更新失败的原因")
    latestVersion: str = Field(default="", description="最新版本号; 没查到为空")
    latestBuild: str = Field(default="", description="最新构建号")
    updateAvailable: bool = Field(default=False, description="有比装着的新的版本")
    requiredAutoMas: str = Field(
        default="",
        description="最新版本要求的 AUTO-MAS 最低版本比当前高时给出; 这时不装, 要先更新 AUTO-MAS",
    )
    assetSize: int = Field(
        default=0,
        description="要下载的包的大小 (字节); 不知道时为 0 (Mirror 酱不填 CDK 时不报大小)",
    )
    phase: str = Field(
        default="idle",
        description=(
            "idle / preparing 正在下载、拼新版 / staged 已下载并核对好、等着换上 / swapping 换上中"
        ),
    )
    preparedVersion: str = Field(
        default="", description="已下载并核对好、下次点「更新」直接换上的版本"
    )
    runningInstances: int = Field(
        default=0,
        description="开着或正在开机的实例台数; 有就不能更新, 要先关掉",
    )
    busy: bool = Field(
        default=False, description="正在更新 (这段时间这个根目录不许开机)"
    )
    progress: Emulator2AvdUpdateProgress = Field(
        default_factory=Emulator2AvdUpdateProgress, description="最近一次更新的进度"
    )
    lastResult: Optional[Emulator2AvdUpdateResult] = Field(
        default=None, description="最近一次换上 / 准备的结果"
    )


class Emulator2AvdUpdateActionOut(OutBase):
    ok: bool = Field(default=False, description="是否已开始")
    reason: str = Field(
        default="",
        description=(
            "started 已开始 / instances_running 有实例开着或正在开机, 什么都没动, 要先关掉 "
            "(看 runningInstances) / busy 正在更新 / up_to_date 已是最新 / "
            "automas_too_old 要先更新 AUTO-MAS / check_failed 查不到最新版本"
        ),
    )
    runningInstances: int = Field(
        default=0, description="开着或正在开机、要先关掉的实例台数"
    )


router = APIRouter(prefix="/api/emulator2", tags=["Emulator 2.0"])
logger = get_logger("Emulator 2.0 API")


def _error(error: BaseException | str) -> dict:
    """统一的失败响应。

    ``service.readable_error`` 负责把认得出的异常翻译成中文一句话——
    界面上不该出现 ``ValueError: badly formed hexadecimal UUID string``。
    """
    message = error if isinstance(error, str) else EmulatorManager.readable_error(error)
    return {"code": 500, "status": "error", "message": message}


@router.post(
    "/search",
    tags=["Get"],
    summary="搜索可加入 Emulator 2.0 的模拟器",
    response_model=Emulator2SearchOut,
    status_code=200,
)
async def search_emulators(
    payload: Emulator2SearchIn = Body(default=Emulator2SearchIn()),
) -> Emulator2SearchOut:
    """列出本机模拟器并逐条判定。不可添加的**也会列出**并给出原因枚举。"""
    try:
        items = await EmulatorManager.search(payload.emulatorId)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"search_emulators失败: {type(e).__name__}: {e}"
        )
        return Emulator2SearchOut(**_error(e), emulators=[])
    return Emulator2SearchOut(emulators=[item.to_dict() for item in items])


@router.post(
    "/paths/add",
    tags=["Add"],
    summary="添加模拟器路径",
    response_model=Emulator2PathAddOut,
    status_code=200,
)
async def add_path(payload: Emulator2PathAddIn = Body(...)) -> Emulator2PathAddOut:
    """探测版本 → 落库 → 为该安装的实例分配设备号。

    版本不合要求时返回 ``ok=False`` 与原因枚举，而不是抛错。
    """
    try:
        result = await EmulatorManager.add_path(
            payload.emulatorId, payload.installPath, payload.alias
        )
    except Exception as e:
        logger.opt(exception=True).warning(f"add_path失败: {type(e).__name__}: {e}")
        return Emulator2PathAddOut(**_error(e))
    return Emulator2PathAddOut(**result)


@router.post(
    "/paths/remove/preview",
    tags=["Get"],
    summary="预览移除模拟器路径的影响",
    response_model=Emulator2PathRemovePreviewOut,
    status_code=200,
)
async def preview_remove_path(
    payload: Emulator2PathRemoveIn = Body(...),
) -> Emulator2PathRemovePreviewOut:
    """只读。列出会失效的设备号与受影响的脚本，供确认页使用。"""
    try:
        result = await EmulatorManager.preview_remove_path(
            payload.emulatorId, payload.pathId
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"preview_remove_path失败: {type(e).__name__}: {e}"
        )
        return Emulator2PathRemovePreviewOut(**_error(e))
    return Emulator2PathRemovePreviewOut(**result)


@router.post(
    "/paths/remove",
    tags=["Delete"],
    summary="移除模拟器路径",
    response_model=Emulator2PathRemoveOut,
    status_code=200,
)
async def remove_path(
    payload: Emulator2PathRemoveIn = Body(...),
) -> Emulator2PathRemoveOut:
    """移除一条路径。设备号**失效并保留**，不会再分配给其他设备。"""
    try:
        result = await EmulatorManager.remove_path(payload.emulatorId, payload.pathId)
    except Exception as e:
        logger.opt(exception=True).warning(f"remove_path失败: {type(e).__name__}: {e}")
        return Emulator2PathRemoveOut(**_error(e))
    return Emulator2PathRemoveOut(**result)


@router.post(
    "/devices",
    tags=["Get"],
    summary="查询合并后的设备列表",
    response_model=Emulator2DevicesOut,
    status_code=200,
)
async def list_devices(payload: Emulator2DevicesIn = Body(...)) -> Emulator2DevicesOut:
    """合并多条安装的实例。键是设备号，另附模拟器自己的实例索引。

    枚举失败的安装标 ``unavailable``——一次枚举失败不等于实例被删除，
    既不写墓碑也不影响下次恢复。``withSettings=false`` 只取状态，给轮询用。
    """
    try:
        result = await EmulatorManager.list_devices(
            payload.emulatorId, with_settings=payload.withSettings
        )
    except Exception as e:
        logger.opt(exception=True).warning(f"list_devices失败: {type(e).__name__}: {e}")
        return Emulator2DevicesOut(**_error(e))
    return Emulator2DevicesOut(**result)


@router.post(
    "/instances/create",
    tags=["Add"],
    summary="新建模拟器实例",
    response_model=Emulator2InstanceCreateOut,
    status_code=200,
)
async def create_instance(
    payload: Emulator2InstanceCreateIn = Body(...),
) -> Emulator2InstanceCreateOut:
    """在某条模拟器安装下新建一个实例，并给它分配设备号。

    新建成功与否**不看命令返回码**——雷电新建成功时返回码也不为 0，
    判据是列表里有没有多出实例。
    """
    try:
        result = await EmulatorManager.create_instance(
            payload.emulatorId,
            payload.pathId,
            payload.name,
            {
                "memory_mb": payload.memoryMb,
                "cpu": payload.cpu,
                "fps": payload.fps,
                "data_partition_gb": payload.dataPartitionGb,
            },
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"create_instance失败: {type(e).__name__}: {e}"
        )
        return Emulator2InstanceCreateOut(**_error(e))
    return Emulator2InstanceCreateOut(**result)


@router.post(
    "/instances/delete/preview",
    tags=["Get"],
    summary="预览删除实例的影响",
    response_model=Emulator2InstanceDeletePreviewOut,
    status_code=200,
)
async def preview_delete_instance(
    payload: Emulator2InstanceDeleteIn = Body(...),
) -> Emulator2InstanceDeletePreviewOut:
    """只读。列出绑定了该设备号的脚本，供确认页使用。"""
    try:
        result = await EmulatorManager.preview_delete_instance(
            payload.emulatorId, payload.slot
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"preview_delete_instance失败: {type(e).__name__}: {e}"
        )
        return Emulator2InstanceDeletePreviewOut(**_error(e))
    return Emulator2InstanceDeletePreviewOut(**result)


@router.post(
    "/instances/delete",
    tags=["Delete"],
    summary="删除模拟器实例",
    response_model=Emulator2InstanceDeleteOut,
    status_code=200,
)
async def delete_instance(
    payload: Emulator2InstanceDeleteIn = Body(...),
) -> Emulator2InstanceDeleteOut:
    """删除一个实例。实例必须先关闭。

    设备号不写墓碑——以后在同一原生索引重建实例仍然是这个设备号；
    在那之前该设备号显示为「未找到」，绑定它的脚本下一次执行直接失败。
    """
    try:
        result = await EmulatorManager.delete_instance(payload.emulatorId, payload.slot)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"delete_instance失败: {type(e).__name__}: {e}"
        )
        return Emulator2InstanceDeleteOut(**_error(e))
    return Emulator2InstanceDeleteOut(**result)


@router.post(
    "/instances/store/open",
    tags=["Action"],
    summary="打开游戏中心",
    response_model=Emulator2StoreOpenOut,
    status_code=200,
)
async def open_store(
    payload: Emulator2StoreOpenIn = Body(...),
) -> Emulator2StoreOpenOut:
    """在一台**已在线**的设备上打开模拟器自带的游戏中心。

    雷电纯净模式会把游戏中心从桌面藏掉，这是它唯一的图形入口。
    拉不起来返回 ``ok=false`` 和一句说明，不算接口错误；只有设备号解析不出来才是 500。
    """
    try:
        result = await EmulatorManager.open_store(payload.emulatorId, payload.slot)
    except Exception as e:
        logger.opt(exception=True).warning(f"open_store失败: {type(e).__name__}: {e}")
        return Emulator2StoreOpenOut(**_error(e))
    return Emulator2StoreOpenOut(**result)


@router.post(
    "/settings/apply",
    tags=["Action"],
    summary="修改实例设置",
    response_model=Emulator2SettingsApplyOut,
    status_code=200,
)
async def apply_settings(
    payload: Emulator2SettingsApplyIn = Body(...),
) -> Emulator2SettingsApplyOut:
    """写一台设备的设置。

    只提交用户改过的字段；``expected`` 与文件现状对不上就拒绝写入并交回冲突字段，
    绝不把表单打开时的旧值整片盖回去。
    """
    try:
        result = await EmulatorManager.apply_settings(
            payload.emulatorId, payload.slot, payload.changes, payload.expected
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"apply_settings失败: {type(e).__name__}: {e}"
        )
        return Emulator2SettingsApplyOut(**_error(e))
    return Emulator2SettingsApplyOut(**result)


@router.post(
    "/settings/apply-all",
    tags=["Action"],
    summary="批量修改全部实例设置",
    response_model=Emulator2SettingsApplyAllOut,
    status_code=200,
)
async def apply_settings_to_all(
    payload: Emulator2SettingsApplyAllIn = Body(...),
) -> Emulator2SettingsApplyAllOut:
    """把同一组设置写到全部实例上。

    没有勾选也没有冲突比对——点它就是明确要求「所有实例都设成这组值」。
    一台失败不影响其余，逐台交回结果。
    """
    try:
        result = await EmulatorManager.apply_settings_to_all(
            payload.emulatorId, payload.changes
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"apply_settings_to_all失败: {type(e).__name__}: {e}"
        )
        return Emulator2SettingsApplyAllOut(**_error(e))
    return Emulator2SettingsApplyAllOut(**result)


@router.post(
    "/stable-mode/apply",
    tags=["Action"],
    summary="应用稳定模式",
    response_model=Emulator2SettingsApplyAllOut,
    status_code=200,
)
async def apply_stable_mode(
    payload: Emulator2StableModeIn = Body(...),
) -> Emulator2SettingsApplyAllOut:
    """把设备切进稳定模式：关掉会干扰截图识别的模拟器功能。

    ``slots`` 留空表示全部。每台交回实际改动了哪几项；已经安全的返回空改动列表。
    **关掉稳定模式不由这个接口负责**——我们不知道用户原来想要什么值，不替他猜。
    """
    try:
        result = await EmulatorManager.apply_stable_mode(
            payload.emulatorId, payload.slots
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"apply_stable_mode失败: {type(e).__name__}: {e}"
        )
        return Emulator2SettingsApplyAllOut(**_error(e))
    return Emulator2SettingsApplyAllOut(**result)


@router.post(
    "/guard/capture",
    tags=["Action"],
    summary="记录配置守卫的基准",
    response_model=Emulator2GuardCaptureOut,
    status_code=200,
)
async def capture_baselines(
    payload: Emulator2DevicesIn = Body(...),
) -> Emulator2GuardCaptureOut:
    """把当前所有设备的设置记成守卫基准。开启守卫时调一次。

    只记用户显式设过的字段：模拟器默认值和从没设过的项没有「应该是什么」可言，
    写进基准等于替用户决定。
    """
    try:
        result = await EmulatorManager.capture_baselines(payload.emulatorId)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"capture_baselines失败: {type(e).__name__}: {e}"
        )
        return Emulator2GuardCaptureOut(**_error(e))
    return Emulator2GuardCaptureOut(**result)


# ---- 魔改 AVD（Android Emulator）------------------------------------------


@router.post(
    "/avd/status",
    tags=["Get"],
    summary="查询魔改 AVD 根目录的组件状态",
    response_model=Emulator2AvdStatusOut,
    status_code=200,
)
async def avd_status(
    payload: Emulator2AvdStatusIn = Body(...),
) -> Emulator2AvdStatusOut:
    """组件清单与是否齐全（缺哪几项）、硬件加速（WHPX）是否可用、开机前电脑检查。
    组件随模拟器内测包提供，MAS 不下载。只读，不联网。``refresh`` 为 true 时检查不走缓存。
    """
    try:
        result = await _utils_emulator2.avd.service.status(
            payload.root, refresh=payload.refresh
        )
    except Exception as e:
        logger.opt(exception=True).warning(f"avd_status失败: {type(e).__name__}: {e}")
        return Emulator2AvdStatusOut(**_error(e))
    return Emulator2AvdStatusOut(**result)


@router.post(
    "/avd/instance/options",
    tags=["Get"],
    summary="查询魔改 AVD 实例选项",
    response_model=Emulator2AvdInstanceOptionsOut,
    status_code=200,
)
async def avd_instance_options(
    payload: Emulator2AvdInstanceIn = Body(...),
) -> Emulator2AvdInstanceOptionsOut:
    """显示档位、内存、核数、数据盘、首次初始化与渲染器检测结果、端口。"""
    try:
        result = await EmulatorManager.avd_instance_options(
            payload.emulatorId, payload.slot
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"avd_instance_options失败: {type(e).__name__}: {e}"
        )
        return Emulator2AvdInstanceOptionsOut(**_error(e))
    return Emulator2AvdInstanceOptionsOut(**result)


@router.post(
    "/avd/instance/apk/install",
    tags=["Action"],
    summary="在魔改 AVD 实例里安装 APK",
    response_model=Emulator2AvdApkInstallOut,
    status_code=200,
)
async def avd_install_apk(
    payload: Emulator2AvdApkInstallIn = Body(...),
) -> Emulator2AvdApkInstallOut:
    """``adb install -r`` 本机的一个 .apk，实例必须已开机；装完才返回。.xapk / 拆分安装包不支持。"""
    try:
        result = await EmulatorManager.install_avd_apk(
            payload.emulatorId, payload.slot, payload.apkPath
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"avd_install_apk失败: {type(e).__name__}: {e}"
        )
        return Emulator2AvdApkInstallOut(**_error(e))
    return Emulator2AvdApkInstallOut(**result)


# ---- 魔改 AVD 更新 ----------------------------------------------------------


@router.post(
    "/avd/update/status",
    tags=["Get"],
    summary="查询魔改 AVD 根目录的更新状态",
    response_model=Emulator2AvdUpdateStatusOut,
    status_code=200,
)
async def avd_update_status(
    payload: Emulator2AvdUpdateStatusIn = Body(...),
) -> Emulator2AvdUpdateStatusOut:
    """装着的版本、最新版本、已下载好的版本、更新进度。``check`` 为 true 时（「检查更新」）先强制问一次
    下载源（Mirror 酱、GitHub）最新版本，不带 CDK；查不到不算接口失败，原因写在 ``checkError``。"""
    try:
        result = await EmulatorManager.avd_update_status(
            payload.root, check=payload.check
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"avd_update_status失败: {type(e).__name__}: {e}"
        )
        return Emulator2AvdUpdateStatusOut(**_error(e))
    return Emulator2AvdUpdateStatusOut(**result)


@router.post(
    "/avd/update",
    tags=["Action"],
    summary="更新魔改 AVD",
    response_model=Emulator2AvdUpdateActionOut,
    status_code=200,
)
async def avd_update(
    payload: Emulator2AvdUpdateIn = Body(...),
) -> Emulator2AvdUpdateActionOut:
    """一键更新：查最新版本，下载（Mirror 酱或 GitHub，整包或增量）并核对，再换上。
    有实例开着或正在开机时什么都不动，返回 ``instances_running``；开始后到结束这个根目录不许开机。
    换上前发现还有程序开着模拟器文件时停在「已下载好」，下次直接换上。
    立刻返回，进度经 WebSocket ``emulator2.avd-update.progress`` 推送。"""
    try:
        result = await EmulatorManager.update_avd(payload.root)
    except Exception as e:
        logger.opt(exception=True).warning(f"avd_update失败: {type(e).__name__}: {e}")
        return Emulator2AvdUpdateActionOut(**_error(e))
    return Emulator2AvdUpdateActionOut(**result)
