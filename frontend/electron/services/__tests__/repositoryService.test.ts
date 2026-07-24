import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'

import type { MirrorService } from '../mirrorService'
import { RepositoryService } from '../repositoryService'
import { writeCompleteWheelhouse } from './wheelhouseFixture'

interface SnapshotWorkspace {
  appRoot: string
  snapshotPath: string
  tmpDir: string
  wheelPath: string
  markerPath: string
}

function createSnapshotWorkspace(): SnapshotWorkspace {
  const snapshotVersion = 'v6.0.0-alpha.test'
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'mas-snapshot-test-'))
  const appRoot = path.join(tmpDir, 'app-root')
  const snapshotPath = path.join(appRoot, 'resources', 'integration-snapshot')
  const requiredDirectories = [
    'app',
    'plugins/auto_mas_core',
    'plugins/browser',
    'plugins/wheels',
    'plugins/ok_script_adapter',
    'plugins/okww_adapter',
    'res',
    'scripts',
    'scripts',
  ]
  for (const directory of requiredDirectories) {
    fs.mkdirSync(path.join(snapshotPath, directory), { recursive: true })
  }
  fs.writeFileSync(path.join(snapshotPath, 'main.py'), '# bundled main')
  fs.writeFileSync(path.join(snapshotPath, 'pyproject.toml'), '[project]\nname = "bundled"\n')
  fs.writeFileSync(path.join(snapshotPath, 'requirements.txt'), 'example==1.0.0\n')
  fs.writeFileSync(path.join(snapshotPath, 'LICENSE'), 'test license\n')
  fs.writeFileSync(path.join(snapshotPath, 'README.md'), '# test\n')
  fs.writeFileSync(path.join(snapshotPath, 'requirements.txt'), '')
  fs.writeFileSync(path.join(snapshotPath, 'LICENSE'), 'test license')
  fs.writeFileSync(path.join(snapshotPath, 'README.md'), '# test snapshot')
  fs.writeFileSync(path.join(snapshotPath, 'app', 'new.txt'), 'new runtime')
  fs.writeFileSync(
    path.join(snapshotPath, 'res', 'version.json'),
    JSON.stringify({ version: snapshotVersion, version_info: { [snapshotVersion]: {} } })
  )

  const wheelsDir = path.join(snapshotPath, 'plugins', 'wheels')
  const { filenames, manifestSha256, runtimeLockSha256, coreVersion } =
    writeCompleteWheelhouse(wheelsDir)
  const wheelPath = path.join(wheelsDir, filenames[0])

  const markerPath = path.join(snapshotPath, 'manifest.json')
  fs.writeFileSync(
    markerPath,
    JSON.stringify({
      schema_version: 1,
      snapshot_id: 'test-snapshot',
      version: snapshotVersion,
      deployment_mode: 'bundled-snapshot',
      required_paths: [
        'app',
        'plugins/auto_mas_core',
        'plugins/browser',
        'plugins/ok_script_adapter',
        'plugins/okww_adapter',
        'plugins/wheels/manifest.json',
        'plugins/wheels/runtime-lock.json',
        'plugins/wheels/pylock.host.toml',
        'plugins/wheels/pylock.combined.toml',
        'main.py',
        'pyproject.toml',
        'requirements.txt',
        'LICENSE',
        'README.md',
        'scripts',
        'res/version.json',
      ],
      wheel_manifest: 'plugins/wheels/manifest.json',
      wheelhouse_contract: {
        manifest_schema_version: 3,
        runtime_lock_schema_version: 1,
        wheel_count: filenames.length,
        plugin_distribution_count: 23,
        plugin_entry_point_count: 21,
        core_distribution_version: coreVersion,
        manifest_sha256: manifestSha256,
        runtime_lock_sha256: runtimeLockSha256,
      },
    })
  )

  return { appRoot, snapshotPath, tmpDir, wheelPath, markerPath }
}

type AnyService = RepositoryService & { [key: string]: any }

