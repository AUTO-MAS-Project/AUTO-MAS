from app.core.plugins.dsl import Schema


schema = Schema.object(
    {
        "enable": Schema.boolean()
        .default(True)
        .required(True)
        .description("是否启用 smoke_test 缓存测试插件"),

        "cache_name": Schema.string()
        .default("smoke_cache")
        .required(False)
        .description("缓存名称，同实例内唯一"),

        "limit_mode": Schema.string()
        .default("count")
        .required(False)
        .description("阈值模式：count（数量）或 bytes（容量）"),

        "limit": Schema.number()
        .default(8)
        .required(True)
        .description("缓存阈值，count 模式表示条目数，bytes 模式配合单位使用"),

        "limit_unit": Schema.string()
        .default("kb")
        .required(False)
        .description("容量单位：b/kb/mb/gb，仅 bytes 模式生效"),

        "clear_before_run": Schema.boolean()
        .default(True)
        .required(False)
        .description("启动时是否先清空该缓存"),

        "write_count": Schema.number()
        .default(20)
        .required(False)
        .description("测试写入条数"),

        "payload_size": Schema.number()
        .default(128)
        .required(False)
        .description("每条测试数据目标长度（字符）"),

        "key_prefix": Schema.string()
        .default("smoke_item")
        .required(False)
        .description("批量写入 key 前缀"),

        "listen_task_events": Schema.boolean()
        .default(True)
        .required(False)
        .description("是否监听 task 事件并写入计数器到缓存"),
    }
)
