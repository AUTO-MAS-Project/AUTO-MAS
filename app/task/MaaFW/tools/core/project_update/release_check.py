"""载荷与同版本官方发行包核对：资源目录里不属于这一版的文件（旧版本残留）清掉。

问题（战双帕弥什 MAA_Punish，2026-10-26）：用户的项目目录是旧版本被新包覆盖过的，上游
已删掉的 ``resource/pgr_win32/pipeline/auto_battle.jsonc`` 还在，导入时一起进了载荷。它与新版
``Auto_Battle/Check_Characters_Skill/Pyroath.jsonc`` 定义了同一个节点，MaaFramework 不允许同一
资源包内节点重名，整包拒收，项目每次运行都失败。第一次全量更新会按 ``apply._import_origin_orphans``
清掉这类文件，可从导入到项目发下一版之间一直跑不起来；同版本重新导入也顶不掉（只在版本
严格更高时推进 latest）。这里补上那段空档：

1. **比对依据**与投影补齐同一套零件（``projection_heal``）：更新下载缓存里同版本的完整包 →
   GitHub Release 资产的中央目录（HTTP Range，只读中央目录与 interface 及其 import，**不下整包**；
   不碰 Mirror 酱的一次性签名地址，不走加速镜像——区间字节只有条目级 CRC）。来源目录本身不能
   当依据：残留就在它里面。
2. **残留的口径**与全量更新清 ``origin=import`` 残留同一条（``apply._import_origin_orphans``）：
   发行包按投影白名单留下的文件（``package_projection_rules`` + ``filter_package_entries``，与整包
   落地同一张表）、新 interface 声明且包里确实铺了文件的资源目录（``resource[].path`` 之外还算
   控制器的 ``attach_resource_path``，见 ``apply._attached_resource_directories``）、
   跳过 ``.auto_mas*`` 与字节码；
   调用方再与 ``origin=import`` 取交集。路径大小写不敏感地比（漏判比误删好：误删的是项目自己的
   资源文件，又没有新包补上）。
3. **两处用**：导入时（:func:`verify_tree`，同步、硬时限，核对不了照旧导入），与运行时资源包
   加载失败（:func:`check_and_clean`：旧载荷减去残留 → staging 里的同版本新载荷 → 登记，靠
   ``payloads.register`` 的同版本例外三顶替没核对过的 latest → 由调用方切视图）。
4. **每个载荷只查一次**：结果记进清单的 ``releaseCheck``（``payloads.RELEASE_CHECK_FIELD``）。
   网络这类暂时失败最多 :data:`MAX_ATTEMPTS` 次、两次之间至少隔 :data:`RETRY_AFTER_SECONDS`；
   导入时没核对成的记 ``stage=import``、不占次数，留给运行时再查。

零宿主耦合：标准库、``httpx`` 与本包内的模块。
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
import zipfile
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Any

import httpx

from .apply import (
    PackagePlan,
    _is_bytecode_artifact,
    _package_resource_directories,
)
from .payloads import (
    ORIGIN_IMPORT,
    RELEASE_CHECK_CLEAN,
    RELEASE_CHECK_FIELD,
    PayloadError,
    PayloadTarget,
    RegisterResult,
    _field,
    clone_payload_into,
    finalize,
    lineage_key,
    lineage_lock,
    manifest_files,
    manifest_path,
    mark_damaged,
    payload_dir,
    projection_revision_of,
    read_lineage,
    read_manifest,
    register,
    release_verified,
    remove_tree,
    write_json_atomic,
)
from .projection import (
    ProjectionError,
    filter_package_entries,
    package_projection_rules,
)
from .projection_heal import (
    HealSkip,
    RangeHTTPReader,
    _cached_packages,
    _norm_version,
    _parse_json,
    package_entries,
    read_entry,
    repoint_latest,
    write_archive_skeleton,
)
from .state import DEFAULT_CACHE_ROOT

logger = logging.getLogger("automas.maafw.project_update.release_check")

RESULT_CLEAN = RELEASE_CHECK_CLEAN
# 核对过、有残留：清单记清理后的载荷（``cleanedTo``）。
RESULT_STALE = "stale"
RESULT_UNAVAILABLE = "unavailable"
# 有残留，但建清理后的载荷失败。
RESULT_FAILED = "failed"
STAGE_IMPORT = "import"
STAGE_RUN = "run"
# 暂时失败（断网、GitHub 连不上、超时）最多查这么多次，两次之间至少隔这么久。只在资源包加载
# 失败时才查（那时每次运行都在失败），间隔比投影补齐（6 小时）短。
MAX_ATTEMPTS = 3
RETRY_AFTER_SECONDS = 30 * 60
# 运行时：整次核对（找依据 + 读中央目录）最多这么久，与投影补齐的运行前检查同一量级。
RUN_CHECK_DEADLINE_SECONDS = 45.0
# 导入时用户在界面上等着：硬时限短一些，超了照旧导入、留给运行时再查。
IMPORT_CHECK_DEADLINE_SECONDS = 15.0
# 单次请求：连接 5 s、读 8 s（GitHub API 由 ``_github_asset`` 自己的超时管）。
HTTP_TIMEOUT = httpx.Timeout(8.0, connect=5.0)
# 清单与报告里记下的残留路径最多几条。
RECORD_ITEMS = 20
_INTERFACE_NAMES = ("interface.json", "interface.jsonc")


@dataclass
class ReleaseListing:
    """同版本发行包的文件表（按投影白名单留下的、项目根相对路径）与它声明的、包里确实铺了
    文件的资源目录。"""

    via: str
    version: str
    files: frozenset[str]
    resource_dirs: frozenset[str]
    transferred: int = 0


# --------------------------------------------------------------------------
# 发行包的文件表
# --------------------------------------------------------------------------


def _identity(interface: Any) -> SimpleNamespace:
    """``_github_asset`` 只读 interface 的 name / github / mirrorchyan_rid：原始 dict 与加载后的
    模型都转成同一个形状。"""

    return SimpleNamespace(
        name=_field(interface, "name"),
        github=_field(interface, "github"),
        mirrorchyan_rid=_field(interface, "mirrorchyan_rid", "mirrorchyanRid"),
    )


def _local_sizes(directory: Path | None) -> dict[str, int]:
    from .range_delta import _local_sizes as local_sizes

    return local_sizes(directory) if directory is not None else {}


def _listing_from_archive(
    archive: zipfile.ZipFile,
    via: str,
    *,
    lineage: str,
    version: str,
    project_root: Path | None,
    workdir: Path,
) -> ReleaseListing:
    """按中央目录算发行包的文件表：与区间差量（``range_delta.open_range_delta``）同一套做法——
    在 ``workdir`` 下建空文件骨架（interface 及其 import 写真内容），叠在 ``project_root``（被
    核对的那棵树）上用 ``package_projection_rules`` 算白名单，与整包落地时同一张表。"""

    interface_rel, infos = package_entries(archive)
    try:
        data = _parse_json(read_entry(archive, infos[interface_rel], interface_rel))
        same = lineage_key(data) == lineage
    except (ValueError, PayloadError) as exc:
        raise HealSkip(
            f"发行包里的 interface.json 读不了：{exc}", permanent=True
        ) from exc
    if not same:
        raise HealSkip("发行包与本机的项目对不上", permanent=True)
    if _norm_version(data.get("version")) != _norm_version(version):
        raise HealSkip(
            f"发行包的版本是 {data.get('version')}，不是 {version}", permanent=True
        )
    # 整包落地时名叫 changes.json 的文件一律不算条目（``apply.build_package_plan``）。
    candidates = {
        rel: info
        for rel, info in infos.items()
        if PurePosixPath(rel).name != "changes.json"
    }
    chosen = infos[interface_rel].filename
    prefix = chosen[: len(chosen) - len(interface_rel)]
    directories = [
        info.filename[len(prefix) :].rstrip("/")
        for info in archive.infolist()
        if info.is_dir()
        and info.filename.startswith(prefix)
        and info.filename[len(prefix) :].strip("/")
    ]
    skeleton = Path(workdir) / f"rc-{uuid.uuid4().hex[:8]}"
    notes: list[str] = []
    try:
        write_archive_skeleton(
            archive, interface_rel, infos, skeleton, directories=directories
        )
        sizes = _local_sizes(project_root)
        sizes.update({rel: info.file_size for rel, info in infos.items()})
        try:
            rules = package_projection_rules(
                skeleton, project_root or skeleton, sizes=sizes
            )
        except ProjectionError as exc:
            raise HealSkip(f"算不出发行包的投影白名单：{exc}", permanent=True) from exc
        kept, _dropped = filter_package_entries(rules, candidates)
        plan = PackagePlan(
            package_type="full",
            package_root=skeleton,
            files={rel: skeleton / rel for rel in kept},
            hashes={},
            deleted=(),
        )
        declared = _package_resource_directories(plan, notes.append)
    finally:
        try:
            remove_tree(skeleton)
        except OSError:
            logger.warning("MaaFW 核对用的骨架目录没删掉，留待启动时清理：%s", skeleton)
    if notes:
        raise HealSkip(notes[0], permanent=True)
    folded = {rel.casefold() for rel in kept}
    # 包里没往某个声明的资源目录铺任何文件：声明与实际对不上，不能拿它当「这个目录本该是
    # 空的」的依据（与 ``_import_origin_orphans`` 同一条）。
    resource_dirs = frozenset(
        directory
        for directory in declared
        if any(rel.startswith(f"{directory.casefold()}/") for rel in folded)
    )
    return ReleaseListing(
        via=via,
        version=version,
        files=frozenset(kept),
        resource_dirs=resource_dirs,
    )


def _open_client(proxy: httpx.Proxy | None) -> httpx.Client:
    """测试替换这里注入 ``MockTransport``。"""

    return httpx.Client(proxy=proxy, follow_redirects=True, timeout=HTTP_TIMEOUT)


def _remote_listing(
    url: str,
    size: int,
    *,
    proxy: httpx.Proxy | None,
    deadline: float | None,
    **kwargs: Any,
) -> ReleaseListing:
    client = _open_client(proxy)
    archive: zipfile.ZipFile | None = None
    try:
        reader = RangeHTTPReader(
            client, url, expected_size=size or None, deadline=deadline
        )
        try:
            archive = zipfile.ZipFile(reader)  # type: ignore[arg-type]
        except zipfile.BadZipFile as exc:
            raise HealSkip(f"发行包的中央目录读不了：{exc}") from exc
        listing = _listing_from_archive(archive, "GitHub 发行包", **kwargs)
        listing.transferred = reader.fetched
        return listing
    finally:
        if archive is not None:
            archive.close()
        client.close()


async def _github_asset(
    interface: Any, version: str, *, proxy: httpx.Proxy | None, shell_hint: str
) -> tuple[str, int]:
    """测试替换这里：同版本 GitHub Release 资产的地址与大小（与投影补齐同一套选资产规则）。"""

    from .projection_heal import _github_asset as github_asset

    return await github_asset(interface, version, proxy=proxy, shell_hint=shell_hint)


async def fetch_release_listing(
    *,
    lineage: str,
    version: str,
    interface: Any,
    workdir: Path,
    project_root: Path | None = None,
    proxy: httpx.Proxy | None = None,
    shell_hint: str = "",
    cache_root: Path | None = None,
    deadline: float | None = None,
) -> ReleaseListing:
    """按 缓存的同版本完整包 → GitHub 发行包中央目录 的顺序取文件表；拿不到抛 :class:`HealSkip`。

    ``project_root``：被核对的那棵树（载荷目录或导入的 staging），白名单叠在它上面算（顶层条目
    的去留看大小，与整包落地时叠在旧载荷上同一口径）。``deadline``：``time.monotonic()`` 的截止
    时刻，远端读取过了它就不再发请求。
    """

    if not str(version or "").strip():
        raise HealSkip("interface.json 没有声明版本号", permanent=True)
    common: dict[str, Any] = {
        "lineage": lineage,
        "version": version,
        "project_root": project_root,
        "workdir": workdir,
    }
    for cached in await asyncio.to_thread(
        _cached_packages, Path(cache_root or DEFAULT_CACHE_ROOT), version
    ):

        def from_cache(path: Path = cached) -> ReleaseListing:
            with zipfile.ZipFile(path) as archive:
                return _listing_from_archive(archive, "本机缓存的发行包", **common)

        try:
            return await asyncio.to_thread(from_cache)
        except (HealSkip, OSError, zipfile.BadZipFile) as exc:
            logger.info("MaaFW 缓存包 %s 不能用来核对：%s", cached, exc)
    url, size = await _github_asset(
        _identity(interface), version, proxy=proxy, shell_hint=shell_hint
    )
    return await asyncio.to_thread(
        _remote_listing, url, size, proxy=proxy, deadline=deadline, **common
    )


def release_orphans(candidates: Iterable[str], listing: ReleaseListing) -> list[str]:
    """``candidates``（项目根相对路径）里落在发行包资源目录内、包里又没有的那些。

    与 ``apply._import_origin_orphans`` 同一口径（只看资源目录、跳过 ``.auto_mas*`` 与字节码）；
    调用方传进来的应当只是 ``origin=import`` 的文件。"""

    package = {rel.casefold() for rel in listing.files}
    prefixes = tuple(f"{directory.casefold()}/" for directory in listing.resource_dirs)
    if not prefixes:
        return []
    orphans: list[str] = []
    for rel in candidates:
        folded = rel.casefold()
        if folded in package or not folded.startswith(prefixes):
            continue
        if _is_bytecode_artifact(rel):
            continue
        if any(part.startswith(".auto_mas") for part in rel.split("/")):
            continue
        orphans.append(rel)
    return sorted(orphans)


# --------------------------------------------------------------------------
# 记录（写在被核对的载荷清单里）
# --------------------------------------------------------------------------


def _now_text() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def make_record(result: str, version: str, **extra: Any) -> dict[str, Any]:
    """一条 ``releaseCheck`` 记录（带时刻；``version`` 是核对的那一版）。"""

    return {
        "result": result,
        "version": str(version or ""),
        "at": _now_text(),
        "atEpoch": time.time(),
        **extra,
    }


def check_record(manifest: Mapping[str, Any] | None) -> dict[str, Any] | None:
    record = (manifest or {}).get(RELEASE_CHECK_FIELD)
    return dict(record) if isinstance(record, Mapping) else None


def cleaned_to(manifest: Mapping[str, Any] | None) -> str | None:
    """这个载荷已清理成哪一份（没清理过为 None）。"""

    record = check_record(manifest)
    if record is None or str(record.get("result") or "") != RESULT_STALE:
        return None
    return str(record.get("cleanedTo") or "") or None


def check_due(manifest: Mapping[str, Any] | None, *, now: float | None = None) -> bool:
    """这个载荷要不要（再）与发行包核对一次。核对过的（没残留 / 已清理）不再查；查不了的：
    永久性的（没有 github、发行包没有这一版……）不再查，暂时的有限次、隔一段时间再查；导入
    时没核对成的（``stage=import``）不占次数、不看间隔。"""

    if manifest is None or release_verified(manifest):
        return False
    record = check_record(manifest)
    if record is None:
        return True
    result = str(record.get("result") or "")
    if result in {RESULT_CLEAN, RESULT_STALE}:
        # clean 却没通过 release_verified：记录的版本对不上，当没查过。
        return result == RESULT_CLEAN
    if str(record.get("stage") or "") == STAGE_IMPORT:
        return not record.get("permanent")
    if record.get("permanent") or int(record.get("attempts") or 0) >= MAX_ATTEMPTS:
        return False
    moment = time.time() if now is None else now
    return moment - float(record.get("atEpoch") or 0) >= RETRY_AFTER_SECONDS


def write_check(
    root: Path, lineage: str, payload_id: str, record: Mapping[str, Any]
) -> None:
    """把核对结果写回清单（谱系短锁内读改写，其余字段原样保留）。"""

    with lineage_lock(root, lineage):
        manifest = read_manifest(root, lineage, payload_id)
        if manifest is None:
            return
        manifest[RELEASE_CHECK_FIELD] = dict(record)
        write_json_atomic(manifest_path(root, lineage, payload_id), manifest)


def _write_check_quietly(target: PayloadTarget, record: Mapping[str, Any]) -> None:
    try:
        write_check(target.root, target.lineage, target.payload_id, record)
    except (OSError, PayloadError) as exc:
        logger.warning(
            "MaaFW 载荷 %s 的发行包核对结果写不回清单：%s", target.payload_id, exc
        )


# --------------------------------------------------------------------------
# 导入时：核对 staging 里的投影树
# --------------------------------------------------------------------------


@dataclass
class ReleaseVerdict:
    """一次核对的结论。``status``：``clean``（核对过，``removed`` 是要拿掉的残留，可能为空）/
    ``unavailable``（核对不了，``reason`` 是原因，``permanent`` 表示再查也一样）。"""

    status: str
    version: str
    removed: list[str]
    via: str = ""
    reason: str = ""
    permanent: bool = False
    transferred: int = 0
    elapsed: float = 0.0

    def record(self, stage: str, attempts: int = 0) -> dict[str, Any]:
        """写进清单的记录：核对成了（不管清没清）对清理后的那份都是 ``clean``。"""

        if self.status == RESULT_CLEAN:
            return make_record(
                RESULT_CLEAN,
                self.version,
                stage=stage,
                via=self.via,
                removedCount=len(self.removed),
                removed=self.removed[:RECORD_ITEMS],
            )
        return make_record(
            RESULT_UNAVAILABLE,
            self.version,
            stage=stage,
            attempts=attempts,
            permanent=self.permanent,
            reason=self.reason[:500],
        )


def _proxy_of(proxy_url: str | None) -> httpx.Proxy | None:
    if not proxy_url:
        return None
    try:
        return httpx.Proxy(proxy_url)
    except Exception:  # noqa: BLE001 - 代理填错按直连，地址不进日志（可能带 user:pw@）
        logger.warning("MaaFW 发行包核对：代理地址无效，本次直连")
        return None


def _reason_of(exc: BaseException) -> tuple[str, bool]:
    if isinstance(exc, HealSkip):
        return str(exc).strip() or type(exc).__name__, exc.permanent
    if isinstance(exc, TimeoutError | asyncio.TimeoutError):
        return "核对超时", False
    return f"{type(exc).__name__}: {exc}".strip(), False


def verify_tree(
    tree: Path,
    files: Iterable[str],
    *,
    lineage: str,
    version: str,
    interface: Any,
    workdir: Path,
    proxy_url: str | None = None,
    shell_hint: str = "",
    cache_root: Path | None = None,
    timeout: float = IMPORT_CHECK_DEADLINE_SECONDS,
) -> ReleaseVerdict:
    """导入时核对投影树 ``tree``（``files`` 是它的文件，项目根相对路径）：**同步、硬时限、从不
    抛异常**。核对放在一个守护线程里跑（它自己的事件循环），``timeout`` 到了不再等，结果记成
    「超时」；那个线程最多再发一个请求就会因截止时刻停下，不碰 ``tree``（只读）。"""

    started = time.monotonic()
    box: dict[str, Any] = {}
    deadline = started + timeout

    async def run() -> ReleaseListing:
        return await asyncio.wait_for(
            fetch_release_listing(
                lineage=lineage,
                version=version,
                interface=interface,
                workdir=workdir,
                project_root=tree,
                proxy=_proxy_of(proxy_url),
                shell_hint=shell_hint,
                cache_root=cache_root,
                deadline=deadline,
            ),
            timeout=timeout,
        )

    def target() -> None:
        try:
            box["listing"] = asyncio.run(run())
        except BaseException as exc:  # noqa: BLE001 - 交给调用方的结论
            box["error"] = exc

    worker = threading.Thread(target=target, name="maafw-release-check", daemon=True)
    worker.start()
    # 线程里的 wait_for 先到点；这里多等几秒收尾，再不回来就不等了。
    worker.join(timeout + 5.0)
    elapsed = time.monotonic() - started
    if worker.is_alive():
        return ReleaseVerdict(
            RESULT_UNAVAILABLE, version, [], reason="核对超时", elapsed=elapsed
        )
    error = box.get("error")
    if error is not None:
        if not isinstance(error, HealSkip):
            logger.warning("MaaFW 导入时核对发行包出错", exc_info=error)
        reason, permanent = _reason_of(error)
        return ReleaseVerdict(
            RESULT_UNAVAILABLE,
            version,
            [],
            reason=reason,
            permanent=permanent,
            elapsed=elapsed,
        )
    listing: ReleaseListing = box["listing"]
    return ReleaseVerdict(
        RESULT_CLEAN,
        version,
        release_orphans(files, listing),
        via=listing.via,
        transferred=listing.transferred,
        elapsed=elapsed,
    )


# --------------------------------------------------------------------------
# 运行时：资源包加载失败后核对并清理
# --------------------------------------------------------------------------


def rebuild_without(
    target: PayloadTarget,
    manifest: Mapping[str, Any],
    removed: Iterable[str],
    record: Mapping[str, Any],
) -> RegisterResult:
    """旧载荷减去 ``removed`` → staging 里的同版本新载荷 → 并入共用库 → 登记（带 ``record``，
    它核对过、由 ``register`` 的同版本例外三顶替没核对过的 latest）。staging 一律
    ``place_fresh``（``clone_payload_into``），载荷不可变；任何一步失败都只是丢掉 staging。"""

    dropped = set(removed)
    old_files = manifest_files(manifest)
    kept = [rel for rel in old_files if rel not in dropped]
    staging = (
        Path(target.staging_root) / f"clean-{target.lineage}-{uuid.uuid4().hex[:8]}"
    )
    damaged = False
    try:
        staging.mkdir(parents=True, exist_ok=False)
        clone_payload_into(target.directory(), kept, staging)
        finalized = finalize(
            staging, blob_store=target.blob_store, private=target.private_paths
        )
        damaged = target.payload_id in {
            str(item)
            for item in read_lineage(target.root, target.lineage).get("damaged") or []
        }
        # 原样搬来的文件内容没变，清单里的哈希直接用（被写穿过的载荷除外）。
        known = (
            {}
            if damaged
            else {
                rel: old_files[rel]["sha256"]
                for rel in kept
                if old_files[rel]["sha256"]
            }
        )
        known.update(finalized.hashes)
        registered = register(
            target.root,
            staging,
            lineage=target.lineage,
            channel=target.channel,
            source=dict(manifest.get("source") or {}),
            by=target.by,
            version=str(manifest.get("version") or ""),
            lineage_info=target.lineage_info,
            known_hashes=known,
            origins={rel: old_files[rel]["origin"] for rel in kept},
            bundled={
                "maafw": str(manifest.get("bundledMaaFW") or ""),
                "python": str(manifest.get("bundledPython") or ""),
            },
            projection_revision=projection_revision_of(manifest),
            release_check=record,
        )
    except BaseException:
        try:
            remove_tree(staging)
        except OSError:
            logger.warning(
                "MaaFW 清理残留的 staging 没删掉，留待启动时清理：%s", staging
            )
        raise
    if damaged:
        # 被写穿过的载荷：坏的 inode 原样链进了新载荷，新 id 也得标 damaged（同投影补齐）。
        try:
            mark_damaged(target.root, target.lineage, registered.payload_id)
        except (OSError, PayloadError) as exc:
            logger.warning(
                "MaaFW 清理后的载荷 %s 没能标上 damaged：%s", registered.payload_id, exc
            )
    return registered


class CleanOutcome:
    """一次运行时核对的结果（``view_update.run_view_update`` 的 ``result``；故意不是
    dataclass，理由同 ``HealOutcome``）。

    ``status``：``verified``（早就核对过）/ ``skipped``（不用查：查不了的次数用完等）/
    ``clean``（核对过，没有残留）/ ``cleaned``（清掉残留并登记了新载荷）/ ``repointed``（别的
    渠道已清理过，本渠道的 latest 指过去）/ ``unavailable``（核对不了）/ ``failed``（建新载荷
    失败）。``switched`` 由宿主在切完视图后填。
    """

    def __init__(
        self,
        status: str,
        *,
        version: str = "",
        removed: Iterable[str] = (),
        via: str = "",
        payload_id: str | None = None,
        reason: str = "",
        permanent: bool = False,
        transferred: int = 0,
        elapsed: float = 0.0,
    ) -> None:
        self.status = status
        self.version = version
        self.removed = sorted(removed)
        self.via = via
        self.payload_id = payload_id
        self.reason = reason
        self.permanent = permanent
        self.transferred = transferred
        self.elapsed = elapsed
        self.switched = False

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return (
            f"CleanOutcome(status={self.status!r}, version={self.version!r}, "
            f"removed={len(self.removed)}, via={self.via!r}, reason={self.reason!r})"
        )


async def _after_register_quietly(
    after_register: Callable[[RegisterResult], Awaitable[Any]] | None,
    registered: RegisterResult,
) -> None:
    """切视图失败不算核对失败：载荷已在册，没切过去的下次运行前的组同步补上（宿主按视图有没有
    真的换掉决定要不要立刻重跑）。"""

    if after_register is None:
        return
    try:
        await after_register(registered)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        logger.warning("MaaFW 清理残留后的切换失败", exc_info=True)


async def check_and_clean(
    target: PayloadTarget,
    after_register: Callable[[RegisterResult], Awaitable[Any]] | None = None,
    *,
    interface: Any,
    proxy: httpx.Proxy | None = None,
    shell_hint: str = "",
    cache_root: Path | None = None,
    deadline_seconds: float = RUN_CHECK_DEADLINE_SECONDS,
) -> CleanOutcome:
    """核对 ``target`` 挂的载荷，有残留就建清理后的同版本载荷、登记，并 await ``after_register``。

    **从不抛异常**（取消除外）：结果记进清单，调用方据 ``status`` 决定要不要立刻重跑。
    """

    started = time.monotonic()
    try:
        manifest = await asyncio.to_thread(
            read_manifest, target.root, target.lineage, target.payload_id
        )
    except Exception as exc:  # noqa: BLE001 - 读不了清单就当不用查
        return CleanOutcome("skipped", reason=f"载荷清单读不了：{exc}")
    if manifest is None:
        return CleanOutcome("skipped", reason="载荷清单不在")
    version = str(manifest.get("version") or "")
    if release_verified(manifest):
        return CleanOutcome("verified", version=version)

    previous = check_record(manifest) or {}
    cleaned = cleaned_to(manifest)
    if cleaned and cleaned != target.payload_id:
        # 别的渠道已经把这份清理过：本渠道的 latest 还指着旧的就指过去（与投影补齐同一做法）。
        try:
            repointed = await asyncio.to_thread(repoint_latest, target, cleaned)
        except Exception as exc:  # noqa: BLE001 - 指不过去就照旧
            logger.warning("MaaFW 渠道 latest 指向清理后的版本失败：%s", exc)
            repointed = None
        if repointed is not None:
            await _after_register_quietly(after_register, repointed)
            return CleanOutcome(
                "repointed",
                version=version,
                removed=list(previous.get("removed") or []),
                payload_id=cleaned,
            )
    if not check_due(manifest):
        return CleanOutcome(
            "skipped",
            version=version,
            reason=str(previous.get("reason") or ""),
            permanent=bool(previous.get("permanent")),
        )
    attempts = (
        0
        if str(previous.get("stage") or "") == STAGE_IMPORT
        else int(previous.get("attempts") or 0)
    ) + 1
    try:
        listing = await asyncio.wait_for(
            fetch_release_listing(
                lineage=target.lineage,
                version=version,
                interface=interface,
                workdir=Path(target.staging_root),
                project_root=target.directory(),
                proxy=proxy,
                shell_hint=shell_hint,
                cache_root=cache_root,
                deadline=time.monotonic() + deadline_seconds,
            ),
            timeout=deadline_seconds,
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - 核对不了只是不清理
        if not isinstance(exc, HealSkip):
            logger.warning("MaaFW 与发行包核对载荷时出错", exc_info=True)
        reason, permanent = _reason_of(exc)
        await asyncio.to_thread(
            _write_check_quietly,
            target,
            make_record(
                RESULT_UNAVAILABLE,
                version,
                stage=STAGE_RUN,
                attempts=attempts,
                permanent=permanent,
                reason=reason[:500],
            ),
        )
        return CleanOutcome(
            "unavailable",
            version=version,
            reason=reason,
            permanent=permanent,
            elapsed=time.monotonic() - started,
        )

    candidates = [
        rel
        for rel, entry in manifest_files(manifest).items()
        if entry["origin"] == ORIGIN_IMPORT
    ]
    removed = release_orphans(candidates, listing)
    if not removed:
        await asyncio.to_thread(
            _write_check_quietly,
            target,
            make_record(
                RESULT_CLEAN, version, stage=STAGE_RUN, via=listing.via, removedCount=0
            ),
        )
        return CleanOutcome(
            "clean",
            version=version,
            via=listing.via,
            transferred=listing.transferred,
            elapsed=time.monotonic() - started,
        )

    try:
        registered = await asyncio.to_thread(
            rebuild_without,
            target,
            manifest,
            removed,
            make_record(
                RESULT_CLEAN,
                version,
                stage=STAGE_RUN,
                via=listing.via,
                derivedFrom=target.payload_id,
                removedCount=len(removed),
                removed=removed[:RECORD_ITEMS],
            ),
        )
    except Exception as exc:  # noqa: BLE001 - 建不成就照旧，记下来有限次重试
        reason = str(exc).strip() or type(exc).__name__
        logger.warning("MaaFW 清理载荷 %s 的残留失败：%s", target.payload_id, reason)
        await asyncio.to_thread(
            _write_check_quietly,
            target,
            make_record(
                RESULT_FAILED,
                version,
                stage=STAGE_RUN,
                attempts=attempts,
                reason=reason[:500],
                removedCount=len(removed),
                removed=removed[:RECORD_ITEMS],
            ),
        )
        return CleanOutcome(
            "failed",
            version=version,
            removed=removed,
            via=listing.via,
            reason=reason,
            elapsed=time.monotonic() - started,
        )

    await asyncio.to_thread(
        _write_check_quietly,
        target,
        make_record(
            RESULT_STALE,
            version,
            stage=STAGE_RUN,
            via=listing.via,
            cleanedTo=registered.payload_id,
            removedCount=len(removed),
            removed=removed[:RECORD_ITEMS],
        ),
    )
    await _after_register_quietly(after_register, registered)
    return CleanOutcome(
        "cleaned",
        version=version,
        removed=removed,
        via=listing.via,
        payload_id=registered.payload_id,
        transferred=listing.transferred,
        elapsed=time.monotonic() - started,
    )


def payload_check_state(
    root: Path, lineage: str, payload_id: str
) -> tuple[str, dict[str, Any]]:
    """宿主拿锁之前的廉价判断（读一个 JSON）：``verified`` / ``due`` / ``repoint`` / ``not_due``
    / ``missing``，附带记录。"""

    try:
        manifest = read_manifest(root, lineage, payload_id)
    except PayloadError:
        return "missing", {}
    if manifest is None:
        return "missing", {}
    record = check_record(manifest) or {}
    if release_verified(manifest):
        return "verified", record
    cleaned = cleaned_to(manifest)
    if cleaned and cleaned != payload_id:
        try:
            if payload_dir(root, lineage, cleaned).is_dir():
                return "repoint", record
        except PayloadError:
            pass
    return ("due" if check_due(manifest) else "not_due"), record


__all__ = [
    "IMPORT_CHECK_DEADLINE_SECONDS",
    "MAX_ATTEMPTS",
    "RECORD_ITEMS",
    "RESULT_CLEAN",
    "RESULT_FAILED",
    "RESULT_STALE",
    "RESULT_UNAVAILABLE",
    "RETRY_AFTER_SECONDS",
    "RUN_CHECK_DEADLINE_SECONDS",
    "STAGE_IMPORT",
    "STAGE_RUN",
    "CleanOutcome",
    "ReleaseListing",
    "ReleaseVerdict",
    "check_and_clean",
    "check_due",
    "check_record",
    "cleaned_to",
    "fetch_release_listing",
    "make_record",
    "payload_check_state",
    "rebuild_without",
    "release_orphans",
    "verify_tree",
    "write_check",
]
