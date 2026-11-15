from maa_adapter.updates.credentials import (
    resolve_takeover_credentials,
    use_maa_github_update,
)

"""L2 只读预下载需求，取自当前统一下载接线。"""


async def check_prefetch(config) -> list:
    """根据托管更新开关、来源和凭据检查本体与资源更新，返回本次需要预下载的请求列表。"""
    from maa_adapter.updates.fluxdown import check_update_download
    from maa_adapter.updates.resources.service import check_resource_download
    from maa_adapter.updates.software.service import check_software_download

    root = config.Info.Path
    if not config.Update.TakeoverEnabled or root is None:
        return []
    github = use_maa_github_update(config, config_dirs=[root / "config"])
    enabled, cdk = resolve_takeover_credentials(config)
    requests = (
        await check_update_download(root, config)
        if github
        else await check_software_download(root, config)
    )
    if github or enabled and cdk is not None:
        requests.extend(
            await check_resource_download(
                root,
                github=github,
                cdk=cdk,
                incremental=config.Update.PackageMode == "incremental",
            )
        )
    return requests
