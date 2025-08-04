import uuid

from fastapi import FastAPI, HTTPException, Path, Body
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional, Literal
from datetime import datetime

from fastapi.middleware.cors import CORSMiddleware

from app.core import Config
from app.utils import get_logger

logger = get_logger("API 模块")

app = FastAPI(
    title="AUTO_MAA",
    description="API for managing automation scripts, plans, and tasks",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有域名跨域访问
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有请求方法，如 GET、POST、PUT、DELETE
    allow_headers=["*"],  # 允许所有请求头
)

# 此文件由ai生成 返回值非最终版本


# ======================
# Data Models
# ======================


# Script Models


class BaseOut(BaseModel):
    code: int = Field(default=200, description="状态码")
    status: str = Field(default="success", description="操作状态")
    message: str = Field(default="操作成功", description="操作消息")


class ScriptCreateIn(BaseModel):
    type: Literal["MAA", "General"]


class ScriptCreateOut(BaseOut):
    scriptId: str = Field(..., description="新创建的脚本ID")
    data: Dict[str, Any] = Field(..., description="脚本配置数据")


class ScriptGetIn(BaseModel):
    scriptId: Optional[str] = Field(None, description="脚本ID，仅在模式为Single时需要")


class ScriptGetOut(BaseOut):
    index: List[Dict[str, str]] = Field(..., description="脚本索引列表")
    data: Dict[str, Any] = Field(..., description="脚本列表或单个脚本数据")


class ScriptUpdateIn(BaseModel):
    scriptId: str = Field(..., description="脚本ID")
    data: Dict[str, Any] = Field(..., description="脚本更新数据")


class ScriptUpdateOut(BaseOut):
    message: str = Field(default="脚本更新成功", description="操作消息")


class ScriptDeleteIn(BaseModel):
    scriptId: str = Field(..., description="脚本ID")


class ScriptUser(BaseModel):
    userId: str
    config: Dict[str, Any] = {}


# Plan Models
class PlanDayConfig(BaseModel):
    吃理智药: int
    连战次数: str
    关卡选择: str
    备选_1: str
    备选_2: str
    备选_3: str
    剩余理智: str


class PlanDetails(BaseModel):
    周一: PlanDayConfig
    周二: PlanDayConfig
    周三: PlanDayConfig
    周四: PlanDayConfig
    周五: PlanDayConfig
    周六: PlanDayConfig
    周日: PlanDayConfig


class PlanCreate(BaseModel):
    name: str
    mode: str  # "全局" or "周计划"
    details: PlanDetails


class PlanUpdate(BaseModel):
    name: Optional[str] = None
    mode: Optional[str] = None
    details: Optional[PlanDetails] = None


class PlanModeUpdate(BaseModel):
    mode: str  # "全局" or "周计划"


# Queue Models
class QueueCreate(BaseModel):
    name: str
    scripts: List[str]
    schedule: str
    description: Optional[str] = None


class QueueUpdate(BaseModel):
    name: Optional[str] = None
    scripts: Optional[List[str]] = None
    schedule: Optional[str] = None
    description: Optional[str] = None


# Task Models
class TaskCreate(BaseModel):
    name: str
    scriptId: str
    planId: str
    queueId: Optional[str] = None
    priority: int = 0
    parameters: Dict[str, Any] = {}


# Settings Models
class SettingsUpdate(BaseModel):
    key: str
    value: Any


# ======================
# API Endpoints
# ======================


# @app.get("/api/activity/latest", summary="获取最新活动内容")
# async def get_latest_activity():
#     """
#     获取最新活动内容
#     """
#     # 实现获取最新活动的逻辑
#     return {"status": "success", "data": {}}


@app.post(
    "/api/add/scripts",
    summary="添加脚本",
    response_model=ScriptCreateOut,
    status_code=200,
)
async def add_script(script: ScriptCreateIn = Body(...)) -> ScriptCreateOut:
    """添加脚本"""

    uid, config = await Config.add_script(script.type)
    return ScriptCreateOut(scriptId=str(uid), data=await config.toDict())


@app.post(
    "/api/get/scripts", summary="查询脚本", response_model=ScriptGetOut, status_code=200
)
async def get_scripts(script: ScriptGetIn = Body(...)) -> ScriptGetOut:
    """查询脚本"""
    try:
        index, data = await Config.get_script(script.scriptId)
    except Exception as e:
        return ScriptGetOut(code=500, status="error", message=str(e), index=[], data={})
    return ScriptGetOut(index=index, data=data)


# @app.post("/api/update/scripts/{scriptId}", summary="更新脚本")
# async def update_script(
#     scriptId: str = Path(..., description="脚本ID"),
#     update_data: ScriptUpdate = Body(...),
# ):
#     """
#     更新脚本
#     """
#     # 实现更新脚本的逻辑
#     return {"status": "success"}


@app.post(
    "/api/delete/scripts",
    summary="删除脚本",
    response_model=BaseOut,
    status_code=200,
)
async def delete_script(
    script: ScriptDeleteIn = Body(..., description="脚本ID")
) -> BaseOut:
    """删除脚本"""
    try:
        await Config.del_script(script.scriptId)
    except Exception as e:
        return BaseOut(code=500, status="error", message=str(e))
    return BaseOut()


@app.post("/api/scripts/{scriptId}/users", summary="为脚本添加用户")
async def add_script_user(
    scriptId: str = Path(..., description="脚本ID"), user: ScriptUser = Body(...)
):
    """
    为脚本添加用户
    """
    # 实现为脚本添加用户的逻辑
    return {"status": "success"}


