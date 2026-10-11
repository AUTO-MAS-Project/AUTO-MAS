import assert from 'node:assert/strict'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { test } from 'node:test'
import { acquireRealRunLock } from './run.mjs'

test('真实入口拒绝并发运行', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'auto-mas-e2e-lock-'))
  const lockPath = path.join(root, 'real.lock')
  try {
    const release = await acquireRealRunLock(lockPath)
    await assert.rejects(acquireRealRunLock(lockPath), /已有本机真实 E2E/)
    await release()
    const releaseAfterCleanup = await acquireRealRunLock(lockPath)
    await releaseAfterCleanup()
  } finally {
    assert.equal(path.dirname(root), path.resolve(tmpdir()))
    await rm(root, { recursive: true, force: true })
  }
})
