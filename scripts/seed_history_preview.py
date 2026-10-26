"""构造一个月的历史记录预览样例；本地一次性脚本，不入库不提交。

数据形态参考 C:/Program Files/AUTO-MAS 的真实业务记录：
用户名、脚本名、时段节奏、统计键与取值分布均按生产数据镜像；
回放视频与失败截图按真实采集语义只挂在异常（error）记录上，
全月均匀分布以避免被保留期清理；媒体样例取自本机 MAA 目录；
并保留一处统计类型冲突用于预览聚合错误展示。
"""

import asyncio
import random
import shutil
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from app.core.history import HistoryStore
from app.models.schema import HistoryAttachmentInput, HistoryWrite
from app.utils.constants import UTC4

# 生产环境真实节奏：用户 → (脚本, 每日时段档数)
USERS = [
    ("myself", "MAA-1", 4),
    ("Rowletkawa", "MAA-1", 4),
    ("渊", "MAA-1", 3),
    ("小莫不异格不改名", "MAA-1", 2),
    ("Akame", "MAA-2", 4),
    ("Sixen", "MAA-2", 3),
    ("Rage", "MAA-2", 3),
    ("大剑是最好的武器", "MAA-2", 2),
    ("袋泡茶", "MAA-2", 1),
    ("z", "MAA-2", 2),
]
MAAEND_USERS = ("myself", "渊")
SLOT_HOURS = (4, 10, 16, 22)
DAYS = 30

STAGES = ("1-7", "1-7", "YW-8", "YW-8", "CE-6", "PR-A-1")
DROP_ITEMS = ("龙门币", "基础作战记录", "固源岩", "酯原料", "源岩")
ERROR_MESSAGES = (
    "MAA 部分任务执行失败",
    "MAA 部分任务执行失败",
    "MAA 部分任务执行失败",
    "MAA 进程超时",
    "MAA 未能正确登录 PRTS",
    "模拟器启动失败",
    "运行超过 120 分钟，已终止",
)
MAAEND_MESSAGES = (
    "[日常] Success!",
    "[日常] Success!",
    "[送货] Success!",
    "[更新] Success!",
    "[日常] MAS 自建账号切换失败",
    "[送货] MAS 自建账号切换失败",
)
VIDEO_SOURCES = (
    Path(r"D:/AUTO/MAA-2/Res/Video/MaterialSynthesis.mp4"),
    Path(r"D:/AUTO/MAA-2/Res/Video/TouchMode.mp4"),
)
SCREENSHOT_SOURCES = tuple(
    sorted(Path(r"D:/AUTO/MAA-2/debug/battle").glob("*_raw.png"))
)[:6]
VIDEO_LIMIT = 8 * 1024 * 1024 * 1024
VIDEO_MAX = 24
VIDEO_CHANCE = 0.07
SHOT_MAX = 22
SHOT_CHANCE = 0.08


def build_maa_data(rng: random.Random, success: bool) -> dict:
    """按生产键位生成一条 MAA 统计 data。"""

    data = {
        "recruit_statistics": {"kind": "counter", "value": {}},
        "drop_statistics": {"kind": "counter", "value": {}},
        "sanity": {"kind": "snapshot", "value": rng.randint(1, 130)},
        "sanity_full_at": {"kind": "snapshot", "value": ""},
        "maa_result": {"kind": "snapshot", "value": ""},
    }
    if rng.random() < 0.3:
        recruits = {}
        for star, chance in (("3★", 0.8), ("4★", 0.5), ("5★", 0.02)):
            if rng.random() < chance:
                recruits[star] = rng.randint(1, 2)
        data["recruit_statistics"]["value"] = recruits
    if success:
        stage = rng.choice(STAGES)
        data["drop_statistics"]["value"] = {
            stage: {
                item: rng.randint(
                    (700 if item == "龙门币" else 1), (820 if item == "龙门币" else 16)
                )
                for item in DROP_ITEMS
                if rng.random() < 0.85
            }
        }
    full_at = datetime.now(tz=UTC4) + timedelta(
        hours=rng.randint(1, 20), minutes=rng.randint(0, 59)
    )
    data["sanity_full_at"]["value"] = full_at.strftime("理智将在 %Y-%m-%d %H:%M 回满。")
    return data


def build_log(rng: random.Random, when: datetime, message: str) -> str:
    """生成 MAA GUI 风格的执行日志。"""

    def stamp(offset: float) -> str:
        moment = when + timedelta(seconds=offset)
        return (
            f"[{moment.strftime('%Y-%m-%d %H:%M:%S')}.{moment.microsecond // 1000:03d}]"
        )

    lines = [
        f"{stamp(0)}[INF][Bootstrapper]           <2> ===================================",
        f"{stamp(0.01)}[INF][Bootstrapper]           <2> MaaAssistantArknights GUI started",
        f"{stamp(0.02)}[INF][Bootstrapper]           <2> Version v6.20.1",
        f"{stamp(0.03)}[INF][AsstProxy]              <2> AsstSetUserDir ret: true",
        f"{stamp(0.4)}[INF][TaskQueueViewController] <2> Start task: 开始唤醒",
        f"{stamp(3.2)}[INF][AsstProxy]              <2> Start: 开始唤醒",
        f"{stamp(26.5)}[INF][AsstProxy]              <2> Succeeded: 开始唤醒",
        f"{stamp(28.1)}[INF][TaskQueueViewController] <2> Start task: 日常任务",
        f"{stamp(31.0)}[INF][AsstProxy]              <2> Start: {rng.choice(('刷理智', '自动公招', '基建换班'))}",
    ]
    duration = rng.randint(180, 900)
    if message == "Success!":
        lines.append(
            f"{stamp(duration)}[INF][AsstProxy]              <2> Succeeded: 日常任务"
        )
    else:
        lines.append(f"{stamp(duration)}[ERR][AsstProxy]              <2> {message}")
    lines.append(
        f"{stamp(duration + 1)}[INF][VersionUpdateViewState] <2> 任务结束：{message}"
    )
    return "\n".join(lines)


