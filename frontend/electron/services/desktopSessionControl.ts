import { randomBytes } from 'node:crypto'

export const desktopSessionControlToken = randomBytes(32).toString('hex')

let transition = false
let endpoint: string | null = null
let childSessionId: number | null = null

export function setDesktopSessionChildId(value: number | null): void {
  childSessionId = value
}

export function getDesktopSessionChildId(): number | null {
  return childSessionId
}
export function setDesktopSessionTransition(value: boolean): void {
  transition = value
}

export function isDesktopSessionTransition(): boolean {
  return transition
}

export function setDesktopSessionEndpoint(value: string | null): void {
  endpoint = value
}

export function getDesktopSessionEndpoint(): string | null {
  return endpoint
}
