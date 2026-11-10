import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'

import { RUNTIME_EXE_ENV } from './runtime'
import { syncRuntimeBinary } from './runtimeBinaryService'

const probe = vi.hoisted(() => ({ run: vi.fn() }))
vi.mock('electron', () => ({ app: { isPackaged: false } }))
vi.mock('./runtime', async importOriginal => ({
  ...(await importOriginal<typeof import('./runtime')>()),
  createRuntimeClient: () => ({ run: probe.run }),
}))
vi.mock('./logger', () => ({
  getLogger: () => ({ info: vi.fn(), warn: vi.fn(), error: vi.fn(), debug: vi.fn() }),
}))

let workspace: string
let runtimePath: string
let previousRuntime: string | undefined

beforeEach(() => {
  workspace = fs.mkdtempSync(path.join(os.tmpdir(), 'mas-runtime-capabilities-'))
  runtimePath = path.join(workspace, 'auto-mas-runtime.exe')
  fs.writeFileSync(runtimePath, 'installed runtime')
  previousRuntime = process.env[RUNTIME_EXE_ENV]
  delete process.env[RUNTIME_EXE_ENV]
  probe.run.mockReset()
})

afterEach(() => {
  if (previousRuntime === undefined) delete process.env[RUNTIME_EXE_ENV]
  else process.env[RUNTIME_EXE_ENV] = previousRuntime
  fs.rmSync(workspace, { recursive: true, force: true })
})

describe('Runtime 版本查询的能力透传', () => {
  it.each([true, false])('残留备份的能力不能覆盖当前 exe：当前支持=%s', async supported => {
    fs.writeFileSync(`${runtimePath}.old`, 'backup runtime')
    probe.run
      .mockResolvedValueOnce({
        success: true,
        result: { details: { runtimeVersion: 'v0.2.0', bootstrapEnvironmentReuse: supported } },
      })
      .mockResolvedValueOnce({
        success: true,
        result: { details: { runtimeVersion: 'v0.2.0', bootstrapEnvironmentReuse: !supported } },
      })
    const outcome = await syncRuntimeBinary({
      appRoot: workspace,
      runtimePath,
      target: { version: 'v0.1.28' },
    })
    expect(outcome.status).toBe('current')
    expect(outcome.bootstrapEnvironmentReuse === true).toBe(supported)
    expect(probe.run).toHaveBeenCalledTimes(2)
  })

  it.each([true, undefined, 'true'])('仅接受实际 exe 公告的布尔能力：%s', async capability => {
    probe.run.mockResolvedValue({
      success: true,
      result: { details: { runtimeVersion: 'v0.1.28', bootstrapEnvironmentReuse: capability } },
    })
    const outcome = await syncRuntimeBinary({
      appRoot: workspace,
      runtimePath,
      target: { version: 'v0.1.28' },
    })
    expect(outcome.status).toBe('current')
    expect(outcome.bootstrapEnvironmentReuse === true).toBe(capability === true)
    expect(probe.run).toHaveBeenCalledTimes(1)
    expect(probe.run.mock.calls[0][0]).toEqual(['version'])
  })

  it('本地版本更高时依据实际 exe 能力，不依据线上目标猜测', async () => {
    probe.run.mockResolvedValue({
      success: true,
      result: { details: { runtimeVersion: 'v0.2.0', bootstrapEnvironmentReuse: true } },
    })
    const outcome = await syncRuntimeBinary({
      appRoot: workspace,
      runtimePath,
      target: { version: 'v0.1.28' },
    })
    expect(outcome.status).toBe('current')
    expect(outcome.bootstrapEnvironmentReuse).toBe(true)
    expect(probe.run).toHaveBeenCalledTimes(1)
  })
})
