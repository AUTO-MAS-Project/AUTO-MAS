from app.core.plugins.dsl import Schema


schema = Schema.object(
    {
        "enable": Schema.boolean()
        .default(True)
        .required(True)
        .description("是否启用 SMTP 通知插件"),

        "smtp_host": Schema.string()
        .default("smtp.example.com")
        .required(True)
        .description("SMTP 服务器地址"),

        "smtp_port": Schema.number()
        .default(587)
        .required(True)
        .description("SMTP 服务器端口"),

        "smtp_username": Schema.string()
        .default("")
        .required(False)
        .description("SMTP 用户名（可选）"),

        "smtp_password": Schema.password()
        .default("")
        .required(False)
        .description("SMTP 密码（前端隐藏显示）"),

        "smtp_use_ssl": Schema.boolean()
        .default(False)
        .required(False)
        .description("是否使用 SSL 连接（一般端口 465）"),

        "smtp_use_starttls": Schema.boolean()
        .default(True)
        .required(False)
        .description("是否使用 STARTTLS（一般端口 587）"),

        "sender_email": Schema.string()
        .default("")
        .required(False)
        .description("发件邮箱地址（留空时使用 smtp_username）"),

        "target_email": Schema.string()
        .default("receiver@example.com")
        .required(True)
        .description("目标邮箱地址"),

        "subject": Schema.string()
        .default("AUTO-MAS 通知")
        .required(False)
        .description("邮件主题"),

        "message": Schema.string()
        .default("任务状态已更新")
        .required(False)
        .description("邮件正文"),

        "events": Schema.list("string")
        .default(["script.success"])
        .required(False)
        .description("监听事件列表（如 script.success/script.error）"),

        "include_payload": Schema.boolean()
        .default(True)
        .required(False)
        .description("是否在邮件中附加事件 payload"),

        "timeout_seconds": Schema.number()
        .default(15)
        .required(False)
        .description("SMTP 连接超时时间（秒）"),
    }
)
