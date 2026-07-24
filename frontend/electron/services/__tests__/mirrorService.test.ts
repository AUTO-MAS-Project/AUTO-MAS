import { afterEach, describe, expect, it } from 'vitest'
import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'

import { MirrorService } from '../mirrorService'

const temporaryRoots: string[] = []

function createRoot(): string {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'auto-mas-mirror-local-'))
  temporaryRoots.push(root)
  return root
}

function markAsBundledRuntime(root: string): void {
  const snapshotPath = path.join(root, 'res', 'integration-snapshot.json')
  fs.mkdirSync(path.dirname(snapshotPath), { recursive: true })
  fs.writeFileSync(snapshotPath, JSON.stringify({ deployment_mode: 'bundled-snapshot' }), 'utf-8')
}

afterEach(() => {
  for (const root of temporaryRoots.splice(0)) {
    fs.rmSync(root, { recursive: true, force: true })
  }
})

describe('MirrorService.initializeLocal', () => {
  it('loads cached endpoints without performing cloud initialization', () => {
    const appRoot = createRoot()
    const configDir = path.join(appRoot, 'config')
    fs.mkdirSync(configDir, { recursive: true })
    fs.writeFileSync(
      path.join(configDir, 'mirror_config.json'),
      JSON.stringify({
        config: {
          mirrors: {},
          apiEndpoints: {
            local: 'http://127.0.0.1:36163',
            websocket: 'ws://127.0.0.1:36163',
          },
        },
        etag: 'local-etag',
        lastUpdated: '2026-07-22T00:00:00.000Z',
      }),
      'utf-8'
    )

    const service = new MirrorService(appRoot)
    service.initializeLocal()

    expect(service.getApiEndpoints()).toEqual({
      local: 'http://127.0.0.1:36163',
      websocket: 'ws://127.0.0.1:36163',
    })
  })

  it('keeps built-in IPv4 loopback endpoints when no cache exists', () => {
    const service = new MirrorService(createRoot())

    service.initializeLocal()

    expect(service.getApiEndpoints()).toEqual({
      local: 'http://127.0.0.1:36163',
      websocket: 'ws://127.0.0.1:36163',
    })
  })

  it('pins a bundled runtime to the local backend despite cached or runtime endpoint overrides', () => {
    const appRoot = createRoot()
    markAsBundledRuntime(appRoot)
    const configDir = path.join(appRoot, 'config')
    fs.mkdirSync(configDir, { recursive: true })
    fs.writeFileSync(
      path.join(configDir, 'mirror_config.json'),
      JSON.stringify({
        config: {
          mirrors: {},
          apiEndpoints: {
            local: 'https://evil.example',
            websocket: 'wss://evil.example',
          },
        },
        lastUpdated: '2026-07-24T00:00:00.000Z',
      }),
      'utf-8'
    )

    const service = new MirrorService(appRoot)
    expect(service.getApiEndpoints()).toEqual({
      local: 'http://127.0.0.1:36163',
      websocket: 'ws://127.0.0.1:36163',
    })

    service.initializeLocal()
    service.updateApiEndpoints({
      local: 'http://127.0.0.1:49999',
      websocket: 'ws://127.0.0.1:49999',
    })

    expect(service.getApiEndpoint('local')).toBe('http://127.0.0.1:36163')
    expect(service.getApiEndpoint('websocket')).toBe('ws://127.0.0.1:36163')
  })
})
