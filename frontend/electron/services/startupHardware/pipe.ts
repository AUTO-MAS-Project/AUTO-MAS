import { randomBytes } from 'node:crypto'
import { createServer, type Socket } from 'node:net'
import { startupAttempt, operationAttempt, localStartupAttempt } from './monitor'
import type { RuntimeEvent } from '../runtime/protocol'

/** 只在这一轮初始化期间服务该 Runtime；凭据与管道名分别随机生成。 */
export function runtimeStartupSample() {
  const attempt = operationAttempt()
  if (!attempt?.sampling) return
  const owner = new WeakRef(attempt)
  if (process.platform !== 'win32' || attempt !== startupAttempt())
    return {
      token: 'local',
      close() {},
      event(event: RuntimeEvent) {
        const active = owner.deref()
        if (active && active === localStartupAttempt()) active.progress(event)
      },
    }
  const token = randomBytes(32).toString('hex')
  let enabled = false
  let disposed = false
  const sockets = new Set<Socket>()
  const server = createServer(socket => {
    sockets.add(socket)
    socket.on('close', () => sockets.delete(socket))
    socket.on('error', () => socket.destroy())
    socket.setTimeout(120, () => socket.destroy())
    let input = ''
    socket.setEncoding('utf8')
    socket.on('data', chunk => {
      input += chunk
      if (input.length > 33) {
        socket.destroy()
        return
      }
      if (!input.endsWith('\n')) return
      const current = owner.deref()
      const summary =
        current &&
        startupAttempt() === current &&
        current.sampling &&
        enabled &&
        input === token.slice(32) + '\n'
          ? current.snapshot(true)
          : {}
      socket.end(JSON.stringify(summary))
    })
  })
  let detach: (() => void) | undefined = attempt.onStop(close)
  function close() {
    if (disposed) return
    disposed = true
    detach?.()
    detach = undefined
    if (server.listening) server.close()
    for (const socket of sockets) socket.destroy()
  }
  server.on('error', close)
  return {
    token,
    close,
    event(event: RuntimeEvent) {
      const current = owner.deref()
      if (!current || current !== localStartupAttempt() || !current.sampling) {
        close()
        return
      }
      current.progress(event)
      if (
        event.type === 'hello' &&
        event.capabilities.includes('startup.resources.v1') &&
        !disposed &&
        !enabled
      ) {
        enabled = true
        server.listen('\\\\.\\pipe\\auto-mas-startup-' + token.slice(0, 32)).unref()
      }
    },
  }
}
