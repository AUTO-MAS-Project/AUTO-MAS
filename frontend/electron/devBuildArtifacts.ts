import * as fs from 'fs'
import * as path from 'path'

export type DevBuildArtifactIssue = {
  /** 面向开发者的简短原因 */
  reason: string
  /** 建议的修复动作 */
  hint: string
}

/**
 * 源码环境（非打包）下，没有 dev server 时前端只能读 dist/。
 * dist 缺失或比 src/ 旧，都会让开发者误以为自己跑的是当前源码。
 *
 * 返回 null 表示产物可用；否则返回需要显式报错退出的原因。
 */
export function inspectDevBuildArtifacts(appRoot: string): DevBuildArtifactIssue | null {
  const indexHtmlPath = path.join(appRoot, 'dist', 'index.html')
  if (!fs.existsSync(indexHtmlPath)) {
    return {
      reason: `未找到 ${indexHtmlPath}`,
      hint: '请先构建前端（yarn build / vite build），或用 yarn dev 同时启动 vite 开发服务器。',
    }
  }

  const newest = findNewestSourceFile(path.join(appRoot, 'src'))
  if (!newest) return null

  const artifactMtime = fs.statSync(indexHtmlPath).mtimeMs
  if (newest.mtimeMs <= artifactMtime) return null

  return {
    reason: `dist 产物早于前端源码（产物 ${new Date(artifactMtime).toLocaleString()}，源码 ${new Date(
      newest.mtimeMs
    ).toLocaleString()}）`,
    hint: `最新源码：${newest.path}\n请重新构建前端，或用 yarn dev 启动 vite 开发服务器。`,
  }
}

/** 递归找出 src/ 下修改时间最新的文件；目录不存在时返回 null */
export function findNewestSourceFile(
  sourceDir: string
): { path: string; mtimeMs: number } | null {
  if (!fs.existsSync(sourceDir)) return null

  let newest: { path: string; mtimeMs: number } | null = null
  const walk = (dir: string): void => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const fullPath = path.join(dir, entry.name)
      if (entry.isDirectory()) {
        walk(fullPath)
        continue
      }
      const mtimeMs = fs.statSync(fullPath).mtimeMs
      if (!newest || mtimeMs > newest.mtimeMs) {
        newest = { path: fullPath, mtimeMs }
      }
    }
  }
  walk(sourceDir)
  return newest
}
