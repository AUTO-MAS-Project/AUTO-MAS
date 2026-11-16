import type { Page, WebSocketRoute } from '@playwright/test'
import { expect } from '@playwright/test'

export async function observeMainConnection(
  page: Page,
  onMessage?: (message: string | Buffer, route: WebSocketRoute) => void
) {
  const connections: { route: WebSocketRoute; closed: boolean; received: number }[] = []
  await page.routeWebSocket(/\/api\/core\/ws$/, route => {
    const server = route.connectToServer()
    const connection = { route, closed: false, received: 0 }
    connections.push(connection)
    server.onMessage(message => {
      connection.received++
      onMessage?.(message, route)
      route.send(message)
    })
    route.onClose(async (code, reason) => {
      connection.closed = true
      await server.close({ code, reason })
    })
    server.onClose(async (code, reason) => {
      connection.closed = true
      await route.close({ code, reason })
    })
  })
  return {
    connections,
    reconnect: async () => {
      await expect.poll(() => connections.length).toBeGreaterThan(0)
      const previous = connections.at(-1)!
      const count = connections.length
      const timeOrigin = await page.evaluate(() => performance.timeOrigin)
      await previous.route.close({ code: 1012, reason: 'E2E connection interruption' })
      await expect.poll(() => previous.closed).toBe(true)
      await expect.poll(() => connections.length, { timeout: 15_000 }).toBeGreaterThan(count)
      const current = connections.at(-1)!
      expect(current.closed).toBe(false)
      expect(await page.evaluate(() => performance.timeOrigin)).toBe(timeOrigin)
      return current
    },
  }
}
