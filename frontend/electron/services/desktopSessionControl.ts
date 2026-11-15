import { randomBytes } from 'node:crypto'

export const desktopSessionControlToken = randomBytes(32).toString('hex')

let childSessionId: number | null = null

export function setDesktopSessionChildId(value: number | null): void {
  childSessionId = value
}

export function getDesktopSessionChildId(): number | null {
  return childSessionId
}
