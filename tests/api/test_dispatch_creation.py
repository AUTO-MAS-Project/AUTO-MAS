"""公开创建契约始终只有一个顶层入口。"""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.dispatch import TaskCreateIn
from app.models.task import TaskMode


@pytest.mark.parametrize("mode", list(TaskMode))
@pytest.mark.parametrize("count", [0, 1, 2])
def test_creation_requires_exactly_one_root(mode, count):
    tasks = {
        str(index): {
            "uid": str(uuid4()),
            "children": {"0": {"uid": str(uuid4())}},
        }
        for index in range(count)
    }
    if count == 1:
        body = TaskCreateIn.model_validate({"mode": mode, "tasks": tasks})
        assert list(body.tasks) == [0]
    else:
        with pytest.raises(ValidationError) as error:
            TaskCreateIn.model_validate({"mode": mode, "tasks": tasks})
        assert error.value.errors()[0]["loc"] == ("tasks",)
