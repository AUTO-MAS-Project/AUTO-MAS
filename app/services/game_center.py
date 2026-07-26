"""游戏中心持久化、provider 注册与业务服务。"""

from __future__ import annotations

import asyncio
import json
import re
import threading
import uuid
from abc import ABC
from dataclasses import dataclass
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Awaitable,
    Callable,
    Dict,
    FrozenSet,
    List,
    Literal,
    Mapping,
    Protocol,
)

from pydantic import ValidationError

from app.models.game_center import (
    GameCenterState,
    GamePlatform,
    StoredGame,
    StoredGameCache,
    StoredGameData,
    StoredGameInfo,
    StoredGamePatch,
    StoredGameTask,
    utc_now_iso,
)
from app.utils.atomic_file import atomic_write_json

if TYPE_CHECKING:
    from app.services.game_presets import GamePreset

GameCapability = Literal["check", "install_or_update", "launch", "close"]
GameInstallOutcome = Literal["completed", "handed_off"]
_PROVIDER_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,127}$")


class GameCenterError(RuntimeError):
    """可安全映射到 API 的游戏中心领域错误。"""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class GameCenterPersistenceError(GameCenterError):
    """游戏中心持久化数据不可安全读取或写入。"""

    def __init__(self, message: str) -> None:
        super().__init__(500, message)


@dataclass(frozen=True)
class GameProviderDescriptor:
    """provider 的稳定发现信息。"""

    name: str
    display_name: str
    platforms: FrozenSet[GamePlatform]
    capabilities: FrozenSet[GameCapability]


@dataclass(frozen=True)
class GameCheckResult:
    """provider 检查结果。"""

    local_version: str = ""
    latest_version: str = ""
    needs_update: bool = False
    installed: bool = False


@dataclass(frozen=True)
class GameProgressEvent:
    """provider 上报的安装或更新进度。"""

    phase: Literal["handoff", "download", "verify", "patch", "install"]
    percent: float = 0.0
    downloaded: int = 0
    total: int = 0
    speed: float = 0.0
    message: str = ""


GameProgressCallback = Callable[[GameProgressEvent], Awaitable[None]]


class GameProvider(ABC):
    """游戏 provider 契约。

    provider 仅实现声明在 descriptor.capabilities 中的动作。默认实现明确
    返回不支持，避免未执行操作却报告成功。
    """

    descriptor: GameProviderDescriptor

    async def check(self, game: StoredGame) -> GameCheckResult:
        raise GameCenterError(400, f"provider {self.descriptor.name} 不支持检查")

    async def install_or_update(
        self,
        game: StoredGame,
        progress: GameProgressCallback,
        cancel_event: asyncio.Event,
    ) -> GameInstallOutcome | None:
        raise GameCenterError(
            400,
            f"provider {self.descriptor.name} 不支持安装或更新",
        )

    async def launch(self, game: StoredGame) -> None:
        raise GameCenterError(400, f"provider {self.descriptor.name} 不支持启动")

    async def close(self, game: StoredGame) -> None:
        raise GameCenterError(400, f"provider {self.descriptor.name} 不支持关闭")


@dataclass(frozen=True)
class RegisteredGameProvider:
    """带所有者的 provider 注册记录。"""

    owner: str
    provider: GameProvider


class GameProviderRegistry:
    """线程安全的游戏 provider 注册表。"""

    def __init__(self) -> None:
        self._providers: Dict[str, RegisteredGameProvider] = {}
        self._lock = threading.RLock()

    def register(self, provider: GameProvider, *, owner: str) -> None:
        descriptor = provider.descriptor
        raw_name = descriptor.name
        name = raw_name.strip()
        owner_name = owner.strip()
        if name != raw_name or not _PROVIDER_NAME_RE.fullmatch(name):
            raise ValueError(f"provider 名称不合法: {name!r}")
        if not owner_name:
            raise ValueError("provider owner 不能为空")
        if not descriptor.display_name.strip():
            raise ValueError(f"provider {name} 展示名称不能为空")
        if not descriptor.platforms:
            raise ValueError(f"provider {name} 必须声明至少一个平台")
        if not descriptor.platforms.issubset({"pc", "emulator"}):
            raise ValueError(f"provider {name} 声明了未知平台")
        if not descriptor.capabilities.issubset(
            {"check", "install_or_update", "launch", "close"}
        ):
            raise ValueError(f"provider {name} 声明了未知能力")

        with self._lock:
            existing = self._providers.get(name)
            if existing is not None and existing.owner != owner_name:
                raise ValueError(
                    f"provider 已由其他插件注册: name={name}, owner={existing.owner}"
                )
            self._providers[name] = RegisteredGameProvider(
                owner=owner_name,
                provider=provider,
            )

    def unregister_owner(self, owner: str) -> None:
        owner_name = owner.strip()
        with self._lock:
            self._providers = {
                name: item
                for name, item in self._providers.items()
                if item.owner != owner_name
            }

    def get(self, name: str) -> RegisteredGameProvider | None:
        with self._lock:
            return self._providers.get(name)

    def list(self) -> List[RegisteredGameProvider]:
        with self._lock:
            return [self._providers[name] for name in sorted(self._providers)]