async def main() -> None:
    root = Path.cwd()
    if not (root / "app" / "core" / "history.py").is_file() or "Program Files" in str(
        root
    ):
        raise SystemExit("必须在开发仓库根目录运行，拒绝在其它目录构造样例")

    rng = random.Random(1546)
    for target in (root / "history",):
        if target.exists():
            shutil.rmtree(target)
    for name in (
        "history.db",
        "history.db-journal",
        "history.db-shm",
        "history.db-wal",
    ):
        (root / "data" / name).unlink(missing_ok=True)
    staging = root / "data" / "_seed_replays"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    for source in (*VIDEO_SOURCES, *SCREENSHOT_SOURCES):
        if not source.is_file():
            raise SystemExit(f"样例媒体缺失：{source}")

    store = HistoryStore()
    await store.initialize(video_limit_bytes=VIDEO_LIMIT)
    today = date.today()
    conflict_day = today - timedelta(days=6)
    videos = 0
    shots = 0
    media_bytes = 0
    count = 0
    try:
        for offset in range(DAYS - 1, -1, -1):
            day = today - timedelta(days=offset)
            for username, script, slots in USERS:
                chosen = sorted(rng.sample(SLOT_HOURS, slots))
                for hour in chosen:
                    when = datetime(
                        day.year,
                        day.month,
                        day.day,
                        hour,
                        rng.randint(0, 59),
                        rng.randint(0, 59),
                        tzinfo=UTC4,
                    )
                    roll = rng.random()
                    if roll < 0.62:
                        status, message = "success", "Success!"
                    elif roll < 0.92:
                        status, message = "error", rng.choice(ERROR_MESSAGES)
                    elif roll < 0.96:
                        status, message = "skipped", "MAA 本轮无需执行，已跳过"
                    else:
                        status, message = "cancelled", "任务被用户手动中止"
                    data = build_maa_data(rng, status == "success")
                    data["maa_result"]["value"] = message
                    if (
                        day == conflict_day
                        and username == "Akame"
                        and hour == SLOT_HOURS[2]
                    ):
                        # 唯一一处类型冲突：同键 sanity 在同日以 counter 出现，
                        # 用于预览聚合错误展示；正常任务不会产生这种数据。
                        data["sanity"] = {"kind": "counter", "value": 7}
                    attachments = []
                    if status == "error":
                        # 附件只挂异常记录：失败回放视频与失败截图按真实采集语义分布，
                        # 概率均匀铺满全月，避免集中在前几天被保留期清理。
                        if videos < VIDEO_MAX and rng.random() < VIDEO_CHANCE:
                            source = VIDEO_SOURCES[videos % len(VIDEO_SOURCES)]
                            staged = staging / f"{uuid.uuid4().hex}.mp4"
                            shutil.copy2(source, staged)
                            media_bytes += source.stat().st_size
                            attachments.append(
                                HistoryAttachmentInput(
                                    path=staged,
                                    kind="video",
                                    role="obs_replay",
                                    display_name=staged.name,
                                )
                            )
                            videos += 1
                        if shots < SHOT_MAX and rng.random() < SHOT_CHANCE:
                            source = SCREENSHOT_SOURCES[shots % len(SCREENSHOT_SOURCES)]
                            staged = staging / f"{uuid.uuid4().hex}.png"
                            shutil.copy2(source, staged)
                            media_bytes += source.stat().st_size
                            attachments.append(
                                HistoryAttachmentInput(
                                    path=staged,
                                    kind="image",
                                    role="failure_screenshot",
                                    display_name="失败截图",
                                )
                            )
                            shots += 1
                    count += 1
                    await store.record(
                        HistoryWrite(
                            time=when,
                            username=username,
                            script_name=script,
                            status=status,
                            message=message,
                            logs=build_log(rng, when, message),
                            data=data,
                            attachments=attachments,
                        )
                    )
            if day.weekday() in (2, 5) or rng.random() < 0.25:
                for username in MAAEND_USERS:
                    if rng.random() < 0.6:
                        message = rng.choice(MAAEND_MESSAGES)
                        when = datetime(
                            day.year,
                            day.month,
                            day.day,
                            21,
                            rng.randint(0, 59),
                            rng.randint(0, 59),
                            tzinfo=UTC4,
                        )
                        count += 1
                        await store.record(
                            HistoryWrite(
                                time=when,
                                username=username,
                                script_name="MaaEnd",
                                status="success"
                                if message.endswith("Success!")
                                else "error",
                                message=message,
                                logs=build_log(rng, when, message),
                                data={
                                    "maaend_result": {
                                        "kind": "snapshot",
                                        "value": message,
                                    }
                                },
                            )
                        )
            print(f"已写入 {day.isoformat()}，累计 {count} 条")
        buckets = await store.search(
            start_date=today - timedelta(days=DAYS - 1), end_date=today, mode="MONTHLY"
        )
        total = sum(
            len(bucket.index) for users in buckets.values() for bucket in users.values()
        )
        conflicts = sum(
            len(bucket.aggregate_errors)
            for users in buckets.values()
            for bucket in users.values()
        )
        print(
            f"完成：{total} 条记录，{videos} 个回放视频、{shots} 张失败截图，"
            f"聚合冲突 {conflicts} 组，媒体约 {media_bytes / 1024 / 1024:.1f} MiB"
        )
    finally:
        await store.close()
        shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(main())
