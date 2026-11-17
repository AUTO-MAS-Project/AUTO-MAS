import json
import uuid
from pathlib import Path
from typing import cast

from auto_mas_core.host.core import Config
from auto_mas_core.host.task_proxy_helpers import (
    CONFIG_BASE_NATIVE,
    CONFIG_BASE_SHARED,
    read_config_base,
)
from auto_mas_core.host.utils import get_logger
from auto_mas_core.host.utils import io as _utils_io

from maa_adapter.config.script import MaaConfig

logger = get_logger("MAA")


async def set_infrastructure(script_id: str, user_id: str, jsonFile: str) -> None:
    """校验并读取用户选择的基建文件，将其原生内容保存到对应 MAA 账号配置。"""
    from maa_adapter.native.config import infrast_format_problem

    logger.info(f"{script_id} - {user_id} 设置基建配置: {jsonFile}")

    script_uid = uuid.UUID(script_id)
    user_uid = uuid.UUID(user_id)
    json_path = Path(jsonFile)

    if not json_path.exists():
        raise FileNotFoundError(f"文件未找到: {json_path}")

    script = Config.ScriptConfig[script_uid]
    if not isinstance(script, MaaConfig):
        raise TypeError(f"托管 {script_id} 不是 MAA 脚本, 无法设置基建配置")

    try:
        infrast_data = json.loads(
            json_path.read_text(encoding="utf-8").removeprefix("\ufeff")
        )
    except json.JSONDecodeError as e:
        raise ValueError("排班表不是有效的 JSON") from e

    problem = infrast_format_problem(infrast_data)
    if problem is not None:
        raise ValueError(problem)

    # 如果标题为默认标题, 则使用文件名作为标题
    if infrast_data.get("title", "文件标题") == "文件标题":
        infrast_data["title"] = json_path.stem

    await script.UserData[user_uid].update(
        type(script.UserData[user_uid]).model_validate(
            {"Data": {"CustomInfrast": json.dumps(infrast_data, ensure_ascii=False)}}
        ),
        check_visibility=False,
    )


def _infrast_config_dir(script_id: str, user_id: str) -> Path:
    """基建班次的事实源目录: 托管=配置来源存档, 原生来源=MAA 当前生效配置。

    与 AutoProxy._config_archive_dir 的来源判定对称; 原生来源不落存档,
    MAA 安装目录的现有配置即持久存储。
    """

    script_uid = uuid.UUID(script_id)
    user_uid = uuid.UUID(user_id)
    script_config = Config.ScriptConfig[script_uid]
    if isinstance(script_config, MaaConfig) and user_uid in script_config.UserData:
        base = read_config_base(script_config.UserData[user_uid])
        if base == CONFIG_BASE_SHARED:
            return Path.cwd() / f"data/{script_id}/Default/ConfigFile"
        if base == CONFIG_BASE_NATIVE:
            root_path = script_config.Info.Path
            if root_path is None:
                raise ValueError("Path未配置，请检查路径设置")
            return root_path / "config"
    return Path.cwd() / f"data/{script_id}/{user_id}/ConfigFile"


