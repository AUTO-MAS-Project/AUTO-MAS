import type { TestNode } from './vueRenderer'

export function pluginUiFrame(frame: TestNode) {
  const child = {}
  Object.assign(frame, { contentWindow: child })
  const { port1, port2 } = new MessageChannel()
  const url = new URL(String(frame.props.src), 'http://mas.test')
  const hash = new URLSearchParams(url.hash.slice(1))
  const envelope = {
    source: 'auto-mas-wheel',
    v: Number(hash.get('v')),
    mountToken: hash.get('mountToken'),
    pluginName: hash.get('pluginName'),
    target: JSON.parse(hash.get('target')!),
  }
  const replies = new Map<number, { result?: unknown; error?: string }>()
  const events: { event: 'stateChanged' | 'configReloaded'; payload: unknown }[] = []
  port1.onmessage = ({ data }) => {
    if (data.event) events.push(data)
    else replies.set(data.requestId, data)
  }
  let nextId = 0
  const request = (action: string, params?: object, overrides?: object, requestId = ++nextId) => {
    port1.postMessage({ ...envelope, action, params, requestId, ...overrides })
    return requestId
  }
  function ready(overrides?: object, origin = 'null', source: object = child) {
    const event = new MessageEvent('message', {
      origin,
      data: { ...envelope, type: 'ready', ...overrides },
      ports: [port2],
    })
    Object.defineProperty(event, 'source', { value: source })
    window.dispatchEvent(event)
  }
  return {
    envelope,
    events,
    replies,
    ready,
    request,
    url,
    close: () => {
      port1.close()
      port2.close()
    },
  }
}
