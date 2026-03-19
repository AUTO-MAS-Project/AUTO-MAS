from app.core.plugins.dsl import Schema


schema = Schema.object(
    {
        "enable": Schema.boolean()
        .default(True)
        .required(True)
        .description("是否启用 smoke_test 插件"),
        
        "message": Schema.string()
        .default("Hello AUTO-MAS")
        .required(False)
        .description("插件启动时使用的示例消息"),

        "runtime_check_on_start": Schema.boolean()
        .default(True)
        .required(False)
        .description("启动时检查并记录运行时解释器信息"),

        "run_runtime_probe": Schema.boolean()
        .default(True)
        .required(False)
        .description("启动时执行 runtime Python 探针"),

        "runtime_probe_code": Schema.string()
        .default("import sys,platform; print(sys.executable); print(platform.platform())")
        .required(False)
        .description("runtime 探针代码（由 runtime 执行）"),

        "python_executable": Schema.string()
        .default("")
        .required(False)
        .description("可选：指定探针使用的解释器路径，留空则走策略默认"),

        "python_timeout_seconds": Schema.number()
        .default(15)
        .required(False)
        .description("runtime 探针超时时间（秒）"),

        "include_payload": Schema.boolean()
        .default(True)
        .required(False)
        .description("事件日志中是否包含 payload"),

        "include_runtime_in_event_log": Schema.boolean()
        .default(False)
        .required(False)
        .description("事件日志中是否附加 runtime 信息"),

        "log_probe_stdout": Schema.boolean()
        .default(True)
        .required(False)
        .description("是否打印 runtime 探针标准输出"),

        "api_token": Schema.password()
        .default("")
        .required(False)
        .description("敏感令牌，前端默认隐藏显示"),

        "retry_count": Schema.number()
        .default(3)
        .required(False)
        .description("重试次数"),

        "channels": Schema.list("string")
        .default(["console"])
        .required(False)
        .description("通知渠道列表"),

        "meta": Schema.key_value()
        .default({})
        .required(False)
        .description("键值对扩展配置"),
        
        "table_data": Schema.table()
        .default([])
        .required(False)
        .description("可扩展表格数据，支持不限行列"),
    }
)
