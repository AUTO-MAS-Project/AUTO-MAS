import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'

import { describe, expect, it, vi } from 'vitest'

import { BackendService } from '../backendService'
import type { MirrorService } from '../mirrorService'

const marker = {
  schemaVersion: 1 as const,
  appRoot: 'C:\\AUTO-MAS-test',
  mainPy: 'C:\\AUTO-MAS-test\\main.py',
  ownerToken: 'owner-token-1234567890',
  createdAt: '2026-07-22T00:00:00.000Z',
  pid: 4242,
  creationTime: '2026-07-22T00:00:00.000Z',
  executablePath: 'C:\\AUTO-MAS-test\\.venv\\Scripts\\python.exe',
  commandLine: '"C:\\AUTO-MAS-test\\.venv\\Scripts\\python.exe" "C:\\AUTO-MAS-test\\main.py"',
}

interface BackendServiceInternals {
  startBackendUnlocked: () => Promise<{ success: boolean; error?: string }>
  prepareUntrackedBackendForStart: (options?: {
    pythonPath?: string
    mainPyPath?: string
    cwd?: string
  }) => Promise<boolean>
  isDevelopmentOrCustomLaunch: (options?: {
    pythonPath?: string
    mainPyPath?: string
    cwd?: string
  }) => boolean
  stopBackendForRuntimeMutationUnlocked: () => Promise<{
    success: boolean
    wasRunning: boolean
    error?: string
  }>
  getBackendPythonArgs: (mainPy: string) => string[]
  getBackendSpawnEnvironment: (options: {
    uvDir: string
    processPath: string
    processPathExt: string
    ownerToken: string | null
  }) => NodeJS.ProcessEnv
  loadVerifiedBackendOwnership: () => Promise<typeof marker | null>
  probeBackendEndpoint: () => Promise<{
    reachable: boolean
    valid: boolean
    devMode?: boolean
    pid?: number
    ownerToken?: string
    httpAuthToken?: string
  }>
  requestBackendClose: (authToken?: string) => Promise<{ success: boolean; error?: string }>
  waitForOwnedProcessExit: (ownership: typeof marker, timeoutMs: number) => Promise<boolean>
  terminateOwnedProcess: (ownership: typeof marker) => Promise<boolean>
  clearOwnershipMarker: (pid: number, ownerToken: string) => void
}

function createService(): BackendService {
  const mirrorService = {
    getApiEndpoint: () => 'http://localhost:36163',
  } as unknown as MirrorService
  return new BackendService(marker.appRoot, mirrorService)
}

describe('BackendService backend launch arguments', () => {
  it('always isolates the packaged virtual environment from machine-wide Python paths', () => {
    const service = createService()
    const internals = service as unknown as BackendServiceInternals

    expect(internals.getBackendPythonArgs(marker.mainPy)).toEqual(['-I', marker.mainPy])
  })

  it('passes an explicit Alpha/manual-only snapshot policy into the Python environment', () => {
    const appRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'auto-mas-alpha-policy-'))
    const snapshotDirectory = path.join(appRoot, 'res')
    fs.mkdirSync(snapshotDirectory, { recursive: true })
    fs.writeFileSync(
      path.join(snapshotDirectory, 'integration-snapshot.json'),
      JSON.stringify({
        schema_version: 1,
        deployment_mode: 'bundled-snapshot',
        release_policy: {
          channel: 'experimental-alpha',
          embedded_updater: 'manual-only',
        },
      }),
      'utf8'
    )

    try {
      const service = new BackendService(appRoot, {
        getApiEndpoint: () => 'http://localhost:36163',
      } as unknown as MirrorService)
      const internals = service as unknown as BackendServiceInternals

      expect(
        internals.getBackendSpawnEnvironment({
          uvDir: path.join(appRoot, 'environment', 'python', 'Scripts'),
          processPath: 'C:\\Windows\\System32',
          processPathExt: '.COM;.EXE;.BAT;.CMD',
          ownerToken: 'owner-token-1234567890',
        })
      ).toMatchObject({
        AUTO_MAS_RELEASE_CHANNEL: 'experimental-alpha',
        AUTO_MAS_EMBEDDED_UPDATE_POLICY: 'manual-only',
        AUTO_MAS_DEV: '0',
        NODE_ENV: 'production',
        AUTO_MAS_BACKEND_OWNER_TOKEN: 'owner-token-1234567890',
      })
    } finally {
      fs.rmSync(appRoot, { recursive: true, force: true })
    }
  })

  it('does not trust inherited development flags for a bundled Alpha runtime', () => {
    const appRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'auto-mas-alpha-dev-flags-'))
    const snapshotDirectory = path.join(appRoot, 'res')
    fs.mkdirSync(snapshotDirectory, { recursive: true })
    fs.writeFileSync(
      path.join(snapshotDirectory, 'integration-snapshot.json'),
      JSON.stringify({ deployment_mode: 'bundled-snapshot' }),
      'utf8'
    )
    vi.stubEnv('NODE_ENV', 'development')
    vi.stubEnv('AUTO_MAS_DEV', '1')

    try {
      const service = new BackendService(appRoot, {
        getApiEndpoint: () => 'http://127.0.0.1:36163',
      } as unknown as MirrorService)
      const internals = service as unknown as BackendServiceInternals
      const environment = internals.getBackendSpawnEnvironment({
        uvDir: path.join(appRoot, 'environment', 'python', 'Scripts'),
        processPath: 'C:\\Windows\\System32',
        processPathExt: '.COM;.EXE;.BAT;.CMD',
        ownerToken: null,
      })

      expect(internals.isDevelopmentOrCustomLaunch()).toBe(false)
      expect(environment).toMatchObject({ AUTO_MAS_DEV: '0', NODE_ENV: 'production' })
    } finally {
      vi.unstubAllEnvs()
      fs.rmSync(appRoot, { recursive: true, force: true })
    }
  })
})