describe('RepositoryService bundled integration snapshot', () => {
  let workspace: SnapshotWorkspace
  let service: AnyService

  beforeEach(() => {
    workspace = createSnapshotWorkspace()
    service = new RepositoryService(
      workspace.appRoot,
      {} as unknown as MirrorService,
      'dev_v2'
    ) as AnyService
  })

  afterEach(() => {
    vi.restoreAllMocks()
    fs.rmSync(workspace.tmpDir, { recursive: true, force: true })
  })

  it('accepts a complete snapshot whose wheel manifest matches its files', () => {
    expect(service.resolveBundledSnapshotPath()).toBe(workspace.snapshotPath)
  })

  it('rejects a marker path that escapes the snapshot root', () => {
    const marker = JSON.parse(fs.readFileSync(workspace.markerPath, 'utf-8'))
    marker.required_paths.push('../outside.txt')
    fs.writeFileSync(workspace.markerPath, JSON.stringify(marker))

    expect(() => service.resolveBundledSnapshotPath()).toThrow('escapes its root')
  })

  it('rejects a marker whose required path is missing', () => {
    const marker = JSON.parse(fs.readFileSync(workspace.markerPath, 'utf-8'))
    marker.required_paths.push('plugins/missing/pyproject.toml')
    fs.writeFileSync(workspace.markerPath, JSON.stringify(marker))

    expect(() => service.resolveBundledSnapshotPath()).toThrow('marker paths are missing')
  })

  it('rejects a required runtime directory whose type is wrong', () => {
    fs.rmSync(path.join(workspace.snapshotPath, 'scripts'), { recursive: true })
    fs.writeFileSync(path.join(workspace.snapshotPath, 'scripts'), 'not a directory')

    expect(() => service.resolveBundledSnapshotPath()).toThrow('wrong type')
  })

  it.each([
    ['deployment_mode', 'remote-clone'],
    ['version', 'v5.4.0-beta.1'],
  ])('rejects an unsupported marker %s', (field, value) => {
    const marker = JSON.parse(fs.readFileSync(workspace.markerPath, 'utf-8'))
    marker[field] = value
    fs.writeFileSync(workspace.markerPath, JSON.stringify(marker))

    expect(() => service.resolveBundledSnapshotPath()).toThrow('unsupported schema or version')
  })

  it('rejects a marker version that differs from snapshot res/version.json', () => {
    const marker = JSON.parse(fs.readFileSync(workspace.markerPath, 'utf-8'))
    marker.version = 'v6.0.0-alpha.other'
    fs.writeFileSync(workspace.markerPath, JSON.stringify(marker))

    expect(() => service.resolveBundledSnapshotPath()).toThrow(
      'marker version does not match res/version.json'
    )
  })

  it.each([
    ['wheel_count', 24, 'wheel count expected 24, got 23'],
    ['core_distribution_version', '6.0.0a2', 'core distribution version expected 6.0.0a2'],
    ['manifest_sha256', '0'.repeat(64), 'manifest SHA-256'],
    ['runtime_lock_sha256', '0'.repeat(64), 'runtime lock SHA-256'],
  ])('rejects a stale marker %s declaration', (field, value, expectedError) => {
    const marker = JSON.parse(fs.readFileSync(workspace.markerPath, 'utf-8'))
    marker.wheelhouse_contract[field] = value
    fs.writeFileSync(workspace.markerPath, JSON.stringify(marker))

    expect(() => service.resolveBundledSnapshotPath()).toThrow(expectedError)
  })

  it('rejects a wheel manifest path outside the deployed wheelhouse', () => {
    const alternateDirectory = path.join(workspace.snapshotPath, 'alternate')
    fs.mkdirSync(alternateDirectory)
    fs.copyFileSync(
      path.join(workspace.snapshotPath, 'plugins', 'wheels', 'manifest.json'),
      path.join(alternateDirectory, 'manifest.json')
    )
    const marker = JSON.parse(fs.readFileSync(workspace.markerPath, 'utf-8'))
    marker.wheel_manifest = 'alternate/manifest.json'
    fs.writeFileSync(workspace.markerPath, JSON.stringify(marker))

    expect(() => service.resolveBundledSnapshotPath()).toThrow(
      'must reference plugins/wheels/manifest.json'
    )
  })

  it('does not replace existing runtime files when a bundled wheel is tampered', async () => {
    const runtimeApp = path.join(workspace.appRoot, 'app')
    fs.mkdirSync(runtimeApp, { recursive: true })
    const sentinelPath = path.join(runtimeApp, 'sentinel.txt')
    fs.writeFileSync(sentinelPath, 'keep me')
    fs.writeFileSync(workspace.wheelPath, 'tampered wheel content')

    const result = await service.pullRepository()

    expect(result.success).toBe(false)
    expect(result.error).toMatch(/(size|SHA-256) mismatch/)
    expect(fs.readFileSync(sentinelPath, 'utf-8')).toBe('keep me')
  })

  it('rolls back every promoted item when a later same-volume swap fails', async () => {
    const runtimeApp = path.join(workspace.appRoot, 'app')
    const runtimeRes = path.join(workspace.appRoot, 'res')
    fs.mkdirSync(runtimeApp, { recursive: true })
    fs.mkdirSync(runtimeRes, { recursive: true })
    fs.writeFileSync(path.join(runtimeApp, 'sentinel.txt'), 'old app')
    fs.writeFileSync(path.join(runtimeRes, 'sentinel.txt'), 'old res')

    const originalMovePath = service.movePath.bind(service)
    vi.spyOn(service, 'movePath').mockImplementation(
      (sourcePath: string, destinationPath: string) => {
        if (
          sourcePath.includes('.runtime-stage-') &&
          destinationPath === path.join(workspace.appRoot, 'res')
        ) {
          throw new Error('simulated promotion failure')
        }
        originalMovePath(sourcePath, destinationPath)
      }
    )

    const result = await service.pullRepository()

    expect(result.success).toBe(false)
    expect(result.error).toContain('was rolled back')
    expect(fs.readFileSync(path.join(runtimeApp, 'sentinel.txt'), 'utf-8')).toBe('old app')
    expect(fs.readFileSync(path.join(runtimeRes, 'sentinel.txt'), 'utf-8')).toBe('old res')
    expect(fs.existsSync(path.join(runtimeApp, 'new.txt'))).toBe(false)
    expect(
      fs
        .readdirSync(workspace.appRoot)
        .some(name => name.startsWith('.runtime-stage-') || name.startsWith('.runtime-backup-'))
    ).toBe(false)
  })

  it('recovers an interrupted deployment after active was moved to backup', () => {
    const runtimeApp = path.join(workspace.appRoot, 'app')
    const stagingDirectory = '.runtime-stage-crash-before-promote'
    const backupDirectory = '.runtime-backup-crash-before-promote'
    const stagingApp = path.join(workspace.appRoot, stagingDirectory, 'app')
    const backupApp = path.join(workspace.appRoot, backupDirectory, 'app')
    fs.mkdirSync(runtimeApp, { recursive: true })
    fs.writeFileSync(path.join(runtimeApp, 'old.txt'), 'old runtime')
    fs.mkdirSync(stagingApp, { recursive: true })
    fs.writeFileSync(path.join(stagingApp, 'new.txt'), 'new runtime')
    fs.mkdirSync(path.dirname(backupApp), { recursive: true })

    service.movePath(runtimeApp, backupApp)
    service.writeDeploymentJournal({
      schema_version: 1,
      staging_directory: stagingDirectory,
      backup_directory: backupDirectory,
      swaps: [{ item: 'app', hadBackup: true }],
    })

    service.recoverInterruptedDeployment()

    expect(fs.readFileSync(path.join(runtimeApp, 'old.txt'), 'utf-8')).toBe('old runtime')
    expect(fs.existsSync(path.join(runtimeApp, 'new.txt'))).toBe(false)
    expect(fs.existsSync(service.transactionJournalPath)).toBe(false)
    expect(fs.existsSync(path.join(workspace.appRoot, stagingDirectory))).toBe(false)
    expect(fs.existsSync(path.join(workspace.appRoot, backupDirectory))).toBe(false)
  })

  it('rolls back an uncommitted promoted runtime after process restart', () => {
    const runtimeApp = path.join(workspace.appRoot, 'app')
    const stagingDirectory = '.runtime-stage-crash-after-promote'
    const backupDirectory = '.runtime-backup-crash-after-promote'
    const stagingApp = path.join(workspace.appRoot, stagingDirectory, 'app')
    const backupApp = path.join(workspace.appRoot, backupDirectory, 'app')
    fs.mkdirSync(runtimeApp, { recursive: true })
    fs.writeFileSync(path.join(runtimeApp, 'old.txt'), 'old runtime')
    fs.mkdirSync(stagingApp, { recursive: true })
    fs.writeFileSync(path.join(stagingApp, 'new.txt'), 'new runtime')
    fs.mkdirSync(path.dirname(backupApp), { recursive: true })

    service.movePath(runtimeApp, backupApp)
    service.movePath(stagingApp, runtimeApp)
    service.writeDeploymentJournal({
      schema_version: 1,
      staging_directory: stagingDirectory,
      backup_directory: backupDirectory,
      swaps: [{ item: 'app', hadBackup: true }],
    })

    service.recoverInterruptedDeployment()

    expect(fs.readFileSync(path.join(runtimeApp, 'old.txt'), 'utf-8')).toBe('old runtime')
    expect(fs.existsSync(path.join(runtimeApp, 'new.txt'))).toBe(false)
    expect(fs.existsSync(service.transactionJournalPath)).toBe(false)
  })

  it('rejects a recovery journal that attempts path traversal', () => {
    fs.mkdirSync(path.dirname(service.transactionJournalPath), { recursive: true })
    fs.writeFileSync(
      service.transactionJournalPath,
      JSON.stringify({
        schema_version: 1,
        staging_directory: '../outside',
        backup_directory: '.runtime-backup-safe',
        swaps: [{ item: 'app', hadBackup: true }],
      })
    )

    expect(() => service.recoverInterruptedDeployment()).toThrow('unsupported schema')
  })
})