@app.get("/api/scripts/{scriptId}/users", summary="查询脚本的所有下属用户")
async def get_script_users(scriptId: str = Path(..., description="脚本ID")):
    """
    查询脚本的所有下属用户
    """
    # 实现查询脚本的所有下属用户的逻辑
    return {"status": "success", "data": []}


@app.get("/api/scripts/{scriptId}/users/{userId}", summary="查询脚本下的单个下属用户")
async def get_script_user(
    scriptId: str = Path(..., description="脚本ID"),
    userId: str = Path(..., description="用户ID"),
):
    """
    查询脚本下的单个下属用户
    """
    # 实现查询脚本下的单个下属用户的逻辑
    return {"status": "success", "data": {}}


@app.put("/api/scripts/{scriptId}/users/{userId}", summary="更新脚本下属用户的关联信息")
async def update_script_user(
    scriptId: str = Path(..., description="脚本ID"),
    userId: str = Path(..., description="用户ID"),
    config: Dict[str, Any] = Body(...),
):
    """
    更新脚本下属用户的关联信息
    """
    # 实现更新脚本下属用户的关联信息的逻辑
    return {"status": "success"}


@app.delete("/api/scripts/{scriptId}/users/{userId}", summary="从脚本移除用户")
async def remove_script_user(
    scriptId: str = Path(..., description="脚本ID"),
    userId: str = Path(..., description="用户ID"),
):
    """
    从脚本移除用户
    """
    # 实现从脚本移除用户的逻辑
    return {"status": "success"}


@app.post("/api/add/plans", summary="创建计划")
async def add_plan(plan: PlanCreate = Body(...)):
    """
    创建计划
    {
        "name": "计划 1",
        "mode": "全局", // 或 "周计划"
        "details": {
            "周一": {
                "吃理智药": 0,
                "连战次数": "AUTO",
                "关卡选择": "当前/上次",
                "备选-1": "当前/上次",
                "备选-2": "当前/上次",
                "备选-3": "当前/上次",
                "剩余理智": "不使用"
            },
            // 其他天数...
        }
    }
    """
    # 实现创建计划的逻辑
    return {"status": "success", "planId": "new_plan_id"}


@app.post("/api/get/plans", summary="查询所有计划")
async def get_plans():
    """
    查询所有计划
    """
    # 实现查询所有计划的逻辑
    return {"status": "success", "data": []}


@app.post("/api/get/plans/{planId}", summary="查询单个计划")
async def get_plan(planId: str = Path(..., description="计划ID")):
    """
    查询单个计划
    """
    # 实现查询单个计划的逻辑
    return {"status": "success", "data": {}}


@app.post("/api/update/plans/{planId}", summary="更新计划")
async def update_plan(
    planId: str = Path(..., description="计划ID"), update_data: PlanUpdate = Body(...)
):
    """
    更新计划
    """
    # 实现更新计划的逻辑
    return {"status": "success"}


@app.post("/api/delete/plans/{planId}", summary="删除计划")
async def delete_plan(planId: str = Path(..., description="计划ID")):
    """
    删除计划
    """
    # 实现删除计划的逻辑
    return {"status": "success"}


@app.post("/api/update/plans/{planId}/mode", summary="切换计划模式")
async def update_plan_mode(
    planId: str = Path(..., description="计划ID"), mode_data: PlanModeUpdate = Body(...)
):
    """
    切换计划模式
    {
        "mode": "周计划"
    }
    """
    # 实现切换计划模式的逻辑
    return {"status": "success"}


@app.post("/api/add/queues", summary="创建调度队列")
async def add_queue(queue: QueueCreate = Body(...)):
    """
    创建调度队列
    """
    # 实现创建调度队列的逻辑
    return {"status": "success", "queueId": "new_queue_id"}


@app.post("/api/get/queues", summary="查询所有调度队列")
async def get_queues():
    """
    查询所有调度队列
    """
    # 实现查询所有调度队列的逻辑
    return {"status": "success", "data": []}


@app.post("/api/get/queues/{queueId}", summary="查询单个调度队列详情")
async def get_queue(queueId: str = Path(..., description="调度队列ID")):
    """
    查询单个调度队列详情
    """
    # 实现查询单个调度队列详情的逻辑
    return {"status": "success", "data": {}}


@app.post("/api/update/queues/{queueId}", summary="更新调度队列")
async def update_queue(
    queueId: str = Path(..., description="调度队列ID"),
    update_data: QueueUpdate = Body(...),
):
    """
    更新调度队列
    """
    # 实现更新调度队列的逻辑
    return {"status": "success"}


@app.post("/api/delete/queues/{queueId}", summary="删除调度队列")
async def delete_queue(queueId: str = Path(..., description="调度队列ID")):
    """
    删除调度队列
    """
    # 实现删除调度队列的逻辑
    return {"status": "success"}


@app.post("/api/add/tasks", summary="添加任务")
async def add_task(task: TaskCreate = Body(...)):
    """
    添加任务
    """
    # 实现添加任务的逻辑
    return {"status": "success", "taskId": "new_task_id"}


@app.post("/api/tasks/{taskId}/start", summary="开始任务")
async def start_task(taskId: str = Path(..., description="任务ID")):
    """
    开始任务
    """
    # 实现开始任务的逻辑
    return {"status": "success"}


@app.post("/api/get/history", summary="查询历史记录")
async def get_history():
    """
    查询历史记录
    """
    # 实现查询历史记录的逻辑
    return {"status": "success", "data": []}


@app.post("/api/update/settings", summary="更新部分设置")
async def update_settings(settings: SettingsUpdate = Body(...)):
    """
    更新部分设置
    """
    # 实现更新部分设置的逻辑
    return {"status": "success"}


# ======================
# Error Handlers
# ======================


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return {"status": "error", "code": exc.status_code, "message": exc.detail}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
