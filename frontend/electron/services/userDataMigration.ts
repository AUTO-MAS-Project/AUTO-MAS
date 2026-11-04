import * as fs from 'fs'
import * as path from 'path'

const MARKER_NAME = '.auto-mas-user-data'

/** 首次选择的单实例锁路径写入标记，避免后续启动因旧目录变化换锁。 */
export function selectUserDataLock(legacyPath: string, targetPath: string): string {
  const marker = path.join(targetPath, MARKER_NAME)
  if (fs.existsSync(marker)) {
    const kind = fs.readFileSync(marker, 'utf8').trim()
    return kind === 'legacy' ? legacyPath : targetPath
  }
  return fs.existsSync(legacyPath) ? legacyPath : targetPath
}

/** 完整复制旧资料；目标目录就绪后才切换，失败时继续使用旧资料。 */
export function migrateUserData(
  legacyPath: string,
  target: string,
  lockPath: string
): {
  path: string
  error?: string
} {
  const marker = path.join(target, MARKER_NAME)
  let staging: string | undefined

  try {
    if (fs.existsSync(marker)) return { path: target }
    if (fs.existsSync(target)) {
      const entries = fs.readdirSync(target)
      // Electron 为当前锁创建的目录可能只有 lockfile；其余已有内容绝不覆盖。
      if (lockPath !== target || entries.some(name => name !== 'lockfile'))
        throw new Error('新用户数据目录已有其他数据')
      fs.writeFileSync(marker, 'current\n', { flag: 'wx' })
      return { path: target }
    }

    staging = fs.mkdtempSync(path.join(path.dirname(target), '.auto-mas-user-data-'))
    // 使用逐项复制：Electron 内置 Node 的目录快速复制在 Windows 上可能拒绝已有目标目录。
    if (fs.existsSync(legacyPath))
      fs.cpSync(legacyPath, staging, { recursive: true, filter: () => true })
    fs.writeFileSync(
      path.join(staging, MARKER_NAME),
      lockPath === legacyPath ? 'legacy\n' : 'current\n',
      { flag: 'wx' }
    )
    fs.renameSync(staging, target)
    return { path: target }
  } catch (error) {
    if (staging) {
      try {
        fs.rmSync(staging, { recursive: true, force: true })
      } catch {
        // 不让临时目录清理失败影响旧目录的使用。
      }
    }
    return { path: legacyPath, error: error instanceof Error ? error.message : String(error) }
  }
}
