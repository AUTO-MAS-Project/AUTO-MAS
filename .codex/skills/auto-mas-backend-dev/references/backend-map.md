# 后端结构地图

## 入口与装配

- `main.py`：后端入口、管理员提权、FastAPI 应用创建、路由注册、静态资源挂载、MCP 挂载、生命周期启动与关闭。
- `app/api/__init__.py`：统一导出路由模块。新增路由模块时要同步更新。

## 主要模块分工

- `app/api/`：HTTP 与 WebSocket 接口层，负责传参与对外暴露。
- `app/models/schema.py`：API 使用的 Pydantic 请求与响应模型，优先复用现有 `OutBase` 风格。
- `app/models/config.py`：持久化配置模型定义。
- `app/core/config.py`：全局 `Config` 单例，负责启动初始化、数据迁移、路径、缓存、持久化、WebSocket 推送、历史与统计处理。
- `app/core/task_manager.py`：任务创建、生命周期、队列调度、清理与电源动作。
- `app/core/timer.py`：周期性后台调度。
- `app/core/broadcast.py`：WebSocket 消息广播。
- `app/services/`：通知、更新、遥测、系统操作等服务组件。
- `app/task/`：脚本类型运行时实现与工具集成，包含 `MAA`、`SRC`、`general`、`maaend` 等路径。
- `app/utils/`：日志、进程、安全、OCR、模拟器、WebSocket 等通用工具。

## 常见改动入口

### 新增接口

1. 在 `app/api/` 新增或修改路由文件。
2. 在 `app/models/schema.py` 中补模型。
3. 如有需要，在 `app/api/__init__.py` 导出路由。
4. 若是新模块，再在 `main.py` 注册。

### 新增配置字段

1. 在 `app/models/config.py` 补配置定义。
2. 如需对外暴露，在 `app/models/schema.py` 补 API 模型。
3. 在 `app/core/config.py` 追踪默认值、读写和广播逻辑。
4. 判断是否需要兼容旧 JSON 或数据库数据，并补迁移处理。

## 项目特征

- 这是强状态、强文件系统依赖的后端，不是纯 CRUD 服务。
- 涉及与数据文件交互的行为都挂在全局 `Config` 上。
- 项目明显偏 Windows 运行环境，并且会操作本地进程、模拟器和文件。
- WebSocket 更新是主流程的一部分，不是附属功能。