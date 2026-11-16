"""Queue config builders shared by scheduler regression tests."""

from datetime import timedelta

from app.models.config import QueueConfig, QueueItem, TimeSet


async def make_queue(queues, sid, *, now, startup="Never", timed=False, cycle=True):
    qid = queues.add(
        QueueConfig,
        payload={
            "Info": {
                "StartUpMode": startup,
                "TimeEnabled": timed,
                "CycleEnabled": cycle,
            },
            "Cycle": {"IntervalMinutes": 60, "LastRunAt": now - timedelta(hours=1)},
        },
    )
    await queues.commit()
    queues[qid].QueueItem.add(QueueItem, payload={"Info": {"ScriptId": str(sid)}})
    await queues[qid].QueueItem.commit()
    if timed:
        queues[qid].TimeSet.add(
            TimeSet,
            payload={
                "Info": {
                    "Time": now.replace(second=0, microsecond=0),
                    "Days": [now.strftime("%A")],
                }
            },
        )
        await queues[qid].TimeSet.commit()
    return qid, queues[qid]