describe('BackendService lifecycle serialization', () => {
  it('does not enter a second start operation before the first one settles', async () => {
    const service = createService()
    const internals = service as unknown as BackendServiceInternals
    let releaseFirst: (() => void) | undefined
    const firstBlocked = new Promise<void>(resolve => {
      releaseFirst = resolve
    })
    const startUnlocked = vi
      .spyOn(internals, 'startBackendUnlocked')
      .mockImplementationOnce(async () => {
        await firstBlocked
        return { success: true }
      })
      .mockResolvedValueOnce({ success: true })

    const first = service.startBackend()
    const second = service.startBackend()
    await Promise.resolve()

    expect(startUnlocked).toHaveBeenCalledTimes(1)
    releaseFirst?.()
    await expect(Promise.all([first, second])).resolves.toEqual([
      { success: true },
      { success: true },
    ])
    expect(startUnlocked).toHaveBeenCalledTimes(2)
  })
})

describe('BackendService untracked development backend isolation', () => {
  it('refuses to attach a production release to a development backend', async () => {
    const service = createService()
    const internals = service as unknown as BackendServiceInternals
    vi.spyOn(internals, 'probeBackendEndpoint').mockResolvedValue({
      reachable: true,
      valid: true,
      devMode: true,
    })
    const stop = vi
      .spyOn(internals, 'stopBackendForRuntimeMutationUnlocked')
      .mockResolvedValue({ success: true, wasRunning: false })

    await expect(internals.prepareUntrackedBackendForStart()).rejects.toThrow(
      '发布版不会复用或停止'
    )
    expect(stop).not.toHaveBeenCalled()
  })

  it('still permits an explicit development launch to reuse its development backend', async () => {
    const service = createService()
    const internals = service as unknown as BackendServiceInternals
    vi.spyOn(internals, 'probeBackendEndpoint').mockResolvedValue({
      reachable: true,
      valid: true,
      devMode: true,
    })
    const stop = vi
      .spyOn(internals, 'stopBackendForRuntimeMutationUnlocked')
      .mockResolvedValue({ success: true, wasRunning: false })

    await expect(
      internals.prepareUntrackedBackendForStart({ pythonPath: 'C:\\dev\\python.exe' })
    ).resolves.toBe(false)
    expect(stop).not.toHaveBeenCalled()
  })
})

describe('BackendService ownership marker durability', () => {
  it('quarantines a truncated marker instead of permanently blocking startup', async () => {
    const appRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'auto-mas-backend-marker-'))
    const markerDirectory = path.join(appRoot, 'environment')
    const markerPath = path.join(markerDirectory, '.backend_ownership.json')
    fs.mkdirSync(markerDirectory, { recursive: true })
    fs.writeFileSync(markerPath, '{"schemaVersion":', 'utf-8')

    try {
      const mirrorService = {
        getApiEndpoint: () => 'http://localhost:36163',
      } as unknown as MirrorService
      const service = new BackendService(appRoot, mirrorService)
      const internals = service as unknown as BackendServiceInternals

      await expect(internals.loadVerifiedBackendOwnership()).resolves.toBeNull()
      expect(fs.existsSync(markerPath)).toBe(false)
      expect(
        fs
          .readdirSync(markerDirectory)
          .filter(name => name.startsWith('.backend_ownership.json.unreadable.'))
      ).toHaveLength(1)
    } finally {
      fs.rmSync(appRoot, { recursive: true, force: true })
    }
  })
})

