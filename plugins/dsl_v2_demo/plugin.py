from .schema import Config


def setup(ctx):
    config = Config.from_storage(ctx.config or {})
    ctx.logger.info(
        f"[dsl_v2_demo] 已启动: title={config.title}, retry={config.retry}, paths={len(config.watch_paths)}"
    )

    def dispose():
        ctx.logger.info("[dsl_v2_demo] 已关闭")

    return dispose
