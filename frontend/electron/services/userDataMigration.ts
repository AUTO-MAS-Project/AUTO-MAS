/**
 * 用户数据目录迁移 —— 把旧版本目录里的本地设置搬到新目录
 *
 * 旧版本用 package.json 的 name=frontend 当目录名（开发版是 frontend-dev），改名后
 * 首启一次性把渲染进程的 Local Storage 拷过去：主题、日志配色、首页布局等只存在这里，
 * 其余是 Chromium profile 与缓存，不迁。旧目录保留不删。
 *
 * 必须在 app ready 之前调用，且任何失败都不能阻断启动：此时 initializeLogger() 还没跑，
 * getLogger() 不可用，只能 console.warn。
 */

import * as fs from 'fs'
import * as path from 'path'

// 迁移完成后在新目录留下的标记，避免每次启动重复搬运
export const MIGRATION_MARKER_FILENAME = 'userdata-migrated.json'

// 只迁渲染进程的本地设置，不整份拷 Chromium 缓存
export const MIGRATED_DIR_NAMES = ['Local Storage'] as const

export interface MigrateLocalStorageOptions {
  legacyUserDataPath: string
  userDataPath: string
}

/**
 * 把旧 userData 目录里属于用户的本地设置搬到新目录
 *
 * @returns 是否真的执行了搬运（便于单测与排查）
 */
export function migrateLocalStorage(options: MigrateLocalStorageOptions): boolean {
  const { legacyUserDataPath, userDataPath } = options

  try {
    if (fs.existsSync(path.join(userDataPath, MIGRATION_MARKER_FILENAME))) {
      return false
    }
    if (!fs.existsSync(legacyUserDataPath)) {
      return false
    }

    const copied: string[] = []
    for (const dirName of MIGRATED_DIR_NAMES) {
      const from = path.join(legacyUserDataPath, dirName)
      const to = path.join(userDataPath, dirName)
      // 新目录已经有了就说明用户已经在新版本里用过，不覆盖
      if (!fs.existsSync(from) || fs.existsSync(to)) {
        continue
      }
      fs.cpSync(from, to, { recursive: true })
      copied.push(dirName)
    }
    if (copied.length === 0) {
      return false
    }

    fs.writeFileSync(
      path.join(userDataPath, MIGRATION_MARKER_FILENAME),
      JSON.stringify({ copied }, null, 2)
    )
    return true
  } catch (error) {
    console.warn(
      '[userDataMigration] 迁移本地设置失败，已跳过: ' +
        (error instanceof Error ? error.message : String(error))
    )
    return false
  }
}
