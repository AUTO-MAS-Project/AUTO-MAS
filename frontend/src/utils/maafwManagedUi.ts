/**
 * The detached/Managed MaaFW resource manager is kept in the source tree while
 * its UI is being redesigned.  Keep this switch deliberately static so a
 * runtime environment variable cannot expose an unfinished destructive flow.
 */
export const MAAFW_MANAGED_UI_ENABLED = false

export const MAAFW_MANAGED_UI_DISABLED_REASON =
  'MaaFW 脱壳项目资源管理正在重构，当前暂未开放；普通项目配置与运行不受影响。'
