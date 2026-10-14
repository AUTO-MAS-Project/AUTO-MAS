# 暂缓专项前端

这里保留依赖旧专项配置与接口的页面、组件、类型及对应测试。当前活动路由、
构建与 `yarn typecheck` 不引用这些模块；活动页面仍由完整的 `src/` 检查覆盖。

本轮包括旧模拟器页面、旧脚本编辑器及其专项依赖、旧计划表，以及旧专项问题包入口。
通用配置来源组件已移至 `src/components/GeneralConfigModeSelector.vue`，仍供活动托管页使用。

- 活动验证：`yarn typecheck`、`yarn test --run`、`yarn vite build`。
- 延后专项诊断：`yarn typecheck:deferred`、`yarn test:deferred`。
- 延后入口当前仍需要对应专项的新后端契约，不能把其失败算作活动迁移通过。
- 专项恢复时先迁移后端，再通过生成器更新客户端，修正这里的契约，最后移回活动入口。

`@deferred/` 指向本目录的 `src/`；`@/` 指向活动代码的 `src/`。
源码保持用于后续专项迁移，不提供旧 API 的虚假兼容实现。