describe('BackendService.stopBackendForRuntimeMutation', () => {
  it('gracefully stops an untracked production backend only when marker, PID and token match', async () => {
    const service = createService()
    const internals = service as unknown as BackendServiceInternals
    vi.spyOn(internals, 'loadVerifiedBackendOwnership').mockResolvedValue(marker)
    vi.spyOn(internals, 'probeBackendEndpoint').mockResolvedValue({
      reachable: true,
      valid: true,
      devMode: false,
      pid: marker.pid,
      ownerToken: marker.ownerToken,
      httpAuthToken: 'backend-http-auth-token-1234567890',
    })
    const close = vi.spyOn(internals, 'requestBackendClose').mockResolvedValue({ success: true })
    vi.spyOn(internals, 'waitForOwnedProcessExit').mockResolvedValue(true)
    const terminate = vi.spyOn(internals, 'terminateOwnedProcess')
    vi.spyOn(internals, 'clearOwnershipMarker').mockImplementation(() => undefined)

    await expect(service.stopBackendForRuntimeMutation()).resolves.toEqual({
      success: true,
      wasRunning: true,
    })
    expect(close).toHaveBeenCalledWith('backend-http-auth-token-1234567890')
    expect(terminate).not.toHaveBeenCalled()
  })

  it('refuses to stop a development backend', async () => {
    const service = createService()
    const internals = service as unknown as BackendServiceInternals
    vi.spyOn(internals, 'loadVerifiedBackendOwnership').mockResolvedValue(marker)
    vi.spyOn(internals, 'probeBackendEndpoint').mockResolvedValue({
      reachable: true,
      valid: true,
      devMode: true,
    })
    const close = vi.spyOn(internals, 'requestBackendClose')
    const terminate = vi.spyOn(internals, 'terminateOwnedProcess')

    const result = await service.stopBackendForRuntimeMutation()

    expect(result.success).toBe(false)
    expect(result.error).toContain('开发模式后端')
    expect(close).not.toHaveBeenCalled()
    expect(terminate).not.toHaveBeenCalled()
  })

  it('refuses a reachable backend from another installation', async () => {
    const service = createService()
    const internals = service as unknown as BackendServiceInternals
    vi.spyOn(internals, 'loadVerifiedBackendOwnership').mockResolvedValue(marker)
    vi.spyOn(internals, 'probeBackendEndpoint').mockResolvedValue({
      reachable: true,
      valid: true,
      devMode: false,
      pid: 9001,
      ownerToken: 'different-owner-token',
    })
    const close = vi.spyOn(internals, 'requestBackendClose')
    const terminate = vi.spyOn(internals, 'terminateOwnedProcess')

    const result = await service.stopBackendForRuntimeMutation()

    expect(result.success).toBe(false)
    expect(result.error).toContain('无法确认属于当前安装目录')
    expect(close).not.toHaveBeenCalled()
    expect(terminate).not.toHaveBeenCalled()
  })

  it('uses exact PID termination for a verified orphan when its endpoint is unreachable', async () => {
    const service = createService()
    const internals = service as unknown as BackendServiceInternals
    vi.spyOn(internals, 'loadVerifiedBackendOwnership').mockResolvedValue(marker)
    vi.spyOn(internals, 'probeBackendEndpoint').mockResolvedValue({
      reachable: false,
      valid: false,
    })
    const close = vi.spyOn(internals, 'requestBackendClose')
    const terminate = vi.spyOn(internals, 'terminateOwnedProcess').mockResolvedValue(true)
    vi.spyOn(internals, 'clearOwnershipMarker').mockImplementation(() => undefined)

    await expect(service.stopBackendForRuntimeMutation()).resolves.toEqual({
      success: true,
      wasRunning: true,
    })
    expect(close).not.toHaveBeenCalled()
    expect(terminate).toHaveBeenCalledWith(marker)
  })
})

describe('BackendService.getManagedProcesses', () => {
  it('returns only an orphan whose process identity marker remains verified', async () => {
    const service = createService()
    const internals = service as unknown as BackendServiceInternals
    vi.spyOn(internals, 'loadVerifiedBackendOwnership').mockResolvedValue(marker)
    vi.spyOn(internals, 'probeBackendEndpoint').mockResolvedValue({
      reachable: false,
      valid: false,
    })

    await expect(service.getManagedProcesses()).resolves.toEqual([
      {
        pid: marker.pid,
        name: 'python.exe',
        command: marker.commandLine,
        commandLine: marker.commandLine,
      },
    ])
  })

  it('does not expose a development backend even when an old marker exists', async () => {
    const service = createService()
    const internals = service as unknown as BackendServiceInternals
    vi.spyOn(internals, 'loadVerifiedBackendOwnership').mockResolvedValue(marker)
    vi.spyOn(internals, 'probeBackendEndpoint').mockResolvedValue({
      reachable: true,
      valid: true,
      devMode: true,
      pid: marker.pid,
      ownerToken: marker.ownerToken,
    })

    await expect(service.getManagedProcesses()).resolves.toEqual([])
  })
})
