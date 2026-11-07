"""定时开关的写入约束由模型信号执行，直接操作也必须回滚并上抛。"""

import pytest
import pytest_asyncio

from app.config import ConfigCollection, config_manager
from app.config.errors import ConfigAggregateError
from app.models.config import QueueConfig, TimeSet


@pytest_asyncio.fixture
async def disabled_queue():
    queue = QueueConfig.build(payload={"Info": {"TimeEnabled": True}})
    await queue.activate()
    for _ in range(2):
        queue.TimeSet.add(TimeSet)
    await queue.TimeSet.commit()
    queue.Info.TimeEnabled = False
    await queue.commit()
    return queue


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["add", "remove", "order", "write", "update"])
async def test_disabled_time_model_rejects_and_rolls_back_all_write_paths(
    disabled_queue, operation
):
    queue = disabled_queue
    item = next(iter(queue.TimeSet.values()))
    before = queue.model_dump(context={"audience": "persist"})

    async def change():
        if operation == "add":
            queue.TimeSet.add(TimeSet)
        elif operation == "remove":
            queue.TimeSet.remove(item.uid)
        elif operation == "order":
            queue.TimeSet.set_order(list(reversed(list(queue.TimeSet.keys()))))
        elif operation == "write":
            item.Info.Days = []
            await item.commit()
            return
        else:
            await item.update(
                TimeSet.model_validate({"Info": {"Days": []}}), check_visibility=False
            )
            return
        await queue.TimeSet.commit()

    with pytest.raises(ConfigAggregateError):
        await change()
    assert queue.model_dump(context={"audience": "persist"}) == before
    assert not item.deleted
    queue.Info.TimeEnabled = True
    await queue.commit()
    await change()


@pytest.mark.asyncio
@pytest.mark.parametrize("fast_init", [False, True])
async def test_disabled_time_settings_load_without_runtime_write_guard(
    disabled_queue, fast_init
):
    payload = disabled_queue.model_dump(context={"audience": "persist"})
    restored = QueueConfig.build(payload=payload)
    await restored.activate(fast_init=fast_init)
    assert not restored.Info.TimeEnabled
    assert restored.model_dump(context={"audience": "persist"}) == payload


@pytest.mark.asyncio
async def test_time_guard_uses_current_transaction_and_preserves_unrelated_writes(
    disabled_queue,
):
    queue = disabled_queue
    queue.Info.Name = "changed"
    await queue.commit()
    unrelated = ConfigCollection[TimeSet].build([TimeSet])
    await unrelated.activate()
    unrelated.add(TimeSet)
    await unrelated.commit()
    assert queue.Info.Name == "changed" and len(unrelated) == 1

    async with config_manager.transaction():
        queue.Info.TimeEnabled = True
        await queue.commit()
        queue.TimeSet.add(TimeSet)
        await queue.TimeSet.commit()
    before = queue.model_dump(context={"audience": "persist"})
    with pytest.raises(ConfigAggregateError):
        async with config_manager.transaction():
            queue.Info.TimeEnabled = False
            await queue.commit()
            queue.TimeSet.add(TimeSet)
            await queue.TimeSet.commit()
    assert queue.model_dump(context={"audience": "persist"}) == before
