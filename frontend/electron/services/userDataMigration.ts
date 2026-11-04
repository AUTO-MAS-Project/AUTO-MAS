import * as fs from 'fs'
import * as path from 'path'

const MARKER_NAME = '.auto-mas-user-data'
const REGENERABLE_DIRECTORIES = new Set([
  'Cache',
  'Code Cache',
  'GPUCache',
  'DawnGraphiteCache',
  'DawnWebGPUCache',
])

/** 首次选择的单实例锁路径写入标记，避免后续启动因旧目录变化换锁。 */
export function selectUserDataLock(legacyPath: string, targetPath: string): string {
  const marker = path.join(targetPath, MARKER_NAME)
  if (fs.existsSync(marker)) {
    const kind = fs.readFileSync(marker, 'utf8').trim()
    if (kind !== 'legacy' && kind !== 'current') throw new Error('用户数据目录标记无效')
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
      if (lockPath === target) {
        // 当前实例在 Windows 上可能只创建 lockfile；其余已有内容绝不覆盖。
        if (entries.some(name => name !== 'lockfile')) throw new Error('新用户数据目录已有其他数据')
        fs.writeFileSync(marker, 'current\n', { flag: 'wx' })
        return { path: target }
      }
      // Electron 查询默认 userData 时可能先创建空目录，旧锁持有期间可以移除它。
      if (entries.length) throw new Error('新用户数据目录已有其他数据')
      fs.rmdirSync(target)
    }

    staging = fs.mkdtempSync(path.join(path.dirname(target), '.auto-mas-user-data-'))
    // 使用逐项复制：Electron 内置 Node 的目录快速复制在 Windows 上可能拒绝已有目标目录。
    if (fs.existsSync(legacyPath))
      fs.cpSync(legacyPath, staging, {
        recursive: true,
        filter: source => {
          const relative = path.relative(legacyPath, source)
          const first = relative.split(path.sep)[0]
          return relative === '' || (first !== 'lockfile' && !REGENERABLE_DIRECTORIES.has(first))
        },
      })
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
    return { path: lockPath, error: error instanceof Error ? error.message : String(error) }
  }
}
