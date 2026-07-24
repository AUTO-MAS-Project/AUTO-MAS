import { readFileSync } from 'node:fs'
import { beforeAll, describe, expect, it, vi } from 'vitest'

vi.mock('@/views/scheduler/schedulerHandlers', () => ({
  default: {
    handleTaskManagerMessage: vi.fn(),
    handleMainMessage: vi.fn(),
  },
}))

vi.mock('@/api', () => ({
  OpenAPI: { BASE: 'http://localhost:36163' },
}))

vi.mock('ant-design-vue', () => ({
  Modal: { error: vi.fn() },
}))

vi.mock('@/composables/useAppClosing', () => ({
  useAppClosing: () => ({
    isClosing: { value: false },
    showClosingOverlay: vi.fn(),
  }),
}))

const logger = {
  debug: vi.fn(),
  info: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
}

let websocketModule!: typeof import('./useWebSocket')

beforeAll(async () => {
  vi.stubGlobal('window', {
    location: {
      hostname: '127.0.0.1',
      reload: vi.fn(),
    },
    electronAPI: {
      getLogger: () => logger,
      getApiEndpoint: vi.fn().mockResolvedValue('ws://localhost:36163'),
    },
    addEventListener: vi.fn(),
  })
  websocketModule = await import('./useWebSocket')
})

describe('WebSocket dialog protocol helpers', () => {
  it('normalizes optional dialog fields so a valid request remains answerable', () => {
    expect(websocketModule.normalizeDialogRequestData({ requestId: 'request-1' })).toEqual({
      requestId: 'request-1',
      title: '操作提示',
      message: '',
      options: ['确定', '取消'],
    })
  })

  it('rejects a dialog request without a usable correlation id', () => {
    expect(websocketModule.normalizeDialogRequestData({ title: '无 requestId' })).toBeNull()
    expect(websocketModule.normalizeDialogRequestData({ requestId: '   ' })).toBeNull()
    expect(websocketModule.normalizeDialogRequestData(null)).toBeNull()
  })

  it('builds the stable Main dialog.response envelope', () => {
    expect(websocketModule.createDialogResponseMessage('request-2', false)).toEqual({
      id: 'Main',
      type: 'dialog.response',
      data: {
        requestId: 'request-2',
        choice: false,
      },
    })
  })

  it('only treats the exact replacement close contract as terminal', () => {
    expect(
      websocketModule.isConnectionReplacedClose({ code: 4001, reason: 'connection replaced' })
    ).toBe(true)
    expect(
      websocketModule.isConnectionReplacedClose({ code: 4001, reason: 'backend stopped' })
    ).toBe(false)
    expect(
      websocketModule.isConnectionReplacedClose({ code: 1006, reason: 'connection replaced' })
    ).toBe(false)
  })

  it('suppresses reconnect for a service-restart close only while the app is closing', () => {
    const serviceRestartClose = { code: 1012, reason: '' }

    expect(websocketModule.shouldReconnectAfterClose(serviceRestartClose, true)).toBe(false)
    expect(websocketModule.shouldReconnectAfterClose(serviceRestartClose, false)).toBe(true)
  })

  it('suppresses reconnect after a message-too-big protocol close', () => {
    expect(
      websocketModule.shouldReconnectAfterClose({ code: 1009, reason: 'message too big' }, false)
    ).toBe(false)
  })

  it('encodes a non-empty handshake token as the privileged WS subprotocol', () => {
    expect(websocketModule.createWebSocketAuthProtocol('  abc123  ')).toBe('auto-mas-auth.abc123')
    expect(websocketModule.createWebSocketAuthProtocol('   ')).toBeUndefined()
    expect(websocketModule.createWebSocketAuthProtocol(null)).toBeUndefined()
  })
})

describe('WebSocketMessageListener compatibility wiring', () => {
  const source = readFileSync(
    new URL('../components/WebSocketMessageListener.vue', import.meta.url),
    'utf8'
  )

  it('keeps legacy Message while rendering the canonical lifecycle dialog queue', () => {
    expect(source).toContain("subscribe({ type: 'Message' }, handleMessage)")
    expect(source).toContain('dialogRequests')
    expect(source).toContain('respondDialog(modal.messageId, choice)')
    expect(source).toContain("return sendRaw('Response', response, modal.messageId)")
  })

  it('only owns and unsubscribes the legacy listener', () => {
    expect(source).toContain('unsubscribe(legacySubscriptionId)')
    expect(source).not.toContain('dialogSubscriptionId')
  })
})
