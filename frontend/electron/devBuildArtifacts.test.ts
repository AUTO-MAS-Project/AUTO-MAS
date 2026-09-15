import { mkdtempSync, mkdirSync, rmSync, utimesSync, writeFileSync } from 'fs'
import { tmpdir } from 'os'
import * as path from 'path'

import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { inspectDevBuildArtifacts } from './devBuildArtifacts'

/** 构造一个含 dist/index.html 与 src/ 的假应用根 */
const makeAppRoot = (): string => {
  const root = mkdtempSync(path.join(tmpdir(), 'mas-dev-artifacts-'))
  mkdirSync(path.join(root, 'dist'))
  mkdirSync(path.join(root, 'src'))
  writeFileSync(path.join(root, 'dist', 'index.html'), '<html></html>')
  writeFileSync(path.join(root, 'src', 'main.ts'), 'export {}\n')
  return root
}

/** 把指定路径的 mtime 设为给定秒级时间戳 */
const setMtime = (target: string, seconds: number): void => {
  const when = new Date(seconds * 1000)
  utimesSync(target, when, when)
}

describe('inspectDevBuildArtifacts', () => {
  let root: string

  beforeEach(() => {
    root = makeAppRoot()
  })

  afterEach(() => {
    rmSync(root, { recursive: true, force: true })
  })

  it('产物比源码新时判定可用', () => {
    setMtime(path.join(root, 'src', 'main.ts'), 1_000)
    setMtime(path.join(root, 'dist', 'index.html'), 2_000)

    expect(inspectDevBuildArtifacts(root)).toBeNull()
  })

  it('源码比产物新时报陈旧并给出最新源码路径', () => {
    setMtime(path.join(root, 'dist', 'index.html'), 1_000)
    const sourceFile = path.join(root, 'src', 'main.ts')
    setMtime(sourceFile, 2_000)

    const issue = inspectDevBuildArtifacts(root)

    expect(issue).not.toBeNull()
    expect(issue?.reason).toContain('dist 产物早于前端源码')
    expect(issue?.hint).toContain(sourceFile)
  })

  it('缺少 dist/index.html 时报告缺失而不是静默通过', () => {
    rmSync(path.join(root, 'dist', 'index.html'))

    const issue = inspectDevBuildArtifacts(root)

    expect(issue?.reason).toContain('未找到')
  })

  it('递归比较子目录里的源码文件', () => {
    const nested = path.join(root, 'src', 'views', 'home')
    mkdirSync(nested, { recursive: true })
    const nestedFile = path.join(nested, 'Home.vue')
    writeFileSync(nestedFile, '<template />')

    setMtime(path.join(root, 'src', 'main.ts'), 1_000)
    setMtime(path.join(root, 'dist', 'index.html'), 2_000)
    setMtime(nestedFile, 3_000)

    const issue = inspectDevBuildArtifacts(root)

    expect(issue?.hint).toContain(nestedFile)
  })

  it('缺少 src/ 时不误报（打包分发场景）', () => {
    rmSync(path.join(root, 'src'), { recursive: true, force: true })

    expect(inspectDevBuildArtifacts(root)).toBeNull()
  })
})