def _infrast_plans(script_id: str, user_id: str) -> tuple[list[dict], str | None, str]:
    """生效排班表 (plans, problem, state), 与运行时使用的那份同源。

    原生来源且关闭覆写常规配置时 set_maa 跳过注入, 运行时直接用 MAA 原生配置,
    排班表只存在原生的 Infrast 任务里(InfrastPlan 不落盘, 事实源是
    Filename 指向的排班文件); 其余组合(托管 / 原生来源+覆写常规配置)都由 MAS
    注入存档排班表。若不加区分地对原生来源读 MAS 存档, 原生来源账号的班次会被
    空存档误拒; 反过来在原生来源+覆写常规配置下读原生配置, 又会与运行时不一致。
    """

    from maa_adapter.native.config import (
        infrast_plan_state,
        load_infrast_plans,
        maa_scheme_name,
        maa_task_queue,
        read_maa_config,
    )

    script_config = cast(MaaConfig, Config.ScriptConfig[uuid.UUID(script_id)])
    user_config = script_config.UserData[uuid.UUID(user_id)]
    if (
        read_config_base(user_config) != CONFIG_BASE_NATIVE
        or user_config.Info.IfQuickConfig
    ):
        raw = user_config.Data.CustomInfrast
        plans, problem = load_infrast_plans(raw)
        return plans, problem, infrast_plan_state(raw)

    config_dir = _infrast_config_dir(script_id, user_id)
    data = read_maa_config(config_dir / "gui.new.json")
    if data is None:
        return [], "未找到或无法读取 MAA 原生配置", "empty"
    queue = maa_task_queue(data, maa_scheme_name(data))
    if not isinstance(queue, list):
        return [], "MAA 原生配置缺少任务队列", "empty"
    for task in queue:
        if not isinstance(task, dict) or task.get("TaskType") != "Infrast":
            continue
        if task.get("Mode") != "Custom":
            return [], "MAA 原生配置未启用自定义基建", "empty"
        filename = task.get("Filename")
        if not isinstance(filename, str) or not filename.strip():
            return [], "MAA 原生配置没有指定排班文件", "empty"
        path = Path(filename.strip())
        if not path.is_file():
            return [], f"MAA 原生排班文件不存在: {path.name}", "empty"
        try:
            text = path.read_text(encoding="utf-8").removeprefix("\ufeff")
        except OSError:
            logger.opt(exception=True).warning(f"读取 MAA 原生排班文件失败: {path}")
            return [], f"MAA 原生排班文件无法读取: {path.name}", "empty"
        plans, problem = load_infrast_plans(text)
        return plans, problem, infrast_plan_state(text)
    return [], "MAA 原生配置中没有基建任务", "empty"


def _infrast_plan_owned_by_mas(script_id: str, user_id: str) -> bool:
    """班次指针是否由 MAS 账号字段管理, 与 set_maa 的注入判定同源。

    覆写常规配置开着时 MAS 注入排班表, 班次由 MAS 决定: 带时段表一律交 MAA 按
    时段选班, 无时段表注入用户自己的 ``Data.InfrastPlanIndex``。关着时 MAS
    不注入, MAA 跑的是来源配置自己的队列, 班次仍在那份配置的 PlanSelect 里。
    """

    script_config = cast(MaaConfig, Config.ScriptConfig[uuid.UUID(script_id)])
    user_config = script_config.UserData[uuid.UUID(user_id)]
    return bool(user_config.Info.IfQuickConfig)


async def set_infrast_plan_select(script_id: str, user_id: str, index: int) -> int:
    """把用户选定的基建班次写入该账号的事实源。

    index 与 MAA 原生语义一致: -1=自动, 0..n-1=从该班开始顺序轮换。MAS 注入
    的组合下事实源是账号配置的 ``Data.InfrastPlanIndex``(每账号一份, 推进由
    MAS 在基建换班完成后做), 带时段表只接受 -1; 原生来源且关覆写常规配置时写 MAA
    原生配置。写不进去时抛异常(而不是返回入参假装成功), 由接口层转成错误响应。
    """

    from maa_adapter.native.config import (
        maa_scheme_name,
        maa_task_queue,
        read_maa_config,
    )

    script_uid = uuid.UUID(script_id)
    user_uid = uuid.UUID(user_id)
    script_config = Config.ScriptConfig[script_uid]
    if not isinstance(script_config, MaaConfig):
        raise TypeError(f"托管 {script_id} 不是 MAA 脚本, 无法设置基建班次")
    if index < -1:
        raise ValueError("基建班次索引不能小于 -1")
    if user_uid not in script_config.UserData:
        raise ValueError(f"托管 {script_id} 下不存在账号 {user_id}")

    # 显式班次要落在 -1..班次数-1 内: MAA 侧只会把越界值静默修正成第一班
    # 或直接报错, 与其静默改掉用户的选择不如在入口拒绝; -1 是默认值无需校验
    plans, problem, state = _infrast_plans(script_id, user_id)
    if index >= 0:
        if problem is not None:
            raise ValueError(f"自定义基建排班不可用, 无法设置基建班次: {problem}")
        if index >= len(plans):
            raise ValueError(
                f"基建班次索引 {index} 超出排班表范围, 该排班表共 {len(plans)} 个班次"
            )

    if _infrast_plan_owned_by_mas(script_id, user_id):
        if state == "period":
            if index >= 0:
                raise ValueError(
                    "带时间段的排班表由 MAA 按时段自动换班, 不支持手选班次"
                )
            return -1
        # 无时段表: -1(自动)即从第一班起, 指针只存 0..n-1
        next_index = max(index, 0)
        await script_config.UserData[user_uid].update(
            type(script_config.UserData[user_uid]).model_validate(
                {"Data": {"InfrastPlanIndex": next_index}}
            ),
            check_visibility=False,
        )
        return next_index

    config_dir = _infrast_config_dir(script_id, user_id)
    data = read_maa_config(config_dir / "gui.new.json")
    if data is None:
        raise ValueError("未找到或无法读取该账号的 MAA 配置, 无法设置基建班次")
    scheme = maa_scheme_name(data)
    queue = maa_task_queue(data, scheme)
    if not isinstance(queue, list):
        raise ValueError(f"MAA 配置的方案「{scheme}」缺少任务队列, 无法设置基建班次")
    tasks = [
        task
        for task in queue
        if isinstance(task, dict) and task.get("TaskType") == "Infrast"
    ]
    if not tasks:
        raise ValueError(f"MAA 配置的方案「{scheme}」中没有基建任务, 无法设置基建班次")
    if all(task.get("PlanSelect") == index for task in tasks):
        return index
    for task in tasks:
        task["PlanSelect"] = index
    _utils_io.write_file(config_dir / "gui.new.json", data)
    return index


