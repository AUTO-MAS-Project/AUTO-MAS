import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import { afterEach, beforeEach, describe, expect, it } from 'vite-plus/test'

import { migrateUserData, selectUserDataLock } from './userDataMigration'

let root: string
let legacy: string
let target: string

beforeEach(() => {
  root = fs.mkdtempSync(path.join(os.tmpdir(), 'mas-user-data-test-'))
  legacy = path.join(root, 'frontend')
  target = path.join(root, 'AUTO-MAS')
})

afterEach(() => fs.rmSync(root, { recursive: true, force: true }))

describe('用户数据目录迁移', () => {
  it('保留旧目录并迁移资源、来源记录和浏览器数据', () => {
    fs.mkdirSync(path.join(legacy, 'appearances', 'theme'), { recursive: true })
    fs.mkdirSync(path.join(legacy, 'Local Storage'))
    fs.writeFileSync(path.join(legacy, 'appearances', 'theme', 'theme.json'), 'theme')
    fs.writeFileSync(path.join(legacy, 'appearance-sources.json'), 'sources')
    fs.writeFileSync(path.join(legacy, 'Local Storage', 'state'), 'storage')

    expect(migrateUserData(legacy, target, legacy)).toEqual({ path: target })
    expect(fs.readFileSync(path.join(target, 'appearances', 'theme', 'theme.json'), 'utf8')).toBe(
      'theme'
    )
    expect(fs.readFileSync(path.join(target, 'appearance-sources.json'), 'utf8')).toBe('sources')
    expect(fs.readFileSync(path.join(target, 'Local Storage', 'state'), 'utf8')).toBe('storage')
    expect(fs.readFileSync(path.join(legacy, 'appearance-sources.json'), 'utf8')).toBe('sources')

    fs.writeFileSync(path.join(target, 'appearance-sources.json'), 'updated')
    expect(migrateUserData(legacy, target, legacy)).toEqual({ path: target })
    expect(fs.readFileSync(path.join(target, 'appearance-sources.json'), 'utf8')).toBe('updated')
  })

  it('全新安装时创建新目录', () => {
    expect(migrateUserData(legacy, target, target)).toEqual({ path: target })
    expect(fs.existsSync(path.join(target, '.auto-mas-user-data'))).toBe(true)
  })

  it('新目录被其他数据占用时保留两边并回退旧目录', () => {
    fs.mkdirSync(legacy)
    fs.mkdirSync(target)
    fs.writeFileSync(path.join(target, 'other'), 'existing')
    expect(migrateUserData(legacy, target, legacy)).toMatchObject({
      path: legacy,
      error: expect.any(String),
    })
    expect(fs.readFileSync(path.join(target, 'other'), 'utf8')).toBe('existing')
  })

  it('复制失败时不留下已完成的目标目录，下次可以重试', () => {
    fs.writeFileSync(legacy, 'not a directory')
    expect(migrateUserData(legacy, target, legacy)).toMatchObject({
      path: legacy,
      error: expect.any(String),
    })
    expect(fs.existsSync(target)).toBe(false)
    expect(fs.readdirSync(root)).toEqual(['frontend'])
    fs.rmSync(legacy)
    fs.mkdirSync(legacy)
    expect(migrateUserData(legacy, target, legacy)).toEqual({ path: target })
  })

  it('开发版迁移资源和 Runtime 到独立目录，不覆盖正式版', () => {
    const developmentLegacy = path.join(root, 'frontend-dev')
    const developmentTarget = path.join(root, 'AUTO-MAS-dev')
    fs.mkdirSync(path.join(developmentLegacy, 'auto-mas-runtime'), { recursive: true })
    fs.mkdirSync(path.join(developmentLegacy, 'mascots', 'demo'), { recursive: true })
    fs.writeFileSync(path.join(developmentLegacy, 'auto-mas-runtime', 'state'), 'runtime')
    fs.writeFileSync(path.join(developmentLegacy, 'mascots', 'demo', 'mascot.json'), 'mascot')
    expect(migrateUserData(legacy, target, legacy)).toEqual({ path: target })

    expect(migrateUserData(developmentLegacy, developmentTarget, developmentLegacy)).toEqual({
      path: developmentTarget,
    })
    expect(fs.readFileSync(path.join(developmentTarget, 'auto-mas-runtime', 'state'), 'utf8')).toBe(
      'runtime'
    )
    expect(
      fs.readFileSync(path.join(developmentTarget, 'mascots', 'demo', 'mascot.json'), 'utf8')
    ).toBe('mascot')
    expect(fs.existsSync(path.join(developmentLegacy, 'auto-mas-runtime', 'state'))).toBe(true)
    expect(migrateUserData(legacy, target, legacy)).toEqual({ path: target })
    expect(migrateUserData(developmentLegacy, developmentTarget, developmentLegacy)).toEqual({
      path: developmentTarget,
    })
  })

  it('新装开发版使用新锁，不创建旧目录；锁路径随后保持不变', () => {
    const developmentLegacy = path.join(root, 'frontend-dev')
    const developmentTarget = path.join(root, 'AUTO-MAS-dev')
    expect(selectUserDataLock(developmentLegacy, developmentTarget)).toBe(developmentTarget)
    fs.mkdirSync(developmentTarget)
    fs.writeFileSync(path.join(developmentTarget, 'lockfile'), '')
    expect(migrateUserData(developmentLegacy, developmentTarget, developmentTarget)).toEqual({
      path: developmentTarget,
    })
    expect(fs.existsSync(developmentLegacy)).toBe(false)
    fs.mkdirSync(developmentLegacy)
    expect(selectUserDataLock(developmentLegacy, developmentTarget)).toBe(developmentTarget)
  })
})
