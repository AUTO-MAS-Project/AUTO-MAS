import { randomBytes } from 'node:crypto'

export const desktopSessionControlToken = randomBytes(32).toString('hex')

let transition = false
let endpoint: string | null = null
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