async def get_infrast_plan_select(script_id: str, user_id: str) -> int:
    """读取当前基建班次索引; 带时段表 / 未设置过时返回 -1(自动)。

    MAS 注入的组合下, 无时段表返回账号字段里的指针(下次从该班开始);
    原生来源且关覆写常规配置时读 MAA 原生配置。
    """

    from maa_adapter.native.config import (
        maa_scheme_name,
        maa_task_queue,
        read_maa_config,
    )

    script_uid = uuid.UUID(script_id)
    if script_uid not in Config.ScriptConfig:
        return -1
    script_config = Config.ScriptConfig[script_uid]
    if not isinstance(script_config, MaaConfig):
        return -1
    user_uid = uuid.UUID(user_id)
    if user_uid not in script_config.UserData:
        return -1
    if _infrast_plan_owned_by_mas(script_id, user_id):
        plans, problem, state = _infrast_plans(script_id, user_id)
        if problem is not None or state != "rotate":
            return -1
        return int(script_config.UserData[user_uid].Data.InfrastPlanIndex) % len(plans)
    config_dir = _infrast_config_dir(script_id, user_id)
    data = read_maa_config(config_dir / "gui.new.json")
    if data is None:
        return -1
    queue = maa_task_queue(data, maa_scheme_name(data))
    if not isinstance(queue, list):
        return -1
    for task in queue:
        if isinstance(task, dict) and task.get("TaskType") == "Infrast":
            plan_select = task.get("PlanSelect")
            return int(plan_select) if isinstance(plan_select, int) else -1
    return -1


async def get_user_combox_infrastructure(script_id: str, user_id: str) -> dict:
    """读取指定账号的自定义基建资料，生成当前可选排班项及可用状态。"""
    logger.info(f"获取用户自定义基建排班下拉框信息: {script_id} - {user_id}")

    script_uid = uuid.UUID(script_id)
    user_uid = uuid.UUID(user_id)

    script_config = Config.ScriptConfig[script_uid]

    # 根据托管类型选择添加对应账号配置
    if not isinstance(script_config, MaaConfig):
        raise TypeError(f"不支持的托管配置类型: {type(script_config)}")

    logger.info("开始获取用户自定义基建排班下拉框信息")

    user_config = script_config.UserData[user_uid]
    plans, problem, state = _infrast_plans(script_id, user_id)
    # 仅自定义模式下不可用才值得提醒; 普通模式空排班表是正常状态
    if problem is not None and user_config.Task.InfrastMode == "Custom":
        logger.warning(f"自定义基建排班不可用, 下拉选项按空返回: {problem}")
    data = []
    for i, plan in enumerate(plans):
        ranges = plan.get("period")
        period = ""
        if isinstance(ranges, list):
            period = ", ".join(
                f"{r[0]}-{r[1]}" for r in ranges if isinstance(r, list) and len(r) >= 2
            )
        data.append(
            {
                "label": plan.get("name", f"排班 {i + 1}"),
                "value": str(i),
                "period": period or None,
            }
        )

    logger.success("用户自定义基建排班下拉框信息获取成功")

    return {"state": state, "data": data}
