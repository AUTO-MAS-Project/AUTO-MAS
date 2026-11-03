import { describe, expect, it, vi } from 'vite-plus/test'

const construct = vi.hoisted(() => vi.fn())
vi.mock('./client', () => ({
  RuntimeClient: class {
    constructor(options: unknown) {
      construct(options)
    }
  },
}))
vi.mock('../instanceConfig', () => ({ getApplicationEnvironment: () => 'development' }))
vi.mock('./runtimeEnv', () => ({
  RUNTIME_APP_ENV: 'AUTO_MAS_ENV',
  buildRuntimeEnv: () => ({ AUTO_MAS_TELEMETRY: 'disabled' }),
}))

import { createRuntimeClient } from './runtimeClientFactory'

describe('desktop backend environment', () => {
  it('enforces home-paint gating for desktop backends', () => {
    createRuntimeClient({ appRoot: 'isolated-root', env: { AUTO_MAS_MCP_WAIT_FOR_HOME: '0' } })
    expect(construct).toHaveBeenCalledWith(
      expect.objectContaining({
        env: expect.objectContaining({
          AUTO_MAS_MCP_WAIT_FOR_HOME: '1',
        }),
      })
    )
  })
})
