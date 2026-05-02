# WebSocket 管理器快速上手

这份文档面向二次开发者，目标是用最少代码通过 `ws_client_manager` 创建并管理：

- 正向连接（后端主动连外部 WS 服务）
- 反向连接（外部客户端连入后端 WS 路由）

管理器入口位于：`app.utils.websocket.ws_client_manager`

---

## 1. 正向连接：openws

适用场景：你知道目标服务器地址，需要后端主动发起连接。

```python
from app.utils.websocket import ws_client_manager

async def open_outbound_ws():
    client = await ws_client_manager.openws(
        name="MyOutbound",                 # 客户端唯一名称
        url="ws://127.0.0.1:5140/ws",     # 目标 WS 地址
        ping_interval=15.0,
        ping_timeout=30.0,
        reconnect_interval=5.0,
        max_reconnect_attempts=-1,          # -1 表示无限重连
    )

    # 可选：发送认证
    await ws_client_manager.send_auth(
        name="MyOutbound",
        token="your-token",
        auth_type="auth",
    )

    # 可选：发送业务消息
    await ws_client_manager.send_message(
        "MyOutbound",
        {"id": "Client", "type": "command", "data": {"hello": "world"}},
    )

    return client
```

---

## 2. 反向连接：openwsr

### 声明式动态反向通道（推荐）

现在后端提供统一动态入口：`/api/ws/{channel_name}`。

你只需要先声明通道，客户端连接到对应路径后，路由会自动调用 `openwsr` 接管：

```python
from app.utils.websocket import ws_client_manager

# 启动阶段执行一次
ws_client_manager.register_reverse_channel(
    name="123123",
    ping_interval=15.0,
    ping_timeout=30.0,
    auth_token="optional-token",
)
```

然后让外部客户端连接：

- `ws://<host>:<port>/api/ws/123123`

注意：

- 只有已声明通道会被放行；未声明会被拒绝。
- `wsdev` 也已改为同样的声明式写法，入口为 `/api/ws/wsdev`。

如果你需要在业务代码里拿到该通道对应的会话实例，可直接等待：

```python
session = await ws_client_manager.wait_for_reverse_session("123123", timeout=10)

# session 可直接发送消息
await session.send_json({"id": "Client", "type": "command", "data": {"ok": True}})
```

---

## 3. 常用管理操作

```python
# 是否存在
ws_client_manager.has_client("MyOutbound")

# 读取统一会话对象（正向/反向都可）
session = ws_client_manager.get_session("MyOutbound")

# 列出所有连接状态
clients = ws_client_manager.list_clients()

# 断开连接
await ws_client_manager.disconnect_client("MyOutbound")

# 删除客户端（系统客户端不可删除）
await ws_client_manager.remove_client("MyOutbound")
```

---

## 3.1 WS 管理器方法总览

以下为 `WSClientManager` 当前公共方法，按功能分组：

- 反向通道声明：
- `register_reverse_channel(name, ping_interval=15.0, ping_timeout=30.0, auth_token=None, on_message=None, on_connect=None, on_disconnect=None, overwrite=True)`
- `unregister_reverse_channel(name)`
- `is_reverse_channel_registered(name)`
- `get_reverse_channel_config(name)`
- `list_reverse_channels()`
- 会话等待与查询：
- `wait_for_reverse_session(name, timeout=None)`
- `get_client(name)`
- `get_session(name)`
- `has_client(name)`
- `is_system_client(name)`
- `list_clients()`
- 正向/反向连接控制：
- `create_client(name, url, ping_interval=15.0, ping_timeout=30.0, reconnect_interval=5.0, max_reconnect_attempts=-1)`
- `openws(name, url, ping_interval=15.0, ping_timeout=30.0, reconnect_interval=5.0, max_reconnect_attempts=-1)`
- `openwsr(name, websocket, ping_interval=15.0, ping_timeout=30.0, auth_token=None, on_message=None, on_connect=None, on_disconnect=None)`
- `connect_client(name)`
- `disconnect_client(name)`
- `remove_client(name)`
- 消息相关：
- `send_message(name, message)`
- `send_auth(name, token, auth_type="auth", extra_data=None)`
- `get_message_history(name=None)`
- `clear_message_history(name=None)`
- 调试连接维护：
- `add_debug_connection(ws)`
- `remove_debug_connection(ws)`
- 其他工具：
- `http_to_ws_url(http_url)`
- `init_system_client_koishi()`
- `update_system_client_koishi()`

---

## 4. 最佳实践

- `name` 保持全局唯一，建议使用业务前缀（如 `Order-WS`、`Notify-WS`）。
- 尽量通过 `ws_client_manager.send_message/send_auth` 统一发送，便于历史记录与调试页联动。
- 反向路由中优先使用 `session.wait_closed()`，避免函数提前返回导致生命周期不一致。
- 系统保留名称（如 `Main`、`Koishi`）不要用于普通业务连接。

---

## 5. 与现有代码对照

你可以直接参考这两个实现：

- 主反向连接入口：`app/api/core.py` 中 `/api/core/ws`
- 管理器实现：`app/utils/websocket.py` 中 `WSClientManager.openws/openwsr`
