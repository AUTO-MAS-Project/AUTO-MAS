import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, expect, it } from 'vite-plus/test'
import { migrateUserData, selectUserDataLock } from './userDataMigration'

const roots: string[] = []

afterEach(() => {
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true })
})

function createProfiles() {
  const root = mkdtempSync(join(tmpdir(), 'mas-profiles-'))
  roots.push(root)
  const legacy = join(root, 'frontend-dev')
  mkdirSync(legacy)
  writeFileSync(join(legacy, 'legacy-data'), '保留旧数据')
  return { root, legacy }
}

it('显式工作树各自取锁，不导入或回退到公共旧数据', () => {
  const { root, legacy } = createProfiles()
  const first = join(root, 'worktree-a')
  const second = join(root, 'worktree-b')
  mkdirSync(first)
  mkdirSync(second)
  // 旧测试版可能已经记录了公共锁；隔离模式不能继续使用它。
  writeFileSync(join(first, '.auto-mas-user-data'), 'legacy\n')
  writeFileSync(join(second, 'existing-data'), '另一个工作树的数据')

  expect(selectUserDataLock(undefined, first)).toBe(first)
  expect(selectUserDataLock(undefined, second)).toBe(second)
  expect(migrateUserData(undefined, first, first, 'win32')).toEqual({ path: first })
  expect(migrateUserData(undefined, second, second, 'win32')).toEqual({ path: second })
  expect(existsSync(join(first, 'legacy-data'))).toBe(false)
  expect(existsSync(join(second, 'legacy-data'))).toBe(false)
  expect(readFileSync(join(legacy, 'legacy-data'), 'utf8')).toBe('保留旧数据')
  expect(readFileSync(join(second, 'existing-data'), 'utf8')).toBe('另一个工作树的数据')
})

it('未显式隔离的正常启动仍可沿用旧锁迁移数据', () => {
  const { root, legacy } = createProfiles()
  const target = join(root, 'ordinary')
  mkdirSync(target)

  const lock = selectUserDataLock(legacy, target)
  expect(lock).toBe(legacy)
  expect(migrateUserData(legacy, target, lock, 'win32')).toEqual({ path: target })
  expect(readFileSync(join(target, 'legacy-data'), 'utf8')).toBe('保留旧数据')
  expect(selectUserDataLock(legacy, target)).toBe(legacy)
})
