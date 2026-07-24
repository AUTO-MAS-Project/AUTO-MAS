import { Buffer } from 'node:buffer'
import { spawnSync } from 'node:child_process'

interface AdminProbeResult {
  status: number | null
  stdout: string | Buffer | null
  error?: Error
}

export type AdminProbeRunner = (
  command: string,
  args: readonly string[],
  options: {
    encoding: 'utf8'
    shell: false
    timeout: number
    windowsHide: true
  }
) => AdminProbeResult

const ADMIN_ROLE_SCRIPT = [
  '$identity = [Security.Principal.WindowsIdentity]::GetCurrent()',
  '$principal = [Security.Principal.WindowsPrincipal]::new($identity)',
  '$role = [Security.Principal.WindowsBuiltInRole]::Administrator',
  "if ($principal.IsInRole($role)) { [Console]::Out.Write('true') } else { [Console]::Out.Write('false') }",
].join('; ')

const ADMIN_ROLE_COMMAND = Buffer.from(ADMIN_ROLE_SCRIPT, 'utf16le').toString('base64')

const defaultRunner: AdminProbeRunner = (command, args, options) =>
  spawnSync(command, [...args], options)

/**
 * Report whether the current Windows process token is actually elevated.
 *
 * A write probe under Windows\Temp is not an elevation check: standard users
 * can usually create files there. WindowsPrincipal evaluates the current token,
 * so a split-token administrator remains false until the process is elevated.
 * Any probe failure is fail-closed and leaves the existing process running.
 */
export function isProcessElevated(
  platform: NodeJS.Platform = process.platform,
  runner: AdminProbeRunner = defaultRunner
): boolean {
  if (platform !== 'win32') return true

  try {
    const result = runner(
      'powershell.exe',
      ['-NoProfile', '-NonInteractive', '-EncodedCommand', ADMIN_ROLE_COMMAND],
      {
        encoding: 'utf8',
        shell: false,
        timeout: 5_000,
        windowsHide: true,
      }
    )
    if (result.error || result.status !== 0) return false
    return (
      String(result.stdout ?? '')
        .trim()
        .toLowerCase() === 'true'
    )
  } catch {
    return false
  }
}