class GameCenterRepository(Protocol):
    """游戏中心持久化接口，便于 Config v2 后续替换后端。"""

    def load(self) -> GameCenterState: ...

    def save(self, state: GameCenterState) -> None: ...


class JsonGameCenterRepository:
    """使用原子 JSON 文件保存游戏条目。"""

    def __init__(self, file_path: Path | None = None) -> None:
        self.file_path = file_path or Path.cwd() / "config" / "GameCenter.json"
        self._lock = threading.RLock()

    def load(self) -> GameCenterState:
        with self._lock:
            if not self.file_path.exists():
                return GameCenterState()
            try:
                payload = json.loads(self.file_path.read_text(encoding="utf-8"))
                return GameCenterState.model_validate(payload)
            except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
                raise GameCenterPersistenceError(
                    f"游戏中心配置损坏，已停止写入: {self.file_path}"
                ) from exc

    def save(self, state: GameCenterState) -> None:
        with self._lock:
            try:
                atomic_write_json(
                    self.file_path,
                    state.model_dump(mode="json"),
                    backup=True,
                    fsync=True,
                    indent=2,
                )
            except OSError as exc:
                raise GameCenterPersistenceError(
                    f"游戏中心配置保存失败: {self.file_path}"
                ) from exc


class GameCenterService:
    """游戏中心正式业务入口。"""

    def __init__(
        self,
        repository: GameCenterRepository,
        *,
        providers: GameProviderRegistry | None = None,
        presets: Mapping[str, GamePreset] | None = None,
    ) -> None:
        self.repository = repository
        self.providers = providers or GameProviderRegistry()
        self.presets = dict(presets or {})
        self._write_lock = asyncio.Lock()
        self._operation_tasks: Dict[
            str,
            asyncio.Task[StoredGameTask | None],
        ] = {}
        self._operation_cancel_events: Dict[str, asyncio.Event] = {}
        self._foreground_actions: set[str] = set()

    def register_provider(self, provider: GameProvider, *, owner: str) -> None:
        self.providers.register(provider, owner=owner)

    def unregister_provider_owner(self, owner: str) -> None:
        self.providers.unregister_owner(owner)

    def list_providers(self) -> List[RegisteredGameProvider]:
        return self.providers.list()

    def list_presets(self) -> List[GamePreset]:
        return list(self.presets.values())

    async def get_games(
        self,
        game_id: str | None = None,
    ) -> tuple[List[str], Dict[str, StoredGame]]:
        state = self.repository.load()
        if game_id is None:
            return list(state.order), {
                item_id: state.games[item_id].model_copy(deep=True)
                for item_id in state.order
            }
        game = state.games.get(game_id)
        if game is None:
            raise GameCenterError(404, f"未找到游戏: {game_id}")
        return [game_id], {game_id: game.model_copy(deep=True)}

    async def add_game(
        self,
        patch: StoredGamePatch,
        *,
        preset_key: str | None = None,
    ) -> StoredGame:
        async with self._write_lock:
            state = self.repository.load()
            game_id = str(uuid.uuid4())
            game = StoredGame(game_id=game_id)
            await self._apply_patch_with_preset_lock(
                game,
                patch,
                preset_key=preset_key,
            )
            state.order.append(game_id)
            state.games[game_id] = game
            self.repository.save(state)
            return game.model_copy(deep=True)

    async def update_game(
        self,
        game_id: str,
        patch: StoredGamePatch,
        *,
        expected_revision: int | None = None,
    ) -> StoredGame:
        async with self._write_lock:
            state = self.repository.load()
            if self._reconcile_interrupted_tasks(state):
                self.repository.save(state)
            self._assert_game_idle(game_id, state)
            game = self._require_game(state, game_id)
            self._check_revision(game, expected_revision)
            await self._apply_patch_with_preset_lock(game, patch)
            game.Revision += 1
            game.UpdatedAt = utc_now_iso()
            self.repository.save(state)
            return game.model_copy(deep=True)

    async def delete_game(
        self,
        game_id: str,
        *,
        expected_revision: int | None = None,
    ) -> None:
        async with self._write_lock:
            state = self.repository.load()
            if self._reconcile_interrupted_tasks(state):
                self.repository.save(state)
            self._assert_game_idle(game_id, state)
            game = self._require_game(state, game_id)
            self._check_revision(game, expected_revision)
            state.order.remove(game_id)
            state.games.pop(game_id)
            state.operations.pop(game_id, None)
            self.repository.save(state)

    async def reorder_games(self, game_ids: List[str]) -> None:
        async with self._write_lock:
            state = self.repository.load()
            if len(game_ids) != len(set(game_ids)):
                raise GameCenterError(400, "游戏顺序包含重复 ID")
            if set(game_ids) != set(state.games):
                raise GameCenterError(400, "游戏顺序必须完整包含现有游戏")
            state.order = list(game_ids)
            self.repository.save(state)

    async def check_game(
        self,
        game_id: str,
        *,
        expected_revision: int | None = None,
    ) -> GameCheckResult:
        async with self._write_lock:
            state = self.repository.load()
            if self._reconcile_interrupted_tasks(state):
                self.repository.save(state)
            self._assert_game_idle(game_id, state)
            stored_game = self._require_game(state, game_id)
            self._check_revision(stored_game, expected_revision)
            game = stored_game.model_copy(deep=True)
            checked_revision = game.Revision
            provider = self._resolve_provider(game, "check")
            self._foreground_actions.add(game_id)

        try:
            result = await provider.check(game)
            async with self._write_lock:
                latest = self.repository.load()
                current = self._require_game(latest, game_id)
                if current.Revision != checked_revision:
                    raise GameCenterError(
                        409,
                        "检查期间游戏配置已更新，结果未写入，请重试",
                    )
                current.Cache = StoredGameCache(
                    LocalVersion=result.local_version,
                    LatestVersion=result.latest_version,
                    NeedsUpdate=result.needs_update,
                    Installed=result.installed,
                    LastChecked=utc_now_iso(),
                )
                current.Revision += 1
                current.UpdatedAt = utc_now_iso()
                self.repository.save(latest)
            return result
        finally:
            async with self._write_lock:
                self._foreground_actions.discard(game_id)

    async def launch_game(
        self,
        game_id: str,
        *,
        expected_revision: int | None = None,
    ) -> str:
        game, provider = await self._begin_foreground_action(
            game_id,
            "launch",
            expected_revision=expected_revision,
        )
        try:
            await provider.launch(game)
            return provider.descriptor.name
        finally:
            await self._end_foreground_action(game_id)

    async def close_game(
        self,
        game_id: str,
        *,
        expected_revision: int | None = None,
    ) -> str:
        game, provider = await self._begin_foreground_action(
            game_id,
            "close",
            expected_revision=expected_revision,
        )
        try:
            await provider.close(game)
            return provider.descriptor.name
        finally:
            await self._end_foreground_action(game_id)

    async def start_install_or_update(
        self,
        game_id: str,
        *,
        expected_revision: int | None = None,
    ) -> StoredGameTask:
        """启动单游戏安装或更新任务。"""

        async with self._write_lock:
            state = self.repository.load()
            if self._reconcile_interrupted_tasks(state):
                self.repository.save(state)
            self._assert_game_idle(game_id, state)
            existing = state.operations.get(game_id)
            if existing is not None and existing.status == "running":
                raise GameCenterError(409, "该游戏已有安装或更新任务运行中")

            stored_game = self._require_game(state, game_id)
            self._check_revision(stored_game, expected_revision)
            game = stored_game.model_copy(deep=True)
            provider = self._resolve_provider(game, "install_or_update")
            operation = StoredGameTask(
                task_id=str(uuid.uuid4()),
                game_id=game_id,
                message="正在准备安装或更新",
            )
            state.operations[game_id] = operation
            self.repository.save(state)

            cancel_event = asyncio.Event()
            self._operation_cancel_events[game_id] = cancel_event
            task = asyncio.create_task(
                self._run_install_or_update(
                    operation.task_id,
                    game,
                    provider,
                    cancel_event,
                )
            )
            self._operation_tasks[game_id] = task
            return operation.model_copy(deep=True)

    async def get_operation_tasks(
        self,
        game_id: str | None = None,
    ) -> Dict[str, StoredGameTask]:
        """返回当前或最近一次任务；页面刷新后仍可恢复显示。"""

        async with self._write_lock:
            state = self.repository.load()
            if self._reconcile_interrupted_tasks(state):
                self.repository.save(state)
            if game_id is not None:
                self._require_game(state, game_id)
                operation = state.operations.get(game_id)
                return (
                    {game_id: operation.model_copy(deep=True)}
                    if operation is not None
                    else {}
                )
            return {
                item_id: operation.model_copy(deep=True)
                for item_id, operation in state.operations.items()
            }

    async def cancel_operation(
        self,
        game_id: str,
        *,
        expected_task_id: str,
        expected_revision: int | None = None,
    ) -> StoredGameTask:
        """取消正在运行的安装或更新，并等待终态落盘。"""

        async with self._write_lock:
            state = self.repository.load()
            game = self._require_game(state, game_id)
            self._check_revision(game, expected_revision)
            operation = state.operations.get(game_id)
            if operation is not None and operation.task_id != expected_task_id:
                raise GameCenterError(409, "任务已变化，请刷新后重试")
            task = self._operation_tasks.get(game_id)
            cancel_event = self._operation_cancel_events.get(game_id)
            if (
                operation is None
                or operation.status != "running"
                or task is None
                or task.done()
            ):
                raise GameCenterError(409, "该游戏当前没有可取消的运行任务")
            if cancel_event is None:
                raise GameCenterError(500, "任务取消状态不可用，请刷新后重试")
            cancel_event.set()
            task.cancel()

        try:
            terminal = await task
        except asyncio.CancelledError:
            terminal = await self._finish_operation(
                expected_task_id,
                game_id,
                status="cancelled",
                phase="cancelled",
                default_message="任务已取消",
            )

        if terminal is None or terminal.task_id != expected_task_id:
            raise GameCenterError(409, "任务已变化，请刷新后重试")
        if terminal.status != "cancelled":
            raise GameCenterError(409, "任务已结束，未执行取消")
        return terminal

    async def cleanup_operations(self) -> None:
        """应用关闭时取消仍在执行的任务。"""

        async with self._write_lock:
            tasks = list(self._operation_tasks.values())
            for cancel_event in self._operation_cancel_events.values():
                cancel_event.set()
            for task in tasks:
                if not task.done():
                    task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_install_or_update(
        self,
        task_id: str,
        game: StoredGame,
        provider: GameProvider,
        cancel_event: asyncio.Event,
    ) -> StoredGameTask | None:
        game_id = game.game_id

        async def report(event: GameProgressEvent) -> None:
            await self._update_operation_progress(task_id, game_id, event)

        try:
            outcome = await provider.install_or_update(game, report, cancel_event)
            if cancel_event.is_set():
                raise asyncio.CancelledError
            if outcome == "handed_off":
                return await self._finish_operation(
                    task_id,
                    game_id,
                    status="handed_off",
                    phase="awaiting_user",
                    default_message="已交给官方启动器，请在启动器内继续",
                )
            return await self._finish_operation(
                task_id,
                game_id,
                status="completed",
                phase="completed",
                default_message="安装或更新操作已完成",
            )
        except asyncio.CancelledError:
            return await self._finish_operation(
                task_id,
                game_id,
                status="cancelled",
                phase="cancelled",
                default_message="任务已取消",
            )
        except Exception as exc:
            return await self._finish_operation(
                task_id,
                game_id,
                status="failed",
                phase="failed",
                default_message=str(exc) or type(exc).__name__,
            )
        finally:
            async with self._write_lock:
                self._operation_tasks.pop(game_id, None)
                self._operation_cancel_events.pop(game_id, None)

    async def _update_operation_progress(
        self,
        task_id: str,
        game_id: str,
        event: GameProgressEvent,
    ) -> None:
        async with self._write_lock:
            state = self.repository.load()
            operation = state.operations.get(game_id)
            if (
                operation is None
                or operation.task_id != task_id
                or operation.status != "running"
            ):
                return
            operation.phase = event.phase
            operation.percent = min(max(event.percent, 0.0), 100.0)
            operation.downloaded = max(event.downloaded, 0)
            operation.total = max(event.total, 0)
            operation.speed = max(event.speed, 0.0)
            operation.message = event.message
            operation.updated_at = utc_now_iso()
            self.repository.save(state)

    async def _finish_operation(
        self,
        task_id: str,
        game_id: str,
        *,
        status: Literal["handed_off", "completed", "failed", "cancelled"],
        phase: Literal["awaiting_user", "completed", "failed", "cancelled"],
        default_message: str,
    ) -> StoredGameTask | None:
        async with self._write_lock:
            state = self.repository.load()
            operation = state.operations.get(game_id)
            if operation is None or operation.task_id != task_id:
                return None
            now = utc_now_iso()
            operation.status = status
            operation.phase = phase
            operation.percent = (
                100.0
                if status in {"handed_off", "completed"}
                else operation.percent
            )
            if status in {"handed_off", "completed"}:
                operation.message = operation.message or default_message
            else:
                operation.message = default_message
            operation.updated_at = now
            operation.finished_at = now
            self.repository.save(state)
            return operation.model_copy(deep=True)

    def _assert_game_idle(
        self,
        game_id: str,
        state: GameCenterState | None = None,
    ) -> None:
        if game_id in self._foreground_actions:
            raise GameCenterError(409, "该游戏已有操作正在执行，请稍后重试")
        task = self._operation_tasks.get(game_id)
        if task is not None and not task.done():
            raise GameCenterError(409, "该游戏已有安装或更新任务，请先取消任务")
        operation = state.operations.get(game_id) if state is not None else None
        if operation is not None and operation.status == "running":
            raise GameCenterError(409, "该游戏已有安装或更新任务，请先取消任务")

    async def _begin_foreground_action(
        self,
        game_id: str,
        capability: GameCapability,
        *,
        expected_revision: int | None = None,
    ) -> tuple[StoredGame, GameProvider]:
        async with self._write_lock:
            state = self.repository.load()
            if self._reconcile_interrupted_tasks(state):
                self.repository.save(state)
            self._assert_game_idle(game_id, state)
            stored_game = self._require_game(state, game_id)
            self._check_revision(stored_game, expected_revision)
            game = stored_game.model_copy(deep=True)
            provider = self._resolve_provider(game, capability)
            self._foreground_actions.add(game_id)
            return game, provider

    async def _end_foreground_action(self, game_id: str) -> None:
        async with self._write_lock:
            self._foreground_actions.discard(game_id)

    def _reconcile_interrupted_tasks(self, state: GameCenterState) -> bool:
        changed = False
        now = utc_now_iso()
        for game_id, operation in state.operations.items():
            task = self._operation_tasks.get(game_id)
            if operation.status == "running" and (task is None or task.done()):
                operation.status = "failed"
                operation.phase = "failed"
                operation.message = "宿主已重启或任务执行中断，请重新开始"
                operation.updated_at = now
                operation.finished_at = now
                changed = True
        return changed

    @staticmethod
    def _require_game(state: GameCenterState, game_id: str) -> StoredGame:
        game = state.games.get(game_id)
        if game is None:
            raise GameCenterError(404, f"未找到游戏: {game_id}")
        return game

    @staticmethod
    def _check_revision(game: StoredGame, expected_revision: int | None) -> None:
        if expected_revision is not None and game.Revision != expected_revision:
            raise GameCenterError(
                409,
                f"游戏配置已更新，请刷新后重试: expected={expected_revision}, actual={game.Revision}",
            )

    async def _apply_patch_with_preset_lock(
        self,
        game: StoredGame,
        patch: StoredGamePatch,
        *,
        preset_key: str | None = None,
    ) -> None:
        requested_key = preset_key
        if requested_key is None and patch.Info is not None:
            requested_key = patch.Info.PresetKey
        requested_key = requested_key or game.Info.PresetKey
        if not requested_key:
            self._apply_patch(game, patch)
            return

        preset = self.presets.get(requested_key)
        if preset is None:
            raise GameCenterError(400, f"尚未注册游戏预设: {requested_key}")

        previous_key = game.Info.PresetKey
        patch_data = patch.Data
        fields_set = patch_data.model_fields_set if patch_data is not None else set()

        if preset.platform == "pc":
            install_path = (
                patch_data.InstallPath
                if patch_data is not None and "InstallPath" in fields_set
                else game.Data.InstallPath
            )
            launch_args = (
                patch_data.LaunchArgs
                if patch_data is not None and "LaunchArgs" in fields_set
                else game.Data.LaunchArgs
            )
            locked_data = StoredGameData(
                InstallPath=install_path,
                LaunchArgs=launch_args,
            )
        else:
            emulator_id = (
                patch_data.EmulatorId
                if patch_data is not None and "EmulatorId" in fields_set
                else game.Data.EmulatorId
            )
            emulator_index = (
                patch_data.EmulatorIndex
                if patch_data is not None and "EmulatorIndex" in fields_set
                else game.Data.EmulatorIndex
            )
            locked_data = StoredGameData(
                PackageName=preset.package_name or None,
                EmulatorId=emulator_id,
                EmulatorIndex=emulator_index or "0",
                AdbPath=await self._derive_emulator_adb_path(emulator_id),
            )

        game.Info = StoredGameInfo(
            Name=preset.name,
            Platform=preset.platform,
            Provider=preset.provider,
            PresetKey=preset.key,
        )
        game.Data = locked_data
        if previous_key and previous_key != preset.key:
            game.Cache = StoredGameCache()

    @staticmethod
    async def _derive_emulator_adb_path(emulator_id: str | None) -> str | None:
        if not emulator_id:
            return None
        from app.plugins.emulator_compat import get_emulator_service

        try:
            _, payload = await get_emulator_service().get_config(emulator_id)
        except Exception as exc:
            raise GameCenterError(
                400,
                f"无法读取所选模拟器配置: {exc}",
            ) from exc

        config: object = payload
        if isinstance(payload, Mapping) and emulator_id in payload:
            config = payload[emulator_id]
        if not isinstance(config, Mapping):
            raise GameCenterError(400, "所选模拟器配置格式不正确")
        info = config.get("Info")
        raw_path = info.get("Path") if isinstance(info, Mapping) else None
        if not isinstance(raw_path, str) or not raw_path.strip():
            return None
        executable = Path(raw_path.strip()).expanduser()
        return str(executable.parent / "adb.exe")

    @staticmethod
    def _apply_patch(game: StoredGame, patch: StoredGamePatch) -> None:
        try:
            if patch.Info is not None:
                for name, value in patch.Info.model_dump(exclude_unset=True).items():
                    setattr(game.Info, name, value)
            if patch.Data is not None:
                for name, value in patch.Data.model_dump(exclude_unset=True).items():
                    setattr(game.Data, name, value)
            game.Info = StoredGameInfo.model_validate(game.Info.model_dump())
        except ValidationError as exc:
            raise GameCenterError(400, "游戏配置字段不合法") from exc

    def _load_game_copy(self, game_id: str) -> StoredGame:
        state = self.repository.load()
        return self._require_game(state, game_id).model_copy(deep=True)

    def _resolve_provider(
        self,
        game: StoredGame,
        capability: GameCapability,
    ) -> GameProvider:
        provider_name = game.Info.Provider.strip()
        if not provider_name:
            raise GameCenterError(400, "游戏尚未配置 provider")
        registered = self.providers.get(provider_name)
        if registered is None:
            raise GameCenterError(503, f"provider 当前不可用: {provider_name}")
        descriptor = registered.provider.descriptor
        if game.Info.Platform not in descriptor.platforms:
            raise GameCenterError(
                400,
                f"provider {provider_name} 不支持平台 {game.Info.Platform}",
            )
        if capability not in descriptor.capabilities:
            raise GameCenterError(400, f"provider {provider_name} 不支持 {capability}")
        return registered.provider


_default_service: GameCenterService | None = None
_default_service_lock = threading.RLock()


def get_default_game_center_service() -> GameCenterService:
    """返回宿主系统插件共享的游戏中心服务。"""

    global _default_service
    with _default_service_lock:
        if _default_service is None:
            from app.services.game_presets import BUILTIN_GAME_PRESETS
            from app.services.game_providers import register_builtin_game_providers

            service = GameCenterService(
                JsonGameCenterRepository(),
                presets=BUILTIN_GAME_PRESETS,
            )
            register_builtin_game_providers(service)
            _default_service = service
        return _default_service


__all__ = [
    "GameCapability",
    "GameCenterError",
    "GameCenterPersistenceError",
    "GameCenterRepository",
    "GameCenterService",
    "GameCheckResult",
    "GameProgressCallback",
    "GameProgressEvent",
    "GameProvider",
    "GameProviderDescriptor",
    "GameProviderRegistry",
    "JsonGameCenterRepository",
    "RegisteredGameProvider",
    "get_default_game_center_service",
]
