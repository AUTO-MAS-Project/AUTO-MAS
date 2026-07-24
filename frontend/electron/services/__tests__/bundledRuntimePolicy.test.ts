import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'

import { afterEach, describe, expect, it } from 'vitest'

import { getBundledRuntimeReleaseEnvironment } from '../bundledRuntimePolicy'

const temporaryDirectories: string[] = []
const resourcesProcess = process as NodeJS.Process & { resourcesPath?: string }
const originalResourcesPathDescriptor = Object.getOwnPropertyDescriptor(process, 'resourcesPath')

function createAppRoot(): string {
  const appRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'auto-mas-runtime-policy-'))
  temporaryDirectories.push(appRoot)
  return appRoot
}

function writeSnapshot(appRoot: string, document: unknown): void {
  const snapshotDirectory = path.join(appRoot, 'res')
  fs.mkdirSync(snapshotDirectory, { recursive: true })
  fs.writeFileSync(
    path.join(snapshotDirectory, 'integration-snapshot.json'),
    JSON.stringify(document),
    'utf8'
  )
}

function restoreResourcesPath(): void {
  if (originalResourcesPathDescriptor) {
    Object.defineProperty(process, 'resourcesPath', originalResourcesPathDescriptor)
  } else {
    Reflect.deleteProperty(resourcesProcess, 'resourcesPath')
  }
}

afterEach(() => {
  restoreResourcesPath()
  for (const directory of temporaryDirectories.splice(0)) {
    fs.rmSync(directory, { recursive: true, force: true })
  }
})

describe('bundled runtime release policy', () => {
  it('enables Alpha environment flags only for a complete local Alpha/manual-only policy', () => {
    const appRoot = createAppRoot()
    writeSnapshot(appRoot, {
      schema_version: 1,
      deployment_mode: 'bundled-snapshot',
      release_policy: {
        channel: 'experimental-alpha',
        embedded_updater: 'manual-only',
      },
    })

    expect(getBundledRuntimeReleaseEnvironment(appRoot)).toEqual({
      AUTO_MAS_RELEASE_CHANNEL: 'experimental-alpha',
      AUTO_MAS_EMBEDDED_UPDATE_POLICY: 'manual-only',
    })
  })

  it.each([
    ['missing policy', { schema_version: 1, deployment_mode: 'bundled-snapshot' }],
    [
      'stable channel',
      {
        schema_version: 1,
        deployment_mode: 'bundled-snapshot',
        release_policy: { channel: 'stable', embedded_updater: 'manual-only' },
      },
    ],
    [
      'automatic update policy',
      {
        schema_version: 1,
        deployment_mode: 'bundled-snapshot',
        release_policy: { channel: 'experimental-alpha', embedded_updater: 'automatic' },
      },
    ],
    [
      'conflicting channel fields',
      {
        schema_version: 1,
        deployment_mode: 'bundled-snapshot',
        release_policy: {
          channel: 'experimental-alpha',
          release_channel: 'stable',
          embedded_updater: 'manual-only',
        },
      },
    ],
  ])('fails closed for %s', (_label, document) => {
    const appRoot = createAppRoot()
    writeSnapshot(appRoot, document)

    expect(getBundledRuntimeReleaseEnvironment(appRoot)).toEqual({})
  })

  it('reads the packaged snapshot when no local snapshot exists', () => {
    const appRoot = createAppRoot()
    const resourcesPath = createAppRoot()
    const snapshotDirectory = path.join(resourcesPath, 'integration-snapshot')
    fs.mkdirSync(snapshotDirectory, { recursive: true })
    fs.writeFileSync(
      path.join(snapshotDirectory, 'manifest.json'),
      JSON.stringify({
        schema_version: 1,
        deployment_mode: 'bundled-snapshot',
        release_policy: {
          release_channel: 'experimental-alpha',
          embedded_updater: 'manual-only',
        },
      }),
      'utf8'
    )
    Object.defineProperty(resourcesProcess, 'resourcesPath', {
      configurable: true,
      value: resourcesPath,
    })

    expect(getBundledRuntimeReleaseEnvironment(appRoot)).toEqual({
      AUTO_MAS_RELEASE_CHANNEL: 'experimental-alpha',
      AUTO_MAS_EMBEDDED_UPDATE_POLICY: 'manual-only',
    })
  })

  it('keeps a packaged Alpha updater manual-only when its snapshot is missing', () => {
    const appRoot = createAppRoot()

    expect(
      getBundledRuntimeReleaseEnvironment(appRoot, {
        isPackaged: true,
        version: 'v6.0.0-alpha.NEXUS-OVERDRIVE.20260722.1',
      })
    ).toEqual({
      AUTO_MAS_RELEASE_CHANNEL: 'experimental-alpha',
      AUTO_MAS_EMBEDDED_UPDATE_POLICY: 'manual-only',
    })
  })

  it('keeps a packaged Alpha updater manual-only when its snapshot is malformed', () => {
    const appRoot = createAppRoot()
    const snapshotDirectory = path.join(appRoot, 'res')
    fs.mkdirSync(snapshotDirectory, { recursive: true })
    fs.writeFileSync(path.join(snapshotDirectory, 'integration-snapshot.json'), '{', 'utf8')

    expect(
      getBundledRuntimeReleaseEnvironment(appRoot, {
        isPackaged: true,
        version: 'v6.0.0-alpha.NEXUS-OVERDRIVE.20260722.1',
      })
    ).toEqual({
      AUTO_MAS_RELEASE_CHANNEL: 'experimental-alpha',
      AUTO_MAS_EMBEDDED_UPDATE_POLICY: 'manual-only',
    })
  })

  it('does not infer Alpha flags for a packaged stable runtime from a stale snapshot', () => {
    const appRoot = createAppRoot()
    writeSnapshot(appRoot, {
      schema_version: 1,
      deployment_mode: 'bundled-snapshot',
      release_policy: {
        channel: 'experimental-alpha',
        embedded_updater: 'manual-only',
      },
    })

    expect(
      getBundledRuntimeReleaseEnvironment(appRoot, {
        isPackaged: true,
        version: 'v6.0.0',
      })
    ).toEqual({})
  })

  it('rejects incomplete packaged release metadata instead of falling back to an Alpha version', () => {
    const appRoot = createAppRoot()

    expect(
      getBundledRuntimeReleaseEnvironment(appRoot, {
        isPackaged: true,
        version: 'v6.0.0-alpha.NEXUS-OVERDRIVE.20260722.1',
        metadata: { autoMasReleaseChannel: 'experimental-alpha' },
      })
    ).toEqual({})
  })

  it('does not fall through a malformed local snapshot to a packaged Alpha policy', () => {
    const appRoot = createAppRoot()
    const localDirectory = path.join(appRoot, 'res')
    fs.mkdirSync(localDirectory, { recursive: true })
    fs.writeFileSync(path.join(localDirectory, 'integration-snapshot.json'), '{', 'utf8')

    const resourcesPath = createAppRoot()
    const snapshotDirectory = path.join(resourcesPath, 'integration-snapshot')
    fs.mkdirSync(snapshotDirectory, { recursive: true })
    fs.writeFileSync(
      path.join(snapshotDirectory, 'manifest.json'),
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
    Object.defineProperty(resourcesProcess, 'resourcesPath', {
      configurable: true,
      value: resourcesPath,
    })

    expect(getBundledRuntimeReleaseEnvironment(appRoot)).toEqual({})
  })
})
