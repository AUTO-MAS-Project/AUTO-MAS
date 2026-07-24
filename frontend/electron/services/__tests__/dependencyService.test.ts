import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'

import { runBoundedProcess } from '../boundedProcess'
import { readAndVerifyBundledRuntimeLock } from '../bundledArtifactValidation'
import { DependencyService } from '../dependencyService'
import type { MirrorService } from '../mirrorService'
import { writeCompleteWheelhouse } from './wheelhouseFixture'

vi.mock('../boundedProcess', () => ({
  runBoundedProcess: vi.fn(),
  terminateProcessTree: vi.fn(),
}))

type AnyService = DependencyService & { [key: string]: any }

describe('DependencyService locked host runtime', () => {
  let tmpDir: string
  let service: AnyService

  beforeEach(() => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'mas-dependency-lock-test-'))
    service = new DependencyService(tmpDir, {} as MirrorService) as AnyService
    fs.mkdirSync(path.dirname(service.uvExe), { recursive: true })
    fs.writeFileSync(service.uvExe, 'uv fixture')
    fs.writeFileSync(service.pythonExe, 'python fixture')
    vi.mocked(runBoundedProcess).mockReset()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    fs.rmSync(tmpDir, { recursive: true, force: true })
  })

  it('installs exact host wheel paths with no resolver or index and atomically promotes the venv', async () => {
    writeCompleteWheelhouse(service.wheelsDir, {
      hostRuntime: [
        { distribution: 'host-one', version: '1.0.0' },
        { distribution: 'host-two', version: '2.0.0' },
      ],
    })
    const runtimeLock = readAndVerifyBundledRuntimeLock(service.wheelsDir)
    fs.mkdirSync(service.venvPath, { recursive: true })
    fs.writeFileSync(path.join(service.venvPath, 'old.txt'), 'old environment')

    vi.mocked(runBoundedProcess).mockImplementation(async (_executable, args) => {
      if (args[0] === 'venv') {
        const stagingPath = args[1]
        fs.mkdirSync(path.join(stagingPath, 'Scripts'), { recursive: true })
        fs.writeFileSync(path.join(stagingPath, 'Scripts', 'python.exe'), 'python fixture')
      } else if (args[0] === 'pip') {
        const pythonIndex = args.indexOf('--python')
        const stagingPath = path.resolve(path.dirname(args[pythonIndex + 1]), '..')
        const sitePackages = path.join(stagingPath, 'Lib', 'site-packages')
        for (const item of runtimeLock.host_runtime) {
          const distInfo = path.join(
            sitePackages,
            `${item.distribution.replace(/[-.]/g, '_')}-${item.version}.dist-info`
          )
          fs.mkdirSync(distInfo, { recursive: true })
          fs.writeFileSync(
            path.join(distInfo, 'METADATA'),
            `Metadata-Version: 2.1\nName: ${item.distribution}\nVersion: ${item.version}\n`
          )
        }
      }
      return { stdout: '', stderr: '' }
    })

    await service.installLockedHostRuntime(runtimeLock)

    const pipCall = vi.mocked(runBoundedProcess).mock.calls.find(call => call[1][0] === 'pip')
    const venvCall = vi.mocked(runBoundedProcess).mock.calls.find(call => call[1][0] === 'venv')
    expect(venvCall?.[1]).toContain('--no-config')
    expect(venvCall?.[2]?.env?.UV_NO_CONFIG).toBe('1')
    expect(pipCall).toBeDefined()
    expect(pipCall![1]).toContain('--no-index')
    expect(pipCall![1]).toContain('--no-deps')
    expect(pipCall![1]).not.toContain('--upgrade')
    expect(pipCall![1]).not.toContain('--index-url')
    for (const item of runtimeLock.host_runtime) {
      expect(pipCall![1]).toContain(path.join(service.wheelsDir, item.filename))
    }
    expect(fs.existsSync(path.join(service.venvPath, 'old.txt'))).toBe(false)
    expect(
      service.hasExactLockedDistributions(
        path.join(service.venvPath, 'Lib', 'site-packages'),
        runtimeLock.host_runtime
      )
    ).toBe(true)
  })

  it('only takes the unchanged fast path for the exact locked host distribution set', async () => {
    writeCompleteWheelhouse(service.wheelsDir, {
      hostRuntime: [
        { distribution: 'host-one', version: '1.0.0' },
        { distribution: 'host-two', version: '2.0.0' },
      ],
    })
    const runtimeLock = readAndVerifyBundledRuntimeLock(service.wheelsDir)
    fs.writeFileSync(service.pyprojectPath, '[project]\ndependencies = []\n')
    fs.mkdirSync(path.dirname(service.venvPythonExe), { recursive: true })
    fs.writeFileSync(service.venvPythonExe, 'python fixture')
    const sitePackages = path.join(service.venvPath, 'Lib', 'site-packages')

    const writeDistInfo = (distribution: string, version: string) => {
      const distInfo = path.join(
        sitePackages,
        `${distribution.replace(/[-.]/g, '_')}-${version}.dist-info`
      )
      fs.mkdirSync(distInfo, { recursive: true })
      fs.writeFileSync(
        path.join(distInfo, 'METADATA'),
        `Metadata-Version: 2.1\nName: ${distribution}\nVersion: ${version}\n`
      )
      return distInfo
    }
    for (const item of runtimeLock.host_runtime) {
      writeDistInfo(item.distribution, item.version)
    }
    fs.writeFileSync(service.hashFilePath, service.calculateHash('pyproject', runtimeLock))

    expect((await service.checkDependencies()).needsInstall).toBe(false)

    const hostOne = runtimeLock.host_runtime.find(item => item.distribution === 'host-one')!
    const hostOnePath = path.join(sitePackages, 'host_one-1.0.0.dist-info')
    fs.rmSync(hostOnePath, { recursive: true })
    expect((await service.checkDependencies()).needsInstall).toBe(true)

    writeDistInfo(hostOne.distribution, hostOne.version)
    const extraPath = writeDistInfo('unexpected-package', '9.9.9')
    expect((await service.checkDependencies()).needsInstall).toBe(true)

    fs.rmSync(extraPath, { recursive: true })
    fs.rmSync(hostOnePath, { recursive: true })
    writeDistInfo(hostOne.distribution, '1.0.1')
    expect((await service.checkDependencies()).needsInstall).toBe(true)
  })

  it('refuses online fallback when an integration snapshot lost its wheelhouse', () => {
    const marker = path.join(tmpDir, 'res', 'integration-snapshot.json')
    fs.mkdirSync(path.dirname(marker), { recursive: true })
    fs.writeFileSync(marker, '{}')

    expect(() => service.readBundledRuntimeLockIfPresent()).toThrow('拒绝回退到在线依赖解析')
  })

  it('restores the old venv when post-promotion validation fails', async () => {
    const stagingPath = path.join(tmpDir, '.venv-stage-test')
    fs.mkdirSync(service.venvPath, { recursive: true })
    fs.writeFileSync(path.join(service.venvPath, 'old.txt'), 'old')
    fs.mkdirSync(stagingPath, { recursive: true })
    fs.writeFileSync(path.join(stagingPath, 'new.txt'), 'new')
    vi.spyOn(service, 'validateLockedVenv').mockRejectedValue(
      new Error('simulated validation failure')
    )

    await expect(service.promoteLockedVenv(stagingPath, { host_runtime: [] })).rejects.toThrow(
      '旧环境已恢复'
    )
    expect(fs.readFileSync(path.join(service.venvPath, 'old.txt'), 'utf-8')).toBe('old')
    expect(fs.existsSync(path.join(service.venvPath, 'new.txt'))).toBe(false)
  })

  it('retries transient Windows directory locks while promoting the staged venv', async () => {
    const stagingPath = path.join(tmpDir, '.venv-stage-test')
    fs.mkdirSync(stagingPath, { recursive: true })
    fs.writeFileSync(path.join(stagingPath, 'new.txt'), 'new')
    vi.spyOn(service, 'validateLockedVenv').mockResolvedValue(undefined)
    vi.spyOn(service, 'waitForFilesystemRetry').mockResolvedValue(undefined)

    const realRename = fs.promises.rename.bind(fs.promises)
    let stagingRenameAttempts = 0
    vi.spyOn(fs.promises, 'rename').mockImplementation(async (sourcePath, targetPath) => {
      if (
        path.resolve(sourcePath.toString()) === path.resolve(stagingPath) &&
        path.resolve(targetPath.toString()) === path.resolve(service.venvPath)
      ) {
        stagingRenameAttempts += 1
        if (stagingRenameAttempts < 3) {
          throw Object.assign(new Error('simulated Windows scanner lock'), { code: 'EPERM' })
        }
      }
      await realRename(sourcePath, targetPath)
    })

    await service.promoteLockedVenv(stagingPath, { host_runtime: [] })

    expect(stagingRenameAttempts).toBe(3)
    expect(service.waitForFilesystemRetry).toHaveBeenCalledTimes(2)
    expect(fs.readFileSync(path.join(service.venvPath, 'new.txt'), 'utf-8')).toBe('new')
    expect(fs.existsSync(service.venvTransactionJournalPath)).toBe(false)
  })

  it('recovers a prepared crash journal by restoring the backup venv', async () => {
    const backupPath = path.join(tmpDir, '.venv-backup-test')
    const stagingPath = path.join(tmpDir, '.venv-stage-test')
    fs.mkdirSync(service.venvPath, { recursive: true })
    fs.writeFileSync(path.join(service.venvPath, 'new.txt'), 'new')
    fs.mkdirSync(backupPath)
    fs.writeFileSync(path.join(backupPath, 'old.txt'), 'old')
    fs.mkdirSync(stagingPath)
    fs.mkdirSync(path.dirname(service.venvTransactionJournalPath), { recursive: true })
    fs.writeFileSync(
      service.venvTransactionJournalPath,
      JSON.stringify({
        schema_version: 1,
        phase: 'prepared',
        had_active_target: true,
        active_path: service.venvPath,
        staging_path: stagingPath,
        backup_path: backupPath,
      })
    )

    await service.recoverVenvTransaction()

    expect(fs.readFileSync(path.join(service.venvPath, 'old.txt'), 'utf-8')).toBe('old')
    expect(fs.existsSync(path.join(service.venvPath, 'new.txt'))).toBe(false)
    expect(fs.existsSync(service.venvTransactionJournalPath)).toBe(false)
  })
})
