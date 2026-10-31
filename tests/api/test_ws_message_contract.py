"""主 WebSocket 出站消息的字段契约快照。

后端经 `app.core.Publisher.send` 把 `app.models.schema` 里的 WS*Data 模型
（`model_dump(mode="json")`，键即字段名）发给前端；前端 `services/websocket/types.ts`
按同名字段消费。字段被误改名或删掉时前后端都不报错，只是界面静默不更新，所以这里把
每种出站消息的字段名集合钉成显式快照。改字段即改对外契约，必须同步改这份快照。
"""

import pytest

from app.models import schema

# 出站消息模型 -> 字段名集合。改动任何一个字段名/删除字段都必须同步这里。
CONTRACT: dict[str, frozenset[str]] = {
    "WSTaskNoticeData": frozenset({"level", "message", "messageKey"}),
    "WSTaskConfigDiscardedData": frozenset({"reason"}),
    "WSSystemNoticeData": frozenset({"level", "title", "lines"}),
    "WSEmulatorOperationData": frozenset(
        {"emulatorId", "index", "operate", "ok", "message"}
    ),
    "WSTaskUserProgressData": frozenset({"current", "total", "task"}),
    "WSTaskUserInfoData": frozenset({"user_id", "name", "status", "progress"}),
    "WSTaskScriptInfoData": frozenset({"script_id", "name", "status", "userList"}),
    "WSTaskCyclePreviewData": frozenset(
        {"queueItemId", "scriptId", "scriptName", "nextRunAt", "isDue", "isRunning"}
    ),
    "WSTaskInfoUpdatedData": frozenset({"task_info", "cycleNextList"}),
    "WSTaskLogUpdatedData": frozenset({"log", "seq", "append", "firstLine"}),
    "WSTaskScriptIdentityData": frozenset({"scriptId", "scriptType"}),
    "WSTaskScriptStartedData": frozenset({"taskId", "runId", "scriptType", "mode"}),
    "WSTaskScriptFinishedData": frozenset(
        {"taskId", "runId", "scriptType", "mode", "outcome", "partialFailure"}
    ),
    "WSTaskCompletedData": frozenset({"result", "outcome", "error", "task_info"}),
    "WSTaskCreatedData": frozenset(
        {"taskId", "mode", "scripts", "queueId", "taskName", "taskType"}
    ),
    "WSPowerCountdownData": frozenset({"operation", "remaining"}),
    "WSPowerSignData": frozenset({"signal"}),
    "WSDisplayMonitorRectData": frozenset({"left", "top", "right", "bottom"}),
    "WSDisplayDetachPromptData": frozenset({"returned", "monitor"}),
    "WSGameSignResultData": frozenset({"result"}),
    "WSUpdateProgressData": frozenset(
        {"downloaded_size", "file_size", "speed", "source"}
    ),
    "WSMaaFWEnvPrepareProgressData": frozenset(
        {"stage", "status", "message", "percent", "log"}
    ),
    "WSMaaFWProjectUpdateProgressData": frozenset(
        {
            "stage",
            "status",
            "message",
            "log",
            "logLevel",
            "percent",
            "downloadedBytes",
            "totalBytes",
            "speedBytesPerSec",
            "packageKind",
            "appliedFiles",
            "totalFiles",
            "extractedFiles",
            "extractTotalFiles",
            "extractedBytes",
            "extractTotalBytes",
        }
    ),
    "WSAvdUpdateProgressData": frozenset(
        {
            "root",
            "stage",
            "status",
            "message",
            "percent",
            "downloadedBytes",
            "totalBytes",
            "speedBytesPerSec",
        }
    ),
    "WSUpdateCompletedData": frozenset({"file"}),
    "WSUpdateFailedData": frozenset({"message"}),
}


@pytest.mark.parametrize("model_name", sorted(CONTRACT))
def test_ws_message_fields_match_snapshot(model_name: str) -> None:
    """每种出站消息的字段名集合必须与快照完全一致（改名/漏字段即变红）。"""

    model = getattr(schema, model_name)
    assert set(model.model_fields) == CONTRACT[model_name]


def test_ws_data_model_set_is_fully_covered() -> None:
    """schema 里所有 WS*Data 出站模型都必须进快照，避免新增消息类型漏登记。"""

    actual = {
        name
        for name, value in vars(schema).items()
        if name.startswith("WS") and name != "WSEnvelope" and isinstance(value, type)
    }
    assert actual == set(CONTRACT)
