import * as path from 'path'
import { fileURLToPath } from 'url'

export interface RendererNavigationPolicy {
  devServerUrl?: string
  packagedHtmlPath: string
}

function normalizeFilesystemPath(value: string): string {
  const normalized = path.resolve(value)
  return process.platform === 'win32' ? normalized.toLowerCase() : normalized
}

/** Only the configured Vite origin or the packaged index file may own the privileged preload. */
export function isTrustedRendererNavigation(
  candidateUrl: string,
  policy: RendererNavigationPolicy
): boolean {
  try {
    const candidate = new URL(candidateUrl)
    if (policy.devServerUrl) {
      const devServer = new URL(policy.devServerUrl)
      return candidate.origin === devServer.origin && candidate.protocol === devServer.protocol
    }
    if (candidate.protocol !== 'file:') {
      return false
    }
    return (
      normalizeFilesystemPath(fileURLToPath(candidate)) ===
      normalizeFilesystemPath(policy.packagedHtmlPath)
    )
  } catch {
    return false
  }
}

/** External links are delegated to the OS and are never rendered with the application preload. */
export function normalizeExternalNavigation(candidateUrl: string): string | null {
  try {
    const candidate = new URL(String(candidateUrl || '').trim())
    if (!['http:', 'https:', 'mailto:'].includes(candidate.protocol.toLowerCase())) {
      return null
    }
    return candidate.href
  } catch {
    return null
  }
}
