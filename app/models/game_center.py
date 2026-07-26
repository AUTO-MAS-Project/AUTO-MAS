"""游戏中心内部持久化模型。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


GamePlatform = Literal["pc", "emulator"]
GameTaskAction = Literal["install_or_update"]
GameTaskPhase = Literal[
    "queued",
    "handoff",
    "download",
    "verify",
    "patch",
    "install",
    "awaiting_user",
    "completed",
    "failed",
    "cancelled",
]
GameTaskStatus = Literal[
    "running",
    "handed_off",
    "completed",
    "failed",
    "cancelled",
]


def utc_now_iso() -> str:
    """返回稳定的 UTC 时间字符串。"""

    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds") + "Z"


class StoredGameInfo(BaseModel):
    """持久化的游戏基础信息。"""

    model_config = ConfigDict(extra="allow")

    Name: str = Field(default="新游戏", min_length=1, max_length=128)
    Platform: GamePlatform = "pc"
    Provider: str = Field(default="", max_length=128)
    PresetKey: Optional[str] = Field(default=None, max_length=128)


class StoredGameData(BaseModel):
    """持久化的游戏运行定位信息。"""

    model_config = ConfigDict(extra="allow")

    InstallPath: Optional[str] = None
    PackageName: Optional[str] = None
    EmulatorId: Optional[str] = None
    EmulatorIndex: Optional[str] = None
    AdbPath: Optional[str] = None
    LaunchArgs: Optional[str] = None


class StoredGameCache(BaseModel):
    """由 provider 检查结果维护的非权威缓存。"""

    model_config = ConfigDict(extra="allow")

    LocalVersion: str = ""
    LatestVersion: str = ""
    NeedsUpdate: bool = False
    Installed: bool = False
    LastChecked: Optional[str] = None


class StoredGame(BaseModel):
    """单个游戏条目的持久化形态。"""

    model_config = ConfigDict(extra="allow")

    game_id: str
    Info: StoredGameInfo = Field(default_factory=StoredGameInfo)
    Data: StoredGameData = Field(default_factory=StoredGameData)
    Cache: StoredGameCache = Field(default_factory=StoredGameCache)
    Revision: int = Field(default=1, ge=1)
    CreatedAt: str = Field(default_factory=utc_now_iso)
    UpdatedAt: str = Field(default_factory=utc_now_iso)


class StoredGameInfoPatch(BaseModel):
    """可更新的游戏基础信息。"""

    Name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    Platform: Optional[GamePlatform] = None
    Provider: Optional[str] = Field(default=None, max_length=128)
    PresetKey: Optional[str] = Field(default=None, max_length=128)


class StoredGameDataPatch(BaseModel):
    """可更新的游戏运行定位信息。"""

    InstallPath: Optional[str] = None
    PackageName: Optional[str] = None
    EmulatorId: Optional[str] = None
    EmulatorIndex: Optional[str] = None
    AdbPath: Optional[str] = None
    LaunchArgs: Optional[str] = None


class StoredGamePatch(BaseModel):
    """游戏条目的局部更新。"""

    Info: Optional[StoredGameInfoPatch] = None
    Data: Optional[StoredGameDataPatch] = None


class StoredGameTask(BaseModel):
    """游戏安装或更新任务的可恢复状态。"""

    task_id: str
    game_id: str
    action: GameTaskAction = "install_or_update"
    status: GameTaskStatus = "running"
    phase: GameTaskPhase = "queued"
    percent: float = Field(default=0.0, ge=0.0, le=100.0)
    downloaded: int = Field(default=0, ge=0)
    total: int = Field(default=0, ge=0)
    speed: float = Field(default=0.0, ge=0.0)
    message: str = ""
    started_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    finished_at: Optional[str] = None


class GameCenterState(BaseModel):
    """游戏中心存储根。"""

    model_config = ConfigDict(extra="allow")

    version: Literal[1] = 1
    order: List[str] = Field(default_factory=list)
    games: Dict[str, StoredGame] = Field(default_factory=dict)
    operations: Dict[str, StoredGameTask] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_index(self) -> "GameCenterState":
        """拒绝会造成条目丢失或重复的损坏索引。"""

        if len(self.order) != len(set(self.order)):
            raise ValueError("游戏中心索引包含重复 ID")
        if set(self.order) != set(self.games):
            raise ValueError("游戏中心索引与数据不一致")
        for game_id, game in self.games.items():
            if game.game_id != game_id:
                raise ValueError(f"游戏中心条目 ID 不一致: {game_id}")
        for game_id, task in self.operations.items():
            if game_id not in self.games or task.game_id != game_id:
                raise ValueError(f"游戏中心任务引用了不存在的游戏: {game_id}")
        return self


__all__ = [
    "GameCenterState",
    "GamePlatform",
    "GameTaskAction",
    "GameTaskPhase",
    "GameTaskStatus",
    "StoredGame",
    "StoredGameCache",
    "StoredGameData",
    "StoredGameDataPatch",
    "StoredGameInfo",
    "StoredGameInfoPatch",
    "StoredGamePatch",
    "StoredGameTask",
    "utc_now_iso",
]
