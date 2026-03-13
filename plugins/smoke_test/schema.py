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
