from fastapi.routing import APIRoute

from app.api.scripts import router

_EXPECTED_ROUTES = (
    "GET /api/scripts/backup/file",
    "GET /api/scripts/backup/list",
    "GET /api/scripts/backup/preview",
    "GET /api/scripts/bettergi/auto-pathing-tree",
    "GET /api/scripts/bettergi/dirs",
    "GET /api/scripts/bettergi/domain-catalog",
    "GET /api/scripts/bettergi/global-domain/settings",
    "GET /api/scripts/bettergi/global-stygian/settings",
    "GET /api/scripts/bettergi/js-scripts",
    "GET /api/scripts/bettergi/key-mouse-scripts",
    "GET /api/scripts/bettergi/one-dragon/configs",
    "GET /api/scripts/bettergi/one-dragon/custom-groups",
    "GET /api/scripts/bettergi/one-dragon/settings",
    "GET /api/scripts/bettergi/script-group/detail",
    "GET /api/scripts/bettergi/script-groups",
    "GET /api/scripts/bettergi/script-readme",
    "GET /api/scripts/bettergi/script-settings-ui",
    "GET /api/scripts/bettergi/strategies",
    "GET /api/scripts/hsr/capabilities",
    "GET /api/scripts/hsr/managed-config",
    "GET /api/scripts/hsr/sra-profiles",
    "GET /api/scripts/hsr/stage-options",
    "GET /api/scripts/maafw/asset",
    "GET /api/scripts/zzzod/app-config",
    "GET /api/scripts/zzzod/catalog",
    "GET /api/scripts/zzzod/instances",
    "GET /api/scripts/zzzod/launchers",
    "GET /api/scripts/zzzod/native-config",
    "GET /api/scripts/zzzod/options",
    "GET /api/scripts/zzzod/teams",
    "POST /api/scripts/Upload/web",
    "POST /api/scripts/add",
    "POST /api/scripts/backup/ensure",
    "POST /api/scripts/backup/restore",
    "POST /api/scripts/bettergi/global-domain/settings",
    "POST /api/scripts/bettergi/global-stygian/settings",
    "POST /api/scripts/bettergi/one-dragon/plan/step-enabled",
    "POST /api/scripts/bettergi/one-dragon/settings",
    "POST /api/scripts/bettergi/script-group/save",
    "POST /api/scripts/config/import",
    "POST /api/scripts/delete",
    "POST /api/scripts/get",
    "POST /api/scripts/hsr/direct-config/clear",
    "POST /api/scripts/hsr/direct-config/import",
    "POST /api/scripts/hsr/update",
    "POST /api/scripts/import/web",
    "POST /api/scripts/m9a/tasks/available",
    "POST /api/scripts/maa/cultivate/operators",
    "POST /api/scripts/maa/cultivate/preview",
    "POST /api/scripts/maa/cultivate/skland/bindings",
    "POST /api/scripts/maa/depot/inventory",
    "POST /api/scripts/maa/depot/items",
    "POST /api/scripts/maa/depot/stage/candidates",
    "POST /api/scripts/maaend/options",
    "POST /api/scripts/maafw/agent-env/prepare",
    "POST /api/scripts/maafw/preview",
    "POST /api/scripts/maafw/update",
    "POST /api/scripts/oknte/configs/batch-update",
    "POST /api/scripts/oknte/configs/list",
    "POST /api/scripts/order",
    "POST /api/scripts/update",
    "POST /api/scripts/user/add",
    "POST /api/scripts/user/combox/infrastructure",
    "POST /api/scripts/user/delete",
    "POST /api/scripts/user/get",
    "POST /api/scripts/user/infrastructure",
    "POST /api/scripts/user/infrastructure/plan-select",
    "POST /api/scripts/user/infrastructure/plan-select/get",
    "POST /api/scripts/user/order",
    "POST /api/scripts/user/update",
    "POST /api/scripts/webhook/add",
    "POST /api/scripts/webhook/delete",
    "POST /api/scripts/webhook/get",
    "POST /api/scripts/webhook/update",
    "POST /api/scripts/zzzod/app-config/save",
    "POST /api/scripts/zzzod/import",
    "POST /api/scripts/zzzod/instances/active-in-od",
    "POST /api/scripts/zzzod/instances/add",
    "POST /api/scripts/zzzod/instances/delete",
    "POST /api/scripts/zzzod/instances/force-login",
    "POST /api/scripts/zzzod/instances/rename",
    "POST /api/scripts/zzzod/instances/run-mode",
    "POST /api/scripts/zzzod/instances/set-active",
    "POST /api/scripts/zzzod/native-config/save",
    "POST /api/scripts/zzzod/teams/save",
)


def test_scripts_route_inventory_snapshot() -> None:
    """路由清单快照：按域拆分 app/api/scripts.py 的机械护栏。

    拆分只改变代码归属，不得增删路径或方法；清单变化即等价性破坏，
    需在拆分 PR 中显式说明并同步本快照。
    """

    inventory = tuple(
        sorted(
            f"{','.join(sorted(route.methods))} {route.path}"
            for route in router.routes
            if isinstance(route, APIRoute)
        )
    )
    assert inventory == _EXPECTED_ROUTES
